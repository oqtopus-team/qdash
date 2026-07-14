# Agent calibration

QDash agent calibration lets a user-operated AI agent run bounded calibration steps while QDash owns execution, deterministic gates, backend application, provenance, and audit records.

This experimental single-qubit path is inspired by [Vibe Calibration](https://arxiv.org/abs/2606.22376). It completes one Skill node at a time and requires operator-approved session scope before hardware operations.

## Install and configure

Install the client from a release or local checkout.

~~~bash
pip install qdash-client
~~~

For local development:

~~~bash
uv tool install ./src/qdash/client
~~~

Configure a named QDash profile as described in the [QDash Client guide](./qdash-client.md). The CLI reads credentials from that profile and does not print them. In a secret-managed environment, set the documented `QDASH_*` variables and replace `--profile local` below with `--from-env`. Agent instructions are distributed separately from [oqtopus-team/skills](https://github.com/oqtopus-team/skills).

Agent endpoints are available to authenticated project members, mutations require editor permission, and workers register the required system deployments at startup. Versioned backend application also requires the existing GitHub configuration credentials and a parameter-to-YAML mapping in `workflow.params_updater.parameter_file_map`.

## Create a bounded session

The session fixes the chip, qubits, tasks, parameter bounds, result-quality gates, action budget, expiry, Skill identity, model identity, and whether an agent may explicitly reconfigure hardware. The action budget counts proposed operations; gate evaluation and commit do not consume additional actions.

~~~bash
qdash-agent --profile local start-session \
  --chip-id chip-001 \
  --qid Q00 \
  --task CheckT1 \
  --allowed-overrides '{"t1":{"minimum":1,"maximum":500}}' \
  --quality-gates '{"r2":{"minimum":0.9}}' \
  --max-actions 20 \
  --allow-reconfigure \
  --skill-name qdash-agent-calibrator \
  --skill-version 1 \
  --skill-hash sha256:replace-with-skill-hash \
  --model-name local-agent-model
~~~

Keep the returned `session_id`. Review the complete scope before authorizing a hardware campaign. Omit `--allow-reconfigure` when the campaign must not run an implicit `Configure` task.

## Run and apply one Skill node

A node performs authorization, staged execution, polling, authoritative candidate extraction, deterministic parameter and quality gates, audited QDash commit, worker-side YAML application, read-back verification, and optional GitHub versioning.

~~~bash
qdash-agent --profile local run-step \
  --session-id SESSION_ID \
  --task CheckT1 \
  --qid Q00 \
  --source-execution-id SOURCE_EXECUTION_ID \
  --candidate-parameter t1 \
  --reconfigure-before-task \
  --commit \
  --apply-backend
~~~

The result includes a Prefect `operation_id` and, after QDash creates its execution record, a separate QDash `execution_id`; the runner resolves and polls both. In QDash, the execution is named `agent:<task>` and tagged `agent-session:<session_id>` so it can be distinguished from a manual `re-execute:<task>` run. Task measurement always uses `update_params=false`. QDash derives the candidate from the authoritative task result and currently normalizes R² as `r2`; a missing required metric rejects the candidate. `--commit` writes only the accepted value to QDash state. `--apply-backend` then instructs a worker to re-read that committed snapshot, pull the latest config, atomically update mapped Qubex YAML files, read them back, and push only the target files. The response records the base and resulting Git versions.

Use `--github-push` when changed backend files must also be versioned in GitHub.

The CLI emits one typed transition:

- `pass`: all requested stages passed; when backend apply was requested, `backend_verified` is true.
- `retry`: dispatch or polling did not reach a terminal result within the configured budget.
- `rollback`: deterministic parameter or quality gates rejected the candidate.
- `human_escalation`: policy, persistence, backend verification, or versioning failed and requires inspection.

An AI agent must branch only on this transition and must never substitute its own numeric candidate.

## Run an autonomous single-qubit campaign

`run-campaign` advances an ordered, declarative plan inside one previously approved session. It
preflights the qid, tasks, candidate parameters, reconfiguration permission, and remaining action
budget before the first hardware operation. A rollback or human escalation stops the campaign
immediately.

~~~bash
qdash-agent --profile local run-campaign \
  --session-id SESSION_ID \
  --qid Q00 \
  --source-execution-id SOURCE_EXECUTION_ID \
  --commit-on-success \
  --idempotency-prefix operator-approved-campaign-001 \
  --plan '[
    {"task_name":"CheckRabi","candidate_parameter":"control_amplitude"},
    {"task_name":"CreateHPIPulse","candidate_parameter":"hpi_amplitude"},
    {"task_name":"CheckT1","candidate_parameter":"t1"}
  ]'
~~~

The campaign keeps the approved source execution fixed so every node retains its complete task
snapshot. After a node passes, its authoritative candidate is carried into later nodes as an input
parameter override. An explicit `parameter_overrides` value on a later node takes precedence over a
carried value. Every override is checked against the immutable session bounds before dispatch.

Nodes may define `id`, `on_pass`, and `on_rollback` to form a bounded decision graph. An omitted
`on_pass` advances to the next array item, `$complete` ends successfully, and an omitted
`on_rollback` stops with `rollback`. A rollback transition means that QDash rejected the measured
candidate; it does not carry that candidate into the recovery node.

~~~bash
qdash-agent --profile local run-campaign \
  --session-id SESSION_ID \
  --qid Q00 \
  --source-execution-id SOURCE_EXECUTION_ID \
  --max-node-executions 3 \
  --plan '[
    {
      "id":"calibrate-rabi",
      "task_name":"CheckRabi",
      "candidate_parameter":"control_amplitude",
      "on_pass":"$complete",
      "on_rollback":"recover-rabi"
    },
    {
      "id":"recover-rabi",
      "task_name":"CheckRabi",
      "candidate_parameter":"control_amplitude",
      "parameter_overrides":{"control_amplitude":0.084},
      "on_pass":"$complete",
      "on_rollback":"calibrate-rabi"
    }
  ]'
