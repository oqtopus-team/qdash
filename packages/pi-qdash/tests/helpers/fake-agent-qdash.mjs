/**
 * A stateful fake of QDash's agent-session API for the model-driven loop
 * tests: sessions, actions with idempotency keys and state versions, staged
 * candidates, interventions that pause a session, and an expert who answers
 * them. It mirrors the server rules the tools rely on (see
 * src/qdash/api/services/agent_session_service.py,
 * agent_session_gate.py, and agent_intervention_service.py), including the
 * checks of `autonomous` requests against the signed-in user (`GET
 * /auth/me`, set with `setCurrentUser`), and the append-only decisions and
 * the audit timeline of agent_session_audit.py; it measures nothing.
 *
 * Shared by packages/pi-qdash/tests and the agent-runtime CLI/chat parity
 * tests, which reach it over HTTP through the real QDash client.
 */

import { createHash } from "node:crypto";
import { createServer } from "node:http";

const SETTLED = new Set(["completed", "failed", "cancelled"]);

function measurementKey(action) {
  const overrides = Object.keys(action.parameter_overrides ?? {}).sort().map((name) => [name, action.parameter_overrides[name]]);
  return JSON.stringify([action.task_name ?? "", action.qids?.[0] ?? "", overrides]);
}

export function startFakeAgentQDash({ username: initialUser = "alice", projectId = "lab-a" } = {}) {
  /** The user the fixture token signs in as; null answers 401, "error" answers 500. */
  let username = initialUser;
  /** Awaited before each request is handled, so a test can interleave requests. */
  let intercept = async () => {};
  /** A release before autonomous checks: it ignores the flag and returns no `autonomous` field. */
  let legacy = false;
  /** A release before decision records and the audit: those endpoints answer 404. */
  let noAudit = false;
  /** A release before stop requests (404), or a stop that fails with this status. */
  let noStop = false;
  let stopFault = null;
  /**
   * How the next decision POSTs fail, one entry per request: `{ status, detail }` refuses
   * without storing, `{ status, detail, afterStore: true }` stores and then answers the error,
   * and `{ drop: true, afterStore }` closes the connection without an answer.
   */
  let decisionFaults = [];
  /** Status the decision list answers with instead of the list, when set. */
  let decisionListStatus = null;
  /** Decisions one session holds, as MAX_DECISIONS_PER_SESSION. */
  let decisionQuota = 2000;
  // Starts at the real time, so expiry agrees with clocks outside the fake.
  let tick = Date.now();
  const clock = () => new Date((tick += 1_000)).toISOString();
  let seq = 0;
  const id = (prefix) => `${prefix}-${++seq}`;

  const state = {
    sessions: new Map(),
    actions: [],
    interventions: [],
    executions: new Map(),
    /** Results each task yields, oldest first; the default is a completed run with no candidate. */
    outcomes: new Map(),
    requests: [],
    dispatches: [],
    /** The calibration state per qubit: committed candidates, which a later run reads as inputs. */
    calibration: {},
    commits: [],
    decisions: [],
  };

  /** Like QDash, a stored expiry without an offset is UTC (tests may store one to mimic the real API). */
  const utcMillis = (value) => Date.parse(/(?:Z|[+-]\d{2}:?\d{2})$/i.test(value) ? value : `${value}Z`);

  function sessionView(session) {
    if ((session.status === "active" || session.status === "waiting_for_human") && utcMillis(session.expires_at) <= tick) {
      session.status = "expired";
    }
    const { candidates: _c, ...view } = session;
    const copy = structuredClone(view);
    // A release before update authority drops the unknown policy field.
    if (legacy) delete copy.policy.parameter_updates;
    return copy;
  }

  function interventionView(item) {
    const session = state.sessions.get(item.session_id);
    sessionView(session);
    return structuredClone({
      ...item,
      session_status: session.status,
      session_state_version: session.state_version,
      session_expires_at: session.expires_at,
      actions_used: session.action_count,
      max_actions: session.policy.max_actions,
      can_resume: item.status === "open" && session.status === "waiting_for_human",
      resume_blockers: [],
      resume_options: [],
      resume_command: null,
      page_path: `/agent-sessions/${item.session_id}/interventions/${item.intervention_id}`,
    });
  }

  function createSession(body, createdBy = username) {
    const policy = {
      allowed_actions: ["run_task", "request_human", "complete_session"],
      allowed_overrides: {},
      quality_gates: {},
      task_quality_gates: {},
      allow_reconfigure: false,
      max_actions: 100,
      autonomy: "confirm_each",
      max_rounds_per_target: 3,
      ...body.policy,
    };
    const created = clock();
    const session = {
      session_id: id("session"),
      project_id: projectId,
      chip_id: body.chip_id,
      created_by: createdBy,
      policy,
      skill_name: body.skill_name ?? "",
      skill_version: body.skill_version ?? "",
      skill_hash: body.skill_hash ?? "",
      // The model the host reported, as agent_session_service.py stores it; model_name is its label.
      model: body.model ?? null,
      model_name: body.model ? `${body.model.provider}/${body.model.model_id}` : "",
      status: "active",
      state_version: 0,
      action_count: 0,
      created_at: created,
      updated_at: created,
      expires_at: new Date(Date.parse(created) + (body.expires_in_seconds ?? 21_600) * 1_000).toISOString(),
      active_intervention_id: null,
    };
    state.sessions.set(session.session_id, session);
    return session;
  }

  function pause(session, item) {
    session.status = "waiting_for_human";
    session.active_intervention_id = item.intervention_id;
    session.state_version += 1;
    state.interventions.push(item);
  }

  function newIntervention(session, fields) {
    const created = clock();
    return {
      intervention_id: id("int"),
      project_id: projectId,
      session_id: session.session_id,
      chip_id: session.chip_id,
      created_by: username,
      node_id: null,
      task_name: null,
      qids: [],
      attempts: [],
      action_id: null,
      previous_intervention_id: null,
      checkpoint: null,
      plan_hash: "",
      pauses_session: true,
      status: "open",
      response: null,
      resume_claim_key: null,
      notification: { status: "sent", attempts: 1, last_error: "" },
      events: [],
      created_at: created,
      updated_at: created,
      ...fields,
    };
  }

  function policyRejection(session, body) {
    const policy = session.policy;
    if (!policy.allowed_actions.includes(body.action_type)) return `Action '${body.action_type}' is not allowed by the session policy`;
    // Asking for a person or finishing needs no measurement budget.
    if (body.action_type === "request_human" || body.action_type === "complete_session") return null;
    if (session.action_count >= policy.max_actions) return "Session action limit has been reached";
    if (body.action_type !== "run_task") return null;
    if (!policy.allowed_tasks.includes(body.task_name)) return `Task '${body.task_name}' is not allowed by the session policy`;
    const outside = body.qids.filter((qid) => !policy.qids.includes(qid));
    if (outside.length) return `Targets are outside the session scope: ${outside.join(", ")}`;
    for (const [name, value] of Object.entries(body.parameter_overrides ?? {})) {
      const bounds = policy.allowed_overrides[name];
      if (!bounds) return `Parameter override '${name}' is not allowed`;
      if ((bounds.minimum != null && value < bounds.minimum) || (bounds.maximum != null && value > bounds.maximum)) {
        return `Parameter override '${name}' is outside the allowed bounds`;
      }
    }
    return null;
  }

  /** The server's checks of an autonomous request: [status, detail] or null. */
  function autonomousRefusal(session) {
    if (!username || username === "error" || username !== session.created_by) {
      return [403, `Autonomous steps run only in an agent session the signed-in user created; this session belongs to ${session.created_by}.`];
    }
    if (session.policy.autonomy !== "auto") return [409, `The session was approved with autonomy ${session.policy.autonomy}; autonomous steps need autonomy auto`];
    return null;
  }

  const runTasks = (session) => state.actions.filter((action) => action.session_id === session.session_id && action.action_type === "run_task" && action.decision === "authorized");
  const running = (action) => action.execution_status !== "not_started" && !SETTLED.has(action.execution_status);

  function autonomousStepRefusal(session, body) {
    const actions = runTasks(session);
    const busy = actions.filter(running).map((action) => action.action_id);
    if (busy.length) return `Action ${busy.join(", ")} of the session is still running; wait for its result before an autonomous step`;
    const key = measurementKey(body);
    const same = actions.filter((action) => measurementKey(action) === key);
    const unstarted = same.find((action) => action.execution_status === "not_started");
    if (unstarted) return `Action ${unstarted.action_id} already proposes this measurement and was never dispatched; dispatch it instead of proposing it again`;
    const rounds = actions.filter((action) => action.task_name === body.task_name && action.qids.includes(body.qids[0])).length;
    if (rounds >= session.policy.max_rounds_per_target) return `${body.task_name} on ${body.qids[0]} already ran ${rounds} times, the session's max_rounds_per_target`;
    const finished = same.filter((action) => SETTLED.has(action.execution_status));
    if (finished.length && !finished.some((action) => action.action_id === body.repeat_of_action_id)) {
      return `Action ${finished.at(-1).action_id} already ran this exact measurement; repeat it only with repeat_of_action_id naming a finished identical action`;
    }
    if (body.repeat_of_action_id && !finished.length) return `repeat_of_action_id ${body.repeat_of_action_id} is not a finished identical measurement of this session`;
    return downstreamRefusal(session, actions, body.task_name, body.qids[0]);
  }

  /**
   * QDash's step rule (agent_parameter_update.downstream_refusal), in short: unresolved evidence
   * anywhere in the session stops every step, a repeat included, until an expert's resume
   * answer cites that action; a dependent step also waits for the commit of a valid result.
   */
  function downstreamRefusal(session, actions, taskName, qid) {
    const answers = own(state.interventions, session).filter((item) => item.response?.decision === "resume" && ["resumed", "resume_authorized"].includes(item.status));
    const decisions = own(state.decisions, session);
    const grant = session.policy.parameter_updates;
    const resolved = new Set();
    for (const action of actions) {
      if (action.execution_status === "not_started" || !SETTLED.has(action.execution_status)) continue;
      const label = `${action.task_name} on ${action.qids[0]} (action ${action.action_id})`;
      const doubts = decisions.filter((item) => item.evidence_action_ids.includes(action.action_id) && ["fail", "inconclusive"].includes(item.assessment));
      let problem = null;
      let since = action.created_at;
      if (action.execution_status !== "completed") problem = `${label} did not complete (${action.execution_status})`;
      else if (doubts.length) {
        problem = `${label} was assessed ${doubts.at(-1).assessment}`;
        since = doubts.at(-1).recorded_at;
      } else if (grant && grant.tasks.includes(action.task_name)) {
        const granted = (action.candidates ?? []).filter((item) => grant.parameters.includes(item.parameter_name));
        const rejected = granted.find((item) => !item.accepted);
        if (!granted.length) problem = `The result of ${label} carries none of the approved update parameters`;
        else if (rejected) problem = `The ${rejected.parameter_name} candidate of ${label} was rejected`;
      }
      if (!problem) continue;
      const cited = answers.some((item) => (item.attempts ?? []).some((attempt) => attempt.action_id === action.action_id) && item.response.responded_at >= since);
      if (cited) {
        resolved.add(action.action_id);
        continue;
      }
      return `${problem}. QDash stops this session's autonomous steps, commits, and applies until a person answers an intervention about it: call qdash_request_agent_human with attemptActionIds [${action.action_id}].`;
    }
    if (!grant) return null;
    const latest = new Map();
    for (const action of actions) {
      if (action.task_name !== taskName && grant.tasks.includes(action.task_name) && action.qids.includes(qid) && action.execution_status === "completed") latest.set(action.task_name, action);
    }
    for (const [other, action] of latest) {
      if (resolved.has(action.action_id)) continue;
      const label = `${other} on ${qid} (action ${action.action_id})`;
      for (const candidate of (action.candidates ?? []).filter((item) => grant.parameters.includes(item.parameter_name) && item.accepted)) {
        if (!state.commits.some((commit) => commit.action_id === action.action_id && commit.parameter_name === candidate.parameter_name)) {
          return `The accepted ${candidate.parameter_name} of ${label} is not committed. Commit it with qdash_commit_agent_session_update after a pass assessment, or ask a person, before a dependent step.`;
        }
      }
    }
    return null;
  }

  function own(list, session) {
    return list.filter((entry) => entry.session_id === session.session_id);
  }

  /** QDash's checks of a commit under the session's update authority, in short. */
  function updateRefusal(session, action, candidate, body) {
    const refusal = autonomousRefusal(session);
    if (refusal) return refusal;
    const grant = session.policy.parameter_updates;
    if (!grant) return [409, "The session's approval did not grant parameter updates."];
    if (!grant.parameters.includes(candidate.parameter_name) || !grant.tasks.includes(action.task_name)) return [409, "The session's approval does not grant this update."];
    const decisions = own(state.decisions, session);
    const decision = decisions.find((item) => item.decision_id === body.decision_id);
    if (!decision) return [409, `Decision '${body.decision_id}' is not a decision of this session`];
    if (!decision.evidence_action_ids.includes(action.action_id)) return [409, `Decision ${decision.decision_id} does not cite action ${action.action_id} as its evidence`];
    if (decision.assessment !== "pass") return [409, `Decision ${decision.decision_id} assessed the result as ${decision.assessment ?? "not stated"}; only an explicit pass can ground an update.`];
    const doubt = decisions.find((item) => item.evidence_action_ids.includes(action.action_id) && ["fail", "inconclusive"].includes(item.assessment));
    if (doubt) return [409, `Decision ${doubt.decision_id} assessed action ${action.action_id} as ${doubt.assessment}; a failed or uncertain result is never committed under the session's authority.`];
    if (state.commits.some((commit) => commit.action_id === action.action_id && commit.parameter_name === candidate.parameter_name)) return [409, "The candidate was already committed"];
    return null;
  }

  function submit(session, body) {
    const hash = JSON.stringify([body.action_type, body.task_name ?? null, body.qids ?? [], body.parameter_overrides ?? {}, body.diagnosis ?? "", body.expected_state_version, body.autonomous ?? false, body.repeat_of_action_id ?? null]);
    const existing = state.actions.find((action) => action.session_id === session.session_id && action.idempotency_key === body.idempotency_key);
    if (existing) {
      if (existing.request_hash !== hash) return [409, { detail: "Idempotency key was already used for a different action" }];
      return [200, existing];
    }
    sessionView(session);
    if (body.autonomous) {
      const refusal = autonomousRefusal(session);
      if (refusal) return [refusal[0], { detail: refusal[1] }];
    }
    if (session.status !== "active") return [409, { detail: `Agent session is not active: ${session.status}` }];
    if (body.expected_state_version !== session.state_version) {
      return [409, { detail: `Agent session state version mismatch: expected ${body.expected_state_version}, current ${session.state_version}` }];
    }
    if (body.autonomous) {
      const refusal = autonomousStepRefusal(session, body);
      if (refusal) return [409, { detail: refusal }];
    }
    const rejection = policyRejection(session, body);
    const action = {
      action_id: id("action"),
      session_id: session.session_id,
      idempotency_key: body.idempotency_key,
      request_hash: hash,
      action_type: body.action_type,
      task_name: body.task_name ?? null,
      qids: body.qids ?? [],
      parameter_overrides: body.parameter_overrides ?? {},
      diagnosis: body.diagnosis ?? "",
      decision: rejection ? "rejected" : "authorized",
      reason: rejection ?? "Action authorized by the session policy; execution has not started",
      execution_status: "not_started",
      operation_id: null,
      execution_id: null,
      state_version_before: session.state_version,
      state_version_after: session.state_version + 1,
      created_at: clock(),
      intervention_id: null,
      autonomous: body.autonomous === true,
      model: body.model ?? null,
    };
    state.actions.push(action);
    if (!rejection && body.action_type === "request_human") {
      const item = newIntervention(session, { reason: "agent_request", summary: action.diagnosis, question: action.diagnosis, action_id: action.action_id, idempotency_key: `request-human:${action.action_id}`, model: action.model });
      action.intervention_id = item.intervention_id;
      pause(session, item);
    } else {
      session.state_version += 1;
      session.action_count += 1;
      if (!rejection && body.action_type === "complete_session") session.status = "completed";
    }
    return [201, action];
  }

  function execute(session, action, body = {}) {
    if (action.decision !== "authorized") return [409, { detail: "Only authorized agent actions can be executed" }];
    if (action.execution_status !== "not_started") return [200, action];
    sessionView(session);
    if (body.autonomous) {
      const refusal = autonomousRefusal(session);
      if (refusal) return [refusal[0], { detail: refusal[1] }];
    }
    if (session.status !== "active") return [409, { detail: `Agent session is not active: ${session.status}` }];
    if (body.autonomous) {
      const busy = runTasks(session).filter((other) => other.action_id !== action.action_id && running(other)).map((other) => other.action_id);
      if (busy.length) return [409, { detail: `Action ${busy.join(", ")} of the session is being dispatched or is still running; an autonomous step waits for its result` }];
    }
    const queue = state.outcomes.get(action.task_name) ?? [];
    const outcome = queue.shift() ?? { status: "completed", candidates: [] };
    const executionId = id("exec");
    action.operation_id = id("op");
    action.execution_id = executionId;
    action.execution_status = outcome.status;
    action.candidates = (outcome.candidates ?? []).map((candidate) => ({
      session_id: session.session_id,
      action_id: action.action_id,
      execution_id: executionId,
      task_id: id("task"),
      task_name: action.task_name,
      qid: action.qids[0],
      source_parameter_name: candidate.parameter_name,
      error: 0,
      unit: "",
      value_type: "float",
      quality_metrics: {},
      reason: candidate.accepted === false ? "outside the bounds" : "Candidate passed the session gates",
      accepted: true,
      ...candidate,
    }));
    state.executions.set(executionId, { execution_id: executionId, chip_id: session.chip_id, name: `agent:${action.task_name}`, status: SETTLED.has(outcome.status) ? outcome.status : "running", note: outcome.note ?? {} });
    // A fresh run reads its declared inputs from the current calibration state.
    state.dispatches.push({ action_id: action.action_id, task_name: action.task_name, qid: action.qids[0], parameter_overrides: action.parameter_overrides, calibration: structuredClone(state.calibration[action.qids[0]] ?? {}) });
    return [200, action];
  }

  /** The expert's answer, given in QDash (not by the agent). */
  function respond(sessionId, { decision = "resume", guidance = "", respondedBy = "expert", interventionId } = {}) {
    const session = state.sessions.get(sessionId);
    const item = state.interventions.find((entry) => entry.intervention_id === (interventionId ?? session.active_intervention_id));
    const at = clock();
    item.response = { response_id: id("resp"), idempotency_key: id("respond"), decision, guidance, resume_node_id: null, responded_by: respondedBy, responded_at: at, expected_state_version: session.state_version };
    item.updated_at = at;
    if (decision === "stop") {
      item.status = "stopped";
      session.status = "cancelled";
    } else if (item.checkpoint) {
      item.status = "resume_authorized";
    } else {
      item.status = "resumed";
      session.status = "active";
    }
    if (session.status !== "waiting_for_human") session.active_intervention_id = null;
    session.state_version += 1;
    return item;
  }

  const server = createServer(async (request, response) => {
    const url = new URL(request.url, "http://fake");
    let body;
    if (request.method === "POST") {
      const chunks = [];
      for await (const chunk of request) chunks.push(chunk);
      body = chunks.length ? JSON.parse(Buffer.concat(chunks).toString("utf8")) : {};
    }
    state.requests.push({ method: request.method, path: url.pathname, query: url.search, body });
    if (legacy && body) delete body.autonomous;
    await intercept({ method: request.method, path: url.pathname, body });
    const send = (status, payload) => {
      response.writeHead(status, { "content-type": "application/json" });
      response.end(JSON.stringify(payload));
    };
    const parts = url.pathname.split("/").filter(Boolean).map(decodeURIComponent);
    if (url.pathname === "/auth/me" && request.method === "GET") {
      if (username === "error") return send(500, { detail: "Internal Server Error" });
      if (!username) return send(401, { detail: "Not authenticated" });
      return send(200, { username, full_name: username, disabled: false });
    }
    if (parts[0] === "executions" && parts.length === 2 && request.method === "GET") {
      const execution = state.executions.get(parts[1]);
      return execution ? send(200, execution) : send(404, { detail: "Execution not found" });
    }
    if (parts[0] !== "agent-sessions") return send(404, { detail: `fake has no ${url.pathname}` });
    if (parts.length === 1) {
      if (request.method === "POST") return send(201, sessionView(createSession(body)));
      const statuses = url.searchParams.getAll("status");
      const chip = url.searchParams.get("chip_id");
      const mine = url.searchParams.get("mine") === "true";
      const limit = Number(url.searchParams.get("limit") ?? 20);
      const items = [...state.sessions.values()]
        .reverse()
        .map(sessionView)
        .filter((session) => (!chip || session.chip_id === chip) && (!mine || session.created_by === username) && (!statuses.length || statuses.includes(session.status)))
        .slice(0, limit);
      return send(200, { items, total: items.length });
    }
    const session = state.sessions.get(parts[1]);
    if (!session) return send(404, { detail: `Agent session '${parts[1]}' not found` });
    if (parts.length === 2) return send(200, sessionView(session));
    const own = (list) => list.filter((entry) => entry.session_id === session.session_id);
    if (parts[2] === "actions") {
      if (parts.length === 3) {
        if (request.method === "POST") {
          const [status, payload] = submit(session, body);
          return send(status, status < 300 ? publicAction(payload) : payload);
        }
        const items = own(state.actions).map(publicAction);
        return send(200, { items, total: items.length });
      }
      const action = own(state.actions).find((entry) => entry.action_id === parts[3]);
      if (!action) return send(404, { detail: `Agent action ${parts[3]} not found` });
      if (parts.length === 4) return send(200, publicAction(action));
      if (parts[4] === "execute") {
        const [status, payload] = execute(session, action, body);
        return send(status, status < 300 ? publicAction(payload) : payload);
      }
      if (parts[4] === "candidates" && parts[6] === "commit" && request.method === "POST") {
        // The commit: re-checks the staged candidate and writes the calibration state.
        const replay = state.commits.find((commit) => commit.session_id === session.session_id && commit.idempotency_key && commit.idempotency_key === body.idempotency_key);
        if (replay) return send(200, publicCommit(replay));
        sessionView(session);
        if (session.status !== "active") return send(409, { detail: `Agent session is not active: ${session.status}` });
        if (body.expected_state_version !== session.state_version) {
          return send(409, { detail: `Agent session state version mismatch: expected ${body.expected_state_version}, current ${session.state_version}` });
        }
        const candidate = (action.candidates ?? []).find((item) => item.parameter_name === parts[5] && item.task_id === body.task_id);
        if (!candidate || !candidate.accepted) return send(409, { detail: "The candidate is missing or was rejected by the session gates" });
        if (body.autonomous) {
          const refusal = updateRefusal(session, action, candidate, body);
          if (refusal) return send(refusal[0], { detail: refusal[1] });
        }
        const before = state.calibration[candidate.qid]?.[candidate.parameter_name] ?? null;
        state.calibration[candidate.qid] = { ...(state.calibration[candidate.qid] ?? {}), [candidate.parameter_name]: candidate.value };
        const commit = {
          commit_id: id("commit"),
          session_id: session.session_id,
          action_id: action.action_id,
          idempotency_key: body.idempotency_key,
          task_id: candidate.task_id,
          parameter_name: candidate.parameter_name,
          value: candidate.value,
          qid: candidate.qid,
          status: "committed",
          before_value: before,
          before_snapshot: before === null ? null : { value: before },
          after_snapshot: { value: candidate.value },
          committed_by: username,
          state_version_before: session.state_version,
          state_version_after: session.state_version + 1,
          created_at: clock(),
          authority: body.autonomous ? "session_policy" : "reviewed",
          decision_id: body.autonomous ? body.decision_id : null,
          backend_status: "not_started",
          backend_authority: null,
        };
        session.state_version += 1;
        state.commits.push(commit);
        return send(200, publicCommit(commit));
      }
      if (parts[4] === "candidates") {
        if (!SETTLED.has(action.execution_status)) return send(409, { detail: "The action has not finished" });
        if (action.execution_status !== "completed") return send(409, { detail: `The action's execution ${action.execution_status}` });
        const items = structuredClone(action.candidates ?? []);
        return send(200, { items, total: items.length });
      }
    }
    if (parts[2] === "commits" && parts[4] === "apply" && request.method === "POST") {
      const commit = state.commits.find((entry) => entry.session_id === session.session_id && entry.commit_id === parts[3]);
      if (!commit) return send(404, { detail: `Agent candidate commit '${parts[3]}' not found` });
      if (commit.backend_apply_key === body.idempotency_key) return send(200, publicCommit(commit));
      sessionView(session);
      if (session.status !== "active") return send(409, { detail: `Agent session is not active: ${session.status}` });
      if (body.autonomous) {
        const refusal = autonomousRefusal(session);
        if (refusal) return send(refusal[0], { detail: refusal[1] });
        if (!session.policy.parameter_updates?.apply_backend) return send(409, { detail: "The session's approval granted commits but not backend applies" });
        if (commit.authority !== "session_policy") return send(409, { detail: "Only a commit made under the session's update authority is applied under it" });
        if (commit.backend_status !== "not_started") return send(409, { detail: "A backend apply was already requested; a failed apply needs a person" });
      }
      commit.backend_apply_key = body.idempotency_key;
      commit.backend_status = "queued";
      commit.backend_operation_id = id("apply");
      commit.backend_authority = body.autonomous ? "session_policy" : "reviewed";
      return send(200, publicCommit(commit));
    }
    if ((parts[2] === "decisions" || parts[2] === "audit") && noAudit) return send(404, { detail: "Not Found" });
    if (parts[2] === "decisions") {
      if (request.method === "GET") {
        if (decisionListStatus) return send(decisionListStatus, { detail: "Service Unavailable" });
        const items = own(state.decisions).map((item) => structuredClone(item));
        return send(200, { items, total: items.length });
      }
      if (!username || username !== session.created_by) {
        return send(403, { detail: `Only ${session.created_by}, who created this agent session, records its decisions` });
      }
      // As QDash does, the reported model is provenance and not part of the request hash.
      const { model: _model, ...hashed } = body;
      const hash = JSON.stringify(hashed);
      const existing = own(state.decisions).find((item) => item.idempotency_key === body.idempotency_key);
      if (existing) {
        if (existing.request_hash !== hash) return send(409, { detail: "Idempotency key was already used for a different decision" });
        return send(200, structuredClone(existing));
      }
      const fault = decisionFaults.shift();
      const fail = () => {
        if (fault.drop) return request.socket.destroy();
        return send(fault.status, { detail: fault.detail ?? "Internal Server Error" });
      };
      if (fault && !fault.afterStore) return fail();
      if (own(state.decisions).length >= decisionQuota) {
        return send(409, { detail: `The session's audit is full: it already holds ${decisionQuota} decisions, so no further decision is recorded` });
      }
      const actions = own(state.actions);
      const unknown = [...(body.evidence_action_ids ?? []), ...(body.next_action_id ? [body.next_action_id] : [])].filter((actionId) => !actions.some((entry) => entry.action_id === actionId));
      if (unknown.length) return send(409, { detail: `Not actions of this session: ${unknown.join(", ")}` });
      if (body.intervention_id && !own(state.interventions).some((entry) => entry.intervention_id === body.intervention_id)) {
        return send(409, { detail: `Not an intervention of this session: ${body.intervention_id}` });
      }
      if (body.supersedes_decision_id && !own(state.decisions).some((entry) => entry.decision_id === body.supersedes_decision_id)) {
        return send(409, { detail: `Not a decision of this session: ${body.supersedes_decision_id}` });
      }
      const decision = {
        decision_id: id("decision"),
        session_id: session.session_id,
        project_id: projectId,
        chip_id: session.chip_id,
        idempotency_key: body.idempotency_key,
        request_hash: hash,
        recorded_by: username,
        recorded_at: clock(),
        session_status_at_record: session.status,
        session_state_version_at_record: session.state_version,
        assessment: body.assessment ?? null,
        interpretation: body.interpretation,
        next_action: body.next_action,
        next_detail: body.next_detail ?? "",
        evidence_action_ids: body.evidence_action_ids ?? [],
        evaluation_ids: body.evaluation_ids ?? [],
        next_action_id: body.next_action_id ?? null,
        intervention_id: body.intervention_id ?? null,
        supersedes_decision_id: body.supersedes_decision_id ?? null,
        model: body.model ?? null,
        evidence_snapshot: {
          actions: (body.evidence_action_ids ?? []).map((actionId) => {
            const action = actions.find((entry) => entry.action_id === actionId);
            return { action_id: actionId, task_name: action.task_name, decision: action.decision, execution_status: action.execution_status, execution_id: action.execution_id, task_id: action.candidates?.[0]?.task_id ?? null };
          }),
          evaluations: [],
        },
      };
      state.decisions.push(decision);
      if (fault) return fail();
      return send(201, structuredClone(decision));
    }
    if (parts[2] === "stop" && request.method === "POST") {
      if (noStop) return send(404, { detail: "Not Found" });
      if (stopFault) return send(stopFault, { detail: "Internal Server Error" });
      sessionView(session);
      const inFlight = () =>
        own(state.actions)
          .filter((entry) => entry.decision === "authorized" && ["dispatching", "queued", "running"].includes(entry.execution_status))
          .map((entry) => ({ kind: "measurement", id: entry.action_id, status: entry.execution_status, execution_id: entry.execution_id }));
      const closed = [];
      let outcome;
      if (session.stop && session.stop.idempotency_key === body.idempotency_key) {
        if (session.stop.reason !== body.reason) return send(409, { detail: "Idempotency key was already used for a different stop" });
        outcome = "already_stopped";
      } else if (session.status !== "active" && session.status !== "waiting_for_human") {
        outcome = "already_ended";
      } else {
        session.stop = { stopped_by: username, stopped_at: clock(), reason: body.reason, idempotency_key: body.idempotency_key, status_before: session.status, state_version: session.state_version + 1 };
        session.status = "cancelled";
        session.state_version += 1;
        session.active_intervention_id = null;
        for (const item of own(state.interventions)) {
          if (item.status === "open" || item.status === "resume_authorized") {
            item.status = "stopped";
            closed.push(item.intervention_id);
          }
        }
        outcome = "stopped";
      }
      return send(200, { outcome, session: sessionView(session), in_flight: inFlight(), closed_intervention_ids: closed });
    }
    if (parts[2] === "audit") {
      // Pages of one snapshot, as agent_session_audit.py serves them: a cursor names the
      // snapshot, and a page of a snapshot whose records changed is refused with 409.
      const header = { ...sessionView(session), missing: ["skill_name", "skill_version", "skill_hash", "model"].filter((name) => !session[name]) };
      const events = auditEvents(session);
      const snapshotId = createHash("sha256").update(JSON.stringify([header, events])).digest("hex").slice(0, 32);
      const cursor = url.searchParams.get("cursor");
      let start = 0;
      if (cursor) {
        const [snapshot, offset] = cursor.split(":");
        if (snapshot !== snapshotId) {
          return send(409, { detail: "The session's audit changed after its first page was read; the pages already read belong to an older snapshot. Read it again from the first page" });
        }
        start = Number(offset);
      }
      const limit = parts[3] === "export" ? events.length : Number(url.searchParams.get("limit") ?? 100);
      const page = events.slice(start, start + limit);
      const more = start + limit < events.length;
      return send(200, {
        schema_version: "qdash.agent-session-audit.v1",
        generated_at: clock(),
        snapshot_id: snapshotId,
        session: header,
        events: page,
        total_events: events.length,
        next_cursor: more ? `${snapshotId}:${start + limit}` : null,
        complete: !more,
        notes: [],
      });
    }
    if (parts[2] === "interventions") {
      if (parts.length === 3 && request.method === "POST") {
        const existing = own(state.interventions).find((entry) => entry.idempotency_key === body.idempotency_key);
        if (existing) return send(200, interventionView(existing));
        sessionView(session);
        if (body.autonomous) {
          const refusal = autonomousRefusal(session);
          if (refusal) return send(refusal[0], { detail: refusal[1] });
        }
        if (session.status === "waiting_for_human") return send(409, { detail: `Agent session already waits on intervention ${session.active_intervention_id}` });
        for (const attempt of body.attempts ?? []) {
          if (attempt.action_id && !own(state.actions).some((entry) => entry.action_id === attempt.action_id)) {
            return send(422, { detail: `Action ${attempt.action_id} is not part of this session` });
          }
        }
        const item = newIntervention(session, {
          idempotency_key: body.idempotency_key,
          reason: body.reason,
          summary: body.summary,
          question: body.question,
          task_name: body.task_name ?? null,
          qids: body.qids ?? [],
          attempts: (body.attempts ?? []).map((attempt) => ({ node_id: "", task_name: "", qid: "", transition: "", status: "", reason: "", execution_id: null, task_id: null, evaluation_id: null, evaluation_run_id: null, ...attempt })),
          pauses_session: session.status === "active",
          model: body.model ?? null,
        });
        if (session.status === "active") pause(session, item);
        else state.interventions.push(item);
        return send(201, interventionView(item));
      }
      if (parts.length === 3) {
        const items = own(state.interventions).slice().reverse().map(interventionView);
        return send(200, { items, total: items.length });
      }
      const item = own(state.interventions).find((entry) => entry.intervention_id === parts[3]);
      if (!item) return send(404, { detail: "Intervention not found" });
      if (parts.length === 4) return send(200, interventionView(item));
      // respond and claim-resume are the expert's and the plan runner's, never the agent's.
      return send(403, { detail: "The fake only lets the expert answer, through respond()" });
    }
    return send(404, { detail: `fake has no ${url.pathname}` });
  });

  /** The session's timeline, built from the fake's records as the server builds it. */
  function auditEvents(session) {
    const mine = (list) => list.filter((entry) => entry.session_id === session.session_id);
    const event = (fields) => ({ actor: null, actor_kind: "unknown", status: null, status_is_current: false, action_id: null, execution_id: null, task_id: null, task_name: null, qid: null, commit_id: null, evaluation_id: null, intervention_id: null, decision_id: null, model: null, missing: [], data: {}, ...fields });
    // An agent record without a reported model names it in missing, as agent_session_audit.py does.
    const modelFields = (model, missing = []) => ({ model: model ?? null, missing: model ? missing : [...missing, "model"] });
    const events = [event({ event_id: `session_created:${session.session_id}`, at: session.created_at, state_version: 0, kind: "session_created", summary: `${session.created_by} approved a session`, actor: session.created_by, actor_kind: "human", provenance: "server_record", ...modelFields(session.model) })];
    const cited = new Set(mine(state.decisions).flatMap((decision) => decision.evidence_action_ids));
    for (const action of mine(state.actions)) {
      const target = action.task_name ? `${action.task_name} on ${action.qids.join(", ")}` : action.action_type;
      events.push(event({ event_id: `action_proposed:${action.action_id}`, at: action.created_at, state_version: action.state_version_before, kind: "action_proposed", summary: action.decision === "rejected" ? `Rejected ${target}: ${action.reason} (not executed)` : `Authorized ${target}`, actor: session.created_by, actor_kind: "agent", provenance: "server_record", status: action.decision, action_id: action.action_id, ...modelFields(action.model), data: { intent: action.diagnosis, requested_overrides: action.parameter_overrides } }));
      if (action.operation_id) {
        const settled = SETTLED.has(action.execution_status);
        events.push(event({ event_id: `measurement:${action.action_id}`, at: action.created_at, state_version: action.state_version_after, kind: "measurement", summary: `${target}: ${action.execution_status}`, actor_kind: "worker", provenance: "server_record", status: action.execution_status, status_is_current: true, action_id: action.action_id, execution_id: action.execution_id, missing: settled && !cited.has(action.action_id) ? ["decision"] : [], data: { gate: action.candidates ?? [] } }));
      }
    }
    for (const decision of mine(state.decisions)) {
      events.push(event({ event_id: `decision:${decision.decision_id}`, at: decision.recorded_at, state_version: decision.session_state_version_at_record, kind: "decision", summary: `Assessed ${decision.assessment ?? "not stated"}; next ${decision.next_action}${decision.next_detail ? `: ${decision.next_detail}` : ""}`, actor: decision.recorded_by, actor_kind: "agent", provenance: "agent_reported", status: "recorded", decision_id: decision.decision_id, intervention_id: decision.intervention_id, ...modelFields(decision.model), data: decision }));
    }
    for (const item of mine(state.interventions)) {
      events.push(event({ event_id: `intervention_opened:${item.intervention_id}`, at: item.created_at, state_version: session.state_version, kind: "intervention_opened", summary: `Asked an expert (${item.reason}): ${item.question}`, actor: item.created_by, actor_kind: "agent", provenance: "agent_reported", status: item.status, status_is_current: true, intervention_id: item.intervention_id, ...modelFields(item.model) }));
      if (item.response) {
        events.push(event({ event_id: `intervention_response:${item.response.response_id}`, at: item.response.responded_at, state_version: item.response.expected_state_version, kind: "intervention_response", summary: `${item.response.responded_by} chose ${item.response.decision}: ${item.response.guidance}`, actor: item.response.responded_by, actor_kind: "human", provenance: "human_reported", intervention_id: item.intervention_id }));
      }
    }
    for (const commit of mine(state.commits)) {
      events.push(event({ event_id: `candidate_commit:${commit.commit_id}`, at: commit.created_at, state_version: commit.state_version_before, kind: "candidate_commit", summary: `Commit of ${commit.parameter_name} = ${commit.value} on ${commit.qid}: ${commit.status} (was ${commit.before_value})`, actor: session.created_by, actor_kind: "human", provenance: "server_record", status: commit.status, status_is_current: true, commit_id: commit.commit_id, data: { before_value: commit.before_value, after_value: commit.value } }));
    }
    events.sort((a, b) => (a.at < b.at ? -1 : a.at > b.at ? 1 : a.state_version - b.state_version));
    return events.map((item, sequence) => ({ ...item, sequence }));
  }

  function publicCommit(commit) {
    const { before_value: _before, backend_apply_key: _key, ...view } = commit;
    if (legacy) {
      delete view.authority;
      delete view.decision_id;
    }
    return structuredClone(view);
  }

  function publicAction(action) {
    const { request_hash: _hash, candidates: _candidates, ...view } = action;
    if (legacy) delete view.autonomous;
    return structuredClone(view);
  }

  return new Promise((resolve) => {
    server.listen(0, "127.0.0.1", () =>
      resolve({
        baseUrl: `http://127.0.0.1:${server.address().port}`,
        state,
        createSession,
        respond,
        /** Queue what the next runs of `taskName` yield. */
        queueOutcome(taskName, ...outcomes) {
          state.outcomes.set(taskName, [...(state.outcomes.get(taskName) ?? []), ...outcomes]);
        },
        /** Sign the fixture token in as `name` (null: 401, "error": 500). */
        setCurrentUser(name) {
          username = name;
        },
        /** Behave as a QDash release before decision records and the audit existed. */
        setNoAuditServer(value) {
          noAudit = value;
        },
        /** Fail the next decision POSTs as listed (see `decisionFaults`). */
        failDecisions(...faults) {
          decisionFaults = faults;
        },
        /** Answer the decision list with this status (null: the list). */
        setDecisionListStatus(value) {
          decisionListStatus = value;
        },
        /** Set how many decisions one session holds. */
        setDecisionQuota(value) {
          decisionQuota = value;
        },
        /** Behave as a QDash release before session stop requests existed. */
        setNoStopServer(value) {
          noStop = value;
        },
        /** Fail every stop with this status (null: answer). */
        setStopFault(value) {
          stopFault = value;
        },
        /** Behave as a QDash release before autonomous checks existed. */
        setLegacyServer(value) {
          legacy = value;
        },
        /** Await `hook({ method, path, body })` before handling each request; none to reset. */
        setIntercept(hook) {
          intercept = hook ?? (async () => {});
        },
        /** Submit an action as another client would, outside the tools. */
        submitDirect(sessionId, body) {
          const [status, payload] = submit(state.sessions.get(sessionId), { qids: [], parameter_overrides: {}, diagnosis: "", ...body });
          return { status, payload: status < 300 ? publicAction(payload) : payload };
        },
        /** Dispatch an action as another client would, outside the tools. */
        executeDirect(sessionId, actionId, body = {}) {
          const action = state.actions.find((entry) => entry.action_id === actionId);
          return execute(state.sessions.get(sessionId), action, body);
        },
        /** Move the fake clock, for expiry. */
        advance(seconds) {
          tick += seconds * 1_000;
        },
        /** Pretend a dispatched run is still going, then let it finish. */
        setExecution(actionId, status) {
          const action = state.actions.find((entry) => entry.action_id === actionId);
          action.execution_status = status;
          if (action.execution_id) state.executions.get(action.execution_id).status = status;
        },
        close: () => new Promise((done) => server.close(done)),
      }),
    );
  });
}
