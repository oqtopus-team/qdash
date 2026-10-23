# Agent Calibration

Agent calibration lets an AI agent you operate run calibration steps one at a time, inside a
scope you approve first, while QDash executes the measurements, checks the results against
fixed gates, and records every decision. It is an experimental single-qubit path inspired by
[Vibe Calibration](https://arxiv.org/abs/2606.22376).

You drive it from the `qdash-agent` command of the Python client. How this works:
[Agent platform](../developer-guide/copilot/agent-platform.md).

## Install and configure

Install the client, then configure a named profile as described in the
[Python client](../reference/clients/python.md#configuration). The command reads credentials
from that profile and never prints them. In a secret-managed environment, set the documented
`QDASH_*` variables and replace `--profile local` below with `--from-env`.

```bash
pip install qdash-client
```

Agent instructions (skills) are distributed separately from
[oqtopus-team/skills](https://github.com/oqtopus-team/skills).

You need to be a member of the project; creating sessions and running steps needs editor
permission. Writing accepted values back to the Qubex configuration files also needs the
GitHub configuration credentials of the deployment and a parameter-to-file mapping in the
application configuration (`workflow.params_updater.parameter_file_map`).

## Create a bounded session

A session fixes everything the agent may touch: the chip, the qubits, the tasks, the bounds a
proposed parameter must fall in, the quality a result must reach, how many actions the agent
may propose, when the grant expires, which skill and model are acting, and whether the agent may
reconfigure hardware. Nothing outside the session is accepted later.

```bash
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
```

Keep the returned `session_id`. Review the whole scope before authorising a campaign on
hardware. Leave out `--allow-reconfigure` when the campaign must not reconfigure the device.
The action budget counts proposed measurements; checking and committing a result do not use
actions.

## Run one step

One step runs a task, extracts the candidate value from the result, checks it against the
session's bounds and quality gates, and, when asked, commits it to QDash and applies it to the
backend configuration files.

```bash
qdash-agent --profile local run-step \
  --session-id SESSION_ID \
  --task CheckT1 \
  --qid Q00 \
  --source-execution-id SOURCE_EXECUTION_ID \
  --candidate-parameter t1 \
  --reconfigure-before-task \
  --commit \
  --apply-backend
```

| Option | Effect |
| --- | --- |
| `--source-execution-id` | Records which execution the step was decided from. The step does not restore that execution's state; it measures from the current calibration state, the way the Task Workbench does. |
| `--candidate-parameter` | The output parameter to extract and judge. A result that lacks a required quality metric is rejected. |
| `--reconfigure-before-task` | Reconfigure the hardware before measuring. Only accepted when the session allows it. |
| `--commit` | Write the accepted value to the calibration state. Nothing is written without it. |
| `--apply-backend` | After the commit, have a worker update the mapped Qubex configuration files from the committed value, read them back, and push the changed files. The response records the configuration versions before and after. |
| `--github-push` | Also version the changed files in GitHub. |

The run appears on the **Execution** page as `agent:<task>`, tagged with the session, so it is
told apart from a workbench quick run or a manual re-execution. The measurement itself never
writes parameters; only the gated commit does.

The command ends with one of four transitions. An agent must branch on this transition and
never substitute a number of its own.

| Transition | Meaning |
| --- | --- |
| `pass` | Every requested stage passed. With `--apply-backend`, the files were verified too. |
| `retry` | The measurement did not reach a result within the time budget. |
| `rollback` | The bounds or quality gates rejected the candidate. |
| `human_escalation` | Policy, persistence, backend verification, or versioning failed. Inspect before continuing. |

## Run a campaign

`run-campaign` runs an ordered plan of steps inside one approved session. Before the first
measurement it checks the qubit, the tasks, the candidate parameters, the reconfiguration
permission, and the remaining action budget against the session. A `rollback` or
`human_escalation` stops the campaign at once.

```bash
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
```

Each node measures from the current calibration state, so a value committed by an earlier node
feeds the later ones. A value a node accepted is also carried into later nodes as an input, even
when it was not committed; an explicit `parameter_overrides` on a node wins over a carried
value, and every override is checked against the session bounds first.

### Recovery branches

Nodes may carry an `id`, `on_pass`, and `on_rollback` to form a small decision graph. Without
`on_pass` the next node follows; `$complete` ends the campaign successfully; without
`on_rollback` a rejected candidate stops the campaign. A rejected candidate is not carried into
the recovery node.

```bash
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
```

`--max-node-executions` bounds every visit, loops included, and must fit in the session's
remaining action budget. A graph that does not finish within the bound ends in
`human_escalation`. The output's `node_path` lists every node visited.

### Committing

With `--commit-on-success`, nothing is written until the campaign ends in `pass`; QDash then
re-checks the latest accepted value of each parameter and saves the set in one step with one
audit record. Any other ending leaves the values uncommitted. This option cannot be combined
with per-node `commit_candidate`, `apply_backend`, or `push_to_github`; without it, a node may set
those itself (`apply_backend` needs `commit_candidate`, and `push_to_github` needs both). A
campaign commit updates the calibration state only; applying the whole set to the backend files
is a separate operation.

The runner retries by itself only failures that happen before a measurement has started, reusing
the same request so nothing runs twice. Once a measurement exists, a timeout returns `retry` to
you rather than measuring again. The result lists every step, execution, candidate, commit,
and planner decision, and the final set of carried parameters.

A planner that chooses the next node at run time, backed by a model, is injected through the
[Python API](../reference/clients/python.md#agent-calibration); the command runs the plan as
written.

## Before the first run on hardware

Backend verification proves that the Qubex configuration files match the committed value; the
next step builds the backend from those files, connects to the hardware, and reconfigures it only
when the session allows. Run a single-qubit canary under supervision first, and confirm the
chip, qubit, task, source execution, bounds, quality gates, action budget, reconfiguration
permission, commit behaviour, and Git branch before starting it. Unattended multi-qubit
campaigns are not supported.