~~~

`--max-node-executions` bounds all graph visits, including loops, and must fit within the session's
remaining action budget before dispatch. If the graph does not finish within the bound, the runner
returns `human_escalation`. The output `node_path` records every visited node. Revisited nodes use a
new deterministic idempotency key while transport retries before dispatch reuse the same key.

With `--commit-on-success`, every node remains staged until the campaign reaches a final `pass`.
QDash then re-resolves and revalidates the latest accepted candidate for each parameter before
persisting the same-qid set with one Qubit save and one audit record. A rollback, retry, human
escalation, or exhausted execution bound leaves the staged candidates uncommitted.

Campaign finalization cannot be combined with per-node `commit_candidate`, `apply_backend`, or
`push_to_github`. Without `--commit-on-success`, a node may explicitly set those fields to `true`;
`apply_backend` requires `commit_candidate`, and `push_to_github` requires both. Campaign
finalization currently updates QDash state only. Applying the complete candidate set to backend
files remains a separate operation. Hardware reconfiguration remains opt-in per node through
`reconfigure_before_task` and must also be authorized by the session.

The runner automatically retries only failures that occur before QDash returns a Prefect operation
or QDash execution ID. It reuses the same action idempotency key during that recovery. Once a
hardware operation exists, a timeout returns `retry` to the operator instead of autonomously
dispatching another measurement.

The session action budget must cover every plan node. Recovery with the same idempotency key does
not consume another action. The result contains every attempted step, execution ID, candidate,
commit, planner decision, and the final carried parameter set.

## Python API

~~~python
from qdash.client import (
    AgentCalibrationRunner,
    AgentCampaignNode,
    AgentCampaignRunner,
    AgentPlannerDecision,
    QDashClient,
)


class CoherencePlanner:
    def choose_next(self, observation):
        if observation.last_outcome.transition.value == "rollback":
            return AgentPlannerDecision("recover-rabi", "use the approved recovery node")
        return AgentPlannerDecision("$complete", "deterministic gates accepted the candidate")


client = QDashClient.from_profile("local")
try:
    outcome = AgentCalibrationRunner(client).run_step(
        session_id="SESSION_ID",
        task_name="CheckT1",
        qid="Q00",
        source_execution_id="SOURCE_EXECUTION_ID",
        candidate_parameter="t1",
        reconfigure_before_task=True,
        commit_candidate=True,
        apply_backend=True,
        push_to_github=True,
    )
    print(outcome.transition, outcome.reason, outcome.commit)

    approved_nodes = [
        AgentCampaignNode(
            node_id="calibrate-rabi",
            task_name="CheckRabi",
            candidate_parameter="control_amplitude",
        ),
        AgentCampaignNode(
            node_id="recover-rabi",
            task_name="CheckRabi",
            candidate_parameter="control_amplitude",
            parameter_overrides={"control_amplitude": 0.084},
        ),
    ]
    campaign = AgentCampaignRunner(client).run_campaign(
        session_id="SESSION_ID",
        qid="Q00",
        source_execution_id="SOURCE_EXECUTION_ID",
        nodes=approved_nodes,
        max_node_executions=3,
        planner=CoherencePlanner(),
        commit_on_success=True,
    )
    print(campaign.transition, campaign.planner_decisions, campaign.campaign_commit)
finally:
    client.close()
~~~

The planner receives only bounded campaign observations and may select an ID already present in
`approved_nodes` or `$complete`. Runner validation rejects unknown IDs, prevents completion after
rollback, and enforces the preflighted node-execution limit. Planner exceptions and invalid
decisions end in `human_escalation`. The CLI executes the declarative graph; inject a model-backed
planner through the Python API when dynamic next-action selection is required.

## Hardware boundary

Backend verification proves that the worker's mapped Qubex YAML values match the gated commit. The next calibration step creates a Qubex backend from those files, connects to hardware, and may run `Configure` only when the session granted it.

Before the first real-device campaign, run a single-qid canary under operator supervision. Confirm the chip, qid, task, source execution, bounds, quality gates, action budget, reconfiguration permission, commit behavior, and Git branch before triggering it. A multi-qubit unattended campaign still requires declarative campaign transitions, topology-safe scheduling, and hardware canary evidence.
