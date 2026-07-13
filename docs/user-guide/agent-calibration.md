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

The result includes a Prefect `operation_id` and, after QDash creates its execution record, a separate QDash `execution_id`; the runner resolves and polls both. Task measurement always uses `update_params=false`. QDash derives the candidate from the authoritative task result and currently normalizes R² as `r2`; a missing required metric rejects the candidate. `--commit` writes only the accepted value to QDash state. `--apply-backend` then instructs a worker to re-read that committed snapshot, pull the latest config, atomically update mapped Qubex YAML files, read them back, and push only the target files. The response records the base and resulting Git versions.

Use `--no-github-push` only for fake-backend or explicitly non-versioned tests. It still verifies local mapped files but does not provide durable configuration provenance.

The CLI emits one typed transition:

- `pass`: all requested stages passed; when backend apply was requested, `backend_verified` is true.
- `retry`: dispatch or polling did not reach a terminal result within the configured budget.
- `rollback`: deterministic parameter or quality gates rejected the candidate.
- `human_escalation`: policy, persistence, backend verification, or versioning failed and requires inspection.

An AI agent must branch only on this transition and must never substitute its own numeric candidate.

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
