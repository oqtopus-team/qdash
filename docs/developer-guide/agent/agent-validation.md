# Agent Loop Validation

The opt-in fake-loop harness tests a real chat model with production pi-qdash tools against a
local QDash fake backend. It is not a CI test or a hardware validation.

## Scenarios

| Scenario | Checks |
| --- | --- |
| `stored-t1` | Reads stored T1 without measuring |
| `t1-rerun` | Measures only the requested T1 task |
| `dependent-commit` | Commits an accepted frequency before the dependent Rabi task |
| `purpose-pipeline` | Records an objective, pipeline, execution links, and reported origin |
| `stored-plan-pipeline` | Runs a validated stored plan by `planId` in an objective; the run records its plan and review digest |
| `unknown-failure` | Pauses on a fault, then repeats only after expert response and continuation |

The harness supplies user approvals and expert answers; the model chooses calibration actions.
Verdicts use QDash records and harness observations. Model claims never pass a test on their own.

## What keeps a run bounded

Preflight requires a loopback API, a chip named `agentval-<name>`, an existing qubit below 64,
editor credentials, required API capabilities, and a verified fake dispatch backend and task
catalog. Failure blocks the run before writes.

Approvals permit only the scenario's targets, tasks, budget, expiry, and update authority.
For a run of a stored plan, the harness reads the plan from QDash and approves it only when the
dialog shows that plan and review digest; `stored-plan-pipeline` declines a raw spec.
Shell/edit/write tools are excluded. The harness caps tool calls and turn time and redacts
credentials from reports. It does not cancel unrelated sessions.

## Run it

Follow [Fake backend setup](../../user-guide/setup/fake-backend.md) for a local deployment of this
revision and [AI Setup](../../user-guide/setup/ai.md) for the chat model. Install workspace
dependencies with `bun install --frozen-lockfile` from the repository root. The pipeline scenarios
need the worker's `calibration-pipeline` deployment. The fault scenario needs
`QDASH_FAKE_FAULT_INJECTION=1` on the worker and `SLACK_AGENT_NOTIFICATION` unset or false.

Set `QDASH_API_TOKEN` and `QDASH_PROJECT_ID` from the local editor's
[API token settings](../../reference/clients/python.md#connect-to-a-deployment), then run:

```bash
export QDASH_BASE_URL=http://127.0.0.1:5714/api
task validate-agent-fake-loop -- --chip-id agentval-loop --qid 4 --create-chip --setup \
  --config-path ./config/qubex-config
```

The URL above uses the default browser port; replace `5714` if `UI_PORT` differs.
`--config-path` must be the host path of the deployment's configuration. `--env-file` selects
another model environment file; `--scenario` selects scenarios; `--model provider/id` selects a
configured chat model. Exit codes: 0 passed, 1 failed, 2 blocked or not run.

## The report

Reports and session audit/graph exports go to `.tmp/agent-fake-loop/<run id>/`, or `--out`.
They record model and code identity, approvals, limits, evidence, and expected/actual checks.

A pass establishes these fake-backend mechanics only. It does not validate hardware behavior,
scientific accuracy, Slack delivery, web presentation, or whether a reported tool origin is true.

## Change and test it

Add fixtures in `agent-runtime/validation/fake-loop/scenarios.ts`, checks in `evaluate.ts`, and
approval rules in `approval.ts`. Keep tasks inside the fake catalog and judge authoritative
records, including failed or missing records.

Run `task ci-agent-runtime`; `fake-loop-validation.test.mjs` and
`fake-loop-calibration.test.mjs` cover the harness without a model or deployment.
