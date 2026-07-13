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

A QDash operator must set `ENABLE_AGENT_CALIBRATION=true` for both the API and worker environment, then restart them. With the default `false`, Agent endpoints remain visible in the API contract but return HTTP 503, and the Agent-only `system-candidate-apply` deployment is not registered. The existing `system-single-task` deployment remains enabled in either mode. Versioned backend application also requires the existing GitHub configuration credentials and a parameter-to-YAML mapping in `workflow.params_updater.parameter_file_map`.

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

The example leaves all candidates staged. A node may explicitly set `commit_candidate`,
`apply_backend`, and `push_to_github` to `true`; `apply_backend` requires `commit_candidate`, and
`push_to_github` requires both. Hardware reconfiguration remains opt-in per node through
`reconfigure_before_task` and must also be authorized by the session.

The runner automatically retries only failures that occur before QDash returns a Prefect operation
or QDash execution ID. It reuses the same action idempotency key during that recovery. Once a
hardware operation exists, a timeout returns `retry` to the operator instead of autonomously
dispatching another measurement.

The session action budget must cover every plan node. Recovery with the same idempotency key does
not consume another action. The result contains every attempted step, execution ID, candidate,
commit, and the final carried parameter set.

## Python API

~~~python
from qdash.client import AgentCalibrationRunner, QDashClient

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
finally:
    client.close()
~~~

## Hardware boundary

Backend verification proves that the worker's mapped Qubex YAML values match the gated commit. The next calibration step creates a Qubex backend from those files, connects to hardware, and may run `Configure` only when the session granted it.

Before the first real-device campaign, run a single-qid canary under operator supervision. Confirm the chip, qid, task, source execution, bounds, quality gates, action budget, reconfiguration permission, commit behavior, and Git branch before triggering it. A multi-qubit unattended campaign still requires declarative campaign transitions, topology-safe scheduling, and hardware canary evidence.
