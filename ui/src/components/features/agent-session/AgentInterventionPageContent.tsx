"use client";

import { useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Play, RotateCcw, Square } from "lucide-react";
import Link from "next/link";
import { type ReactNode, useState } from "react";
import { toast } from "sonner";

import {
  getGetAgentInterventionQueryKey,
  getGetAgentSessionQueryKey,
  getListAgentInterventionsQueryKey,
  useGetAgentIntervention,
  useRespondAgentIntervention,
  useRetryAgentInterventionNotification,
} from "@/client/agent-session/agent-session";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { PageContainer } from "@/components/ui/PageContainer";
import { QubitTile } from "@/components/ui/QubitTile";
import { useProject } from "@/contexts/ProjectContext";
import { getApiErrorMessage } from "@/lib/utils/apiError";
import { formatDateTime } from "@/lib/utils/datetime";
import type { AgentInterventionAttempt, AgentInterventionResponse } from "@/schemas";

import {
  interventionActionState,
  interventionReasonLabel,
  interventionStatusStyle,
  notificationStyle,
  sessionStatusLabel,
} from "./interventionLabels";
import { projectRequest, useLinkedProject } from "./useLinkedProject";

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <div className="text-xs text-base-content/60">{label}</div>
      <div className="mt-1 text-sm">{children}</div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="card card-border bg-base-100">
      <div className="card-body gap-3 p-4">
        <h2 className="text-sm font-medium">{title}</h2>
        {children}
      </div>
    </section>
  );
}

function AttemptLinks({ attempt }: { attempt: AgentInterventionAttempt }) {
  const links: { href: string; label: string }[] = [];
  if (attempt.execution_id) {
    links.push({
      href: `/executions/${encodeURIComponent(attempt.execution_id)}`,
      label: "Execution",
    });
  }
  if (attempt.task_id) {
    links.push({
      href: `/task-results/${encodeURIComponent(attempt.task_id)}`,
      label: "Result and figures",
    });
  }
  if (attempt.evaluation_run_id) {
    links.push({
      href: `/evaluations/${encodeURIComponent(attempt.evaluation_run_id)}`,
      label: "Evaluation",
    });
  }
  if (links.length === 0) return <span className="text-base-content/60">-</span>;
  return (
    <div className="flex flex-wrap gap-x-3 gap-y-1">
      {links.map((link) => (
        <Link key={link.href} href={link.href} className="link link-hover">
          {link.label}
        </Link>
      ))}
    </div>
  );
}

function AttemptsTable({ attempts }: { attempts: AgentInterventionAttempt[] }) {
  if (attempts.length === 0) {
    return <p className="text-sm text-base-content/60">The agent attached no attempts</p>;
  }
  return (
    <div className="overflow-x-auto">
      <p className="mb-2 text-xs text-base-content/60">
        Outcome and reason are as the agent reported them. QDash checked that the evidence links
        belong to this session.
      </p>
      <table className="table table-sm">
        <thead>
          <tr>
            <th>Node</th>
            <th>Task</th>
            <th>Outcome</th>
            <th>Reason</th>
            <th>Evidence</th>
          </tr>
        </thead>
        <tbody>
          {attempts.map((attempt, index) => (
            <tr key={`${attempt.action_id ?? "attempt"}-${index}`}>
              <td className="font-mono text-xs">{attempt.node_id || "-"}</td>
              <td>
                <div className="flex flex-wrap items-center gap-2">
                  <span>{attempt.task_name || "-"}</span>
                  {attempt.qid ? <QubitTile qid={attempt.qid} /> : null}
                </div>
              </td>
              <td>
                <div className="flex flex-col gap-0.5">
                  <span>{attempt.status || "-"}</span>
                  {attempt.transition ? (
                    <span className="text-xs text-base-content/60">{attempt.transition}</span>
                  ) : null}
                </div>
              </td>
              <td className="max-w-md whitespace-pre-wrap break-words text-xs">
                {attempt.reason || "-"}
              </td>
              <td>
                <AttemptLinks attempt={attempt} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function StatusAlert({ intervention }: { intervention: AgentInterventionResponse }) {
  switch (intervention.status) {
    case "open":
    case "responding":
      return intervention.pauses_session ? (
        <div role="alert" className="alert alert-warning alert-soft">
          <span>
            The session is paused. No action, measurement, or commit runs until an expert answers.
          </span>
        </div>
      ) : (
        <div role="alert" className="alert alert-soft">
          <span>
            Recorded on a {sessionStatusLabel(intervention.session_status).toLowerCase()} session;
            it cannot resume. Close it once reviewed.
          </span>
        </div>
      );
    case "resume_authorized":
      return (
        <div role="alert" className="alert alert-info alert-soft alert-vertical items-start">
          <span>
            Resume authorized. The session stays paused until the plan&apos;s runner claims the
            resume; QDash does not start the runner. Run this where the plan ran, with your client
            profile:
          </span>
          {intervention.resume_command ? (
            <code className="block w-full overflow-x-auto rounded-field bg-base-200 px-3 py-2 font-mono text-xs">
              {intervention.resume_command}
            </code>
          ) : null}
        </div>
      );
    case "resumed":
      return (
        <div role="alert" className="alert alert-success alert-soft">
          <span>
            {intervention.checkpoint
              ? `A runner resumed the plan${intervention.resumed_by ? ` (${intervention.resumed_by})` : ""}.`
              : "The session is active again; the agent continues with its own proposals."}
          </span>
        </div>
      );
    case "stopped":
      return (
        <div role="alert" className="alert alert-soft">
          <span>The expert stopped this session. It is not reactivated.</span>
        </div>
      );
    default:
      return null;
  }
}

function ResponseRecord({ intervention }: { intervention: AgentInterventionResponse }) {
  const response = intervention.response;
  if (!response) return null;
  return (
    <div className="grid gap-3 md:grid-cols-3">
      <Field label="Decision">
        {response.decision === "resume" ? "Resume" : "Stop"}
        {response.resume_node_id ? (
          <span className="text-base-content/60"> from {response.resume_node_id}</span>
        ) : null}
      </Field>
      <Field label="Answered by">
        {response.responded_by}
        <span className="text-base-content/60"> · {formatDateTime(response.responded_at)}</span>
      </Field>
      {intervention.resume_outcome ? (
        <Field label="Resumed run">
          {intervention.resume_outcome.transition}
          {intervention.resume_outcome.reason ? (
            <span className="text-base-content/60"> · {intervention.resume_outcome.reason}</span>
          ) : null}
        </Field>
      ) : null}
      <div className="md:col-span-3">
        <Field label="Guidance">
          <p className="whitespace-pre-wrap break-words">{response.guidance || "-"}</p>
        </Field>
      </div>
    </div>
  );
}

function ResponseForm({
  intervention,
  onAnswered,
}: {
  intervention: AgentInterventionResponse;
  onAnswered: () => void;
}) {
  const respond = useRespondAgentIntervention({
    request: projectRequest(intervention.project_id),
  });
  const [guidance, setGuidance] = useState("");
  const options = intervention.resume_options ?? [];
  const stoppedNode = intervention.checkpoint?.stopped_node_id ?? "";
  const [resumeNode, setResumeNode] = useState(stoppedNode);
  const [confirmStop, setConfirmStop] = useState(false);
  const [idempotencyKey, setIdempotencyKey] = useState(() => crypto.randomUUID());
  const blockers = intervention.resume_blockers ?? [];
  const chosen = options.find((option) => option.node_id === resumeNode);
  const resumeDisabled =
    respond.isPending || !intervention.can_resume || (chosen !== undefined && !chosen.available);

  const submit = (decision: "resume" | "stop") => {
    respond.mutate(
      {
        sessionId: intervention.session_id,
        interventionId: intervention.intervention_id,
        data: {
          idempotency_key: idempotencyKey,
          expected_state_version: intervention.session_state_version,
          decision,
          guidance,
          resume_node_id:
            decision === "resume" && intervention.checkpoint && resumeNode ? resumeNode : null,
        },
      },
      {
        onSuccess: () => {
          setConfirmStop(false);
          toast.success(decision === "resume" ? "Resume authorized" : "Session stopped");
          onAnswered();
        },
        onError: (error) => {
          setConfirmStop(false);
          setIdempotencyKey(crypto.randomUUID());
          toast.error(getApiErrorMessage(error, "The answer was not recorded"));
          onAnswered();
        },
      },
    );
  };

  return (
    <div className="flex flex-col gap-3">
      {blockers.length > 0 ? (
        <div role="alert" className="alert alert-warning alert-soft alert-vertical items-start">
          <span className="font-medium">Resume is not possible</span>
          <ul className="list-disc pl-5 text-sm">
            {blockers.map((blocker) => (
              <li key={blocker}>{blocker}</li>
            ))}
          </ul>
        </div>
      ) : null}
      <fieldset className="fieldset">
        <legend className="fieldset-legend">Guidance</legend>
        <textarea
          className="textarea w-full"
          rows={4}
          maxLength={5000}
          value={guidance}
          onChange={(event) => setGuidance(event.target.value)}
          placeholder="What you found and what the agent should consider"
          aria-describedby="guidance-help"
        />
        <p id="guidance-help" className="label whitespace-normal">
          {intervention.checkpoint
            ? "Stored on this record with your name. The resume-plan command prints it for the person running the resume; the plan runner does not act on it."
            : "Stored on this record with your name. An agent operated from pi or chat can read it with its intervention tool."}{" "}
          It does not change the plan, the scope, or any parameter.
        </p>
      </fieldset>
      {intervention.checkpoint && options.length > 0 ? (
        <fieldset className="fieldset">
          <legend className="fieldset-legend">Resume from</legend>
          <select
            className="select w-full sm:w-auto"
            value={resumeNode}
            onChange={(event) => setResumeNode(event.target.value)}
            aria-describedby="resume-node-help"
          >
            {options.map((option) => (
              <option key={option.node_id} value={option.node_id} disabled={!option.available}>
                {option.node_id} · {option.task_name} · {option.visits}
                {option.max_visits ? `/${option.max_visits}` : ""} runs
                {option.node_id === stoppedNode ? " · stopped here" : ""}
              </option>
            ))}
          </select>
          <p id="resume-node-help" className="label whitespace-normal">
            Only nodes of the approved plan. Completed measurements are not repeated; the node runs
            as a new visit within its limit.
          </p>
        </fieldset>
      ) : null}
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          className="btn btn-primary"
          disabled={resumeDisabled}
          onClick={() => submit("resume")}
        >
          <Play data-icon="inline-start" aria-hidden="true" />
          {intervention.checkpoint ? "Authorize resume" : "Reactivate session"}
        </button>
        <button
          type="button"
          className="btn btn-outline btn-error"
          disabled={respond.isPending}
          onClick={() => setConfirmStop(true)}
        >
          <Square data-icon="inline-start" aria-hidden="true" />
          {intervention.pauses_session ? "Stop session" : "Close"}
        </button>
      </div>
      <ConfirmDialog
        open={confirmStop}
        onOpenChange={setConfirmStop}
        title={intervention.pauses_session ? "Stop this session?" : "Close this intervention?"}
        description={
          intervention.pauses_session
            ? "The session is cancelled and cannot be reactivated. Further work needs a newly authorized session."
            : "The intervention is closed with your guidance. The session does not change."
        }
        confirmLabel={intervention.pauses_session ? "Stop session" : "Close"}
        destructive
        pending={respond.isPending}
        onConfirm={() => submit("stop")}
      />
    </div>
  );
}

function NotificationPanel({
  intervention,
  canEdit,
  onRetried,
}: {
  intervention: AgentInterventionResponse;
  canEdit: boolean;
  onRetried: () => void;
}) {
  const retry = useRetryAgentInterventionNotification({
    request: projectRequest(intervention.project_id),
  });
  const delivery = intervention.notification;
  const style = notificationStyle(delivery.status);
  const retryable = canEdit && ["pending", "failed", "sending"].includes(delivery.status);
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <span className={`badge badge-soft ${style.badge}`}>{style.label}</span>
        <span className="text-xs text-base-content/60">
          {delivery.attempts} {delivery.attempts === 1 ? "attempt" : "attempts"}
          {delivery.sent_at ? ` · sent ${formatDateTime(delivery.sent_at)}` : ""}
          {delivery.next_attempt_at && delivery.status === "pending"
            ? ` · next try ${formatDateTime(delivery.next_attempt_at)}`
            : ""}
        </span>
        {retryable ? (
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            disabled={retry.isPending}
            onClick={() =>
              retry.mutate(
                {
                  sessionId: intervention.session_id,
                  interventionId: intervention.intervention_id,
                },
                {
                  onSuccess: () => onRetried(),
                  onError: (error) =>
                    toast.error(getApiErrorMessage(error, "The Slack retry did not start")),
                },
              )
            }
          >
            <RotateCcw data-icon="inline-start" aria-hidden="true" />
            Retry Slack
          </button>
        ) : null}
      </div>
      {delivery.last_error ? (
        <p className="text-xs text-error">Last error: {delivery.last_error}</p>
      ) : null}
      {delivery.last_reply_error ? (
        <p className="text-xs text-warning">
          Last thread reply failed: {delivery.last_reply_error}
        </p>
      ) : null}
      <p className="text-xs text-base-content/60">
        This page is the record. Slack only points to it, so the intervention is complete whether or
        not a message was sent.
      </p>
    </div>
  );
}

export function AgentInterventionPageContent({
  sessionId,
  interventionId,
}: {
  sessionId: string;
  interventionId: string;
}) {
  const queryClient = useQueryClient();
  const { canEdit } = useProject();
  const linked = useLinkedProject();
  const projectId = linked.status === "ready" ? linked.projectId : null;
  // Keyed and sent by project, so a record of one project never shows under another.
  const { data, isLoading, isError, error } = useGetAgentIntervention(sessionId, interventionId, {
    query: {
      queryKey: [...getGetAgentInterventionQueryKey(sessionId, interventionId), projectId],
      enabled: projectId !== null,
      refetchInterval: (query) => {
        const status = query.state.data?.data.status;
        return status === "open" || status === "resume_authorized" ? 10_000 : false;
      },
    },
    request: projectId ? projectRequest(projectId) : undefined,
  });
  const intervention = data?.data;
  const refresh = () => {
    void queryClient.invalidateQueries({
      queryKey: getGetAgentInterventionQueryKey(sessionId, interventionId),
    });
    void queryClient.invalidateQueries({ queryKey: getListAgentInterventionsQueryKey(sessionId) });
    void queryClient.invalidateQueries({ queryKey: getGetAgentSessionQueryKey(sessionId) });
  };
  const back = (
    <Link
      href={`/agent-sessions/${encodeURIComponent(sessionId)}`}
      className="btn btn-square btn-ghost btn-sm shrink-0"
      aria-label="Back to the agent session"
    >
      <ArrowLeft className="h-4 w-4" aria-hidden="true" />
    </Link>
  );

  if (linked.status === "unavailable" || linked.status === "no_project") {
    return (
      <PageContainer maxWidth>
        <div className="mb-6 flex items-center gap-3">
          {back}
          <h1 className="text-xl font-medium">Agent intervention</h1>
        </div>
        <div role="alert" className="alert alert-error alert-soft">
          <span>
            {linked.status === "unavailable"
              ? `This intervention belongs to project ${linked.projectId}, which your account cannot open.`
              : "Your account has no project, so this intervention cannot be opened."}{" "}
            Ask a project owner for access.
          </span>
        </div>
      </PageContainer>
    );
  }

  if (linked.status === "pending" || isLoading) {
    return (
      <PageContainer maxWidth>
        <div className="flex flex-col gap-4" aria-busy="true">
          <div className="skeleton h-8 w-72" />
          <div className="skeleton h-24 w-full" />
          <div className="skeleton h-48 w-full" />
        </div>
      </PageContainer>
    );
  }

  if (isError || !intervention) {
    return (
      <PageContainer maxWidth>
        <div className="mb-6 flex items-center gap-3">
          {back}
          <h1 className="text-xl font-medium">Agent intervention</h1>
        </div>
        <div role="alert" className="alert alert-error alert-soft">
          <span>{getApiErrorMessage(error, "This intervention could not be loaded")}</span>
        </div>
      </PageContainer>
    );
  }

  const status = interventionStatusStyle(intervention.status);
  const action = interventionActionState(intervention);

  return (
    <PageContainer maxWidth>
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex min-w-0 items-start gap-3">
          {back}
          <div className="min-w-0">
            <h1 className="text-xl font-medium">{interventionReasonLabel(intervention.reason)}</h1>
            <p className="mt-1 text-sm text-base-content/60">
              Agent intervention on {intervention.chip_id} ·{" "}
              {formatDateTime(intervention.created_at)}
              {" · "}by {intervention.created_by}
            </p>
          </div>
        </div>
        <span className={`badge badge-soft shrink-0 ${status.badge}`}>{status.label}</span>
      </div>

      <div className="flex flex-col gap-4">
        <StatusAlert intervention={intervention} />

        <Section title="Question">
          <p className="whitespace-pre-wrap break-words">{intervention.question}</p>
          <div>
            <div className="text-xs text-base-content/60">Why the agent stopped</div>
            <p className="mt-1 whitespace-pre-wrap break-words text-sm">{intervention.summary}</p>
          </div>
        </Section>

        <Section title="Scope">
          <div className="grid gap-3 sm:grid-cols-2 md:grid-cols-4">
            <Field label="Task">{intervention.task_name ?? "-"}</Field>
            <Field label="Targets">
              <div className="flex flex-wrap gap-1">
                {intervention.qids.length > 0
                  ? intervention.qids.map((qid) => <QubitTile key={qid} qid={qid} />)
                  : "-"}
              </div>
            </Field>
            <Field label="Session">{sessionStatusLabel(intervention.session_status)}</Field>
            <Field label="Actions used">
              {intervention.actions_used} of {intervention.max_actions}
            </Field>
            <Field label="Plan node">{intervention.node_id ?? "-"}</Field>
            <Field label="Session expires">{formatDateTime(intervention.session_expires_at)}</Field>
            {intervention.plan_hash ? (
              <div className="sm:col-span-2">
                <Field label="Approved plan">
                  <span className="break-all font-mono text-xs">{intervention.plan_hash}</span>
                </Field>
              </div>
            ) : null}
          </div>
        </Section>

        <Section title="Recent attempts">
          <AttemptsTable attempts={intervention.attempts} />
        </Section>

        <Section title="Response">
          {action.kind === "answer" && canEdit ? (
            <ResponseForm intervention={intervention} onAnswered={refresh} />
          ) : null}
          {action.kind === "answer" && !canEdit ? (
            <p className="text-sm text-base-content/60">
              An editor of this project can answer. You can read the record.
            </p>
          ) : null}
          {action.kind !== "answer" ? <ResponseRecord intervention={intervention} /> : null}
        </Section>

        <Section title="Slack">
          <NotificationPanel intervention={intervention} canEdit={canEdit} onRetried={refresh} />
        </Section>

        <Section title="History">
          <ul className="flex flex-col gap-2">
            {intervention.events.map((event, index) => (
              <li key={`${event.at}-${index}`} className="text-sm">
                <span className="text-base-content/60">{formatDateTime(event.at)}</span>{" "}
                <span className="font-medium">{event.actor}</span> {event.kind.replace(/_/g, " ")}
                {event.detail ? (
                  <span className="text-base-content/60"> · {event.detail}</span>
                ) : null}
              </li>
            ))}
          </ul>
        </Section>
      </div>
    </PageContainer>
  );
}
