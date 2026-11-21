# Agent Calibration

Agent calibration lets an AI agent calibrate named qubits one measurement at a time, inside a
scope you approve once, while QDash runs each measurement, checks the result against fixed
gates, and records every step. When the agent cannot tell what to do next, it stops and asks an
expert in QDash, and it continues from QDash's records once the expert has answered. It is an
experimental single-qubit path inspired by
[Vibe Calibration](https://arxiv.org/abs/2606.22376).

You ask for it in plain words, in the QDash web **Agent** or in pi with the pi-qdash
extension; both offer the same tools and the same approvals. A fixed plan can also be run
from the command line; see [Run a fixed plan from the command line](#run-a-fixed-plan-from-the-command-line).
How this works: [Agentic Calibration](../developer-guide/copilot/agentic-calibration.md).

## Before you start

You need to be a member of the project; approving a session, its measurements, and an expert
answer needs editor permission.

- **Web Agent:** open the **Agent** as described in [AI Chat](./ai-chat.md).
- **pi:** install pi and the extension with `pi install npm:@oqtopus-team/pi-qdash`, using the
  version released with your QDash deployment. Connect it with `QDASH_BASE_URL` and
  `QDASH_API_TOKEN`, or with a profile as described in the
  [Python client](../reference/clients/python.md#connect-to-a-deployment).

To have experts notified in Slack when the agent stops, configure
[Slack notifications](./setup.md#notify-experts-of-agent-interventions-in-slack).

## Ask for a calibration

1. Ask for the goal and the qubits, for example "Calibrate Q00 on chip-001 step by step, and
   ask an expert if it gets stuck." The agent reads the qubits' current results and the task
   documentation and chooses the tasks; you do not name tasks or commands.
2. The agent proposes a session: the chip, the qubits, the tasks it may run, the range of each
   input it may change, the number of measurements, how often one task may run on one qubit,
   how long the session lasts, and that it may run them on its own. The web Agent shows it on an
   approval card; pi asks for confirmation. A non-interactive `pi -p` run cannot ask, so the
   session is created only when your request tells the agent to confirm it.
3. Approve it. The approval covers every measurement inside that scope: the agent does not ask
   again per step. It never covers a qubit, task, range, or number of measurements beyond the
   session, and saving values to the calibration asks you separately. The approval is yours:
   the agent runs steps on its own only in a session you created, not in a colleague's.
4. The agent measures, reads each result, its figures, and the task documentation, and chooses
   the next measurement. Each run appears on the **Execution** page as `agent:<task>`, inside
   the session's row. A
   measurement never writes calibration parameters; its values wait as candidates, checked
   against the session's ranges and quality limits.
5. Each measurement uses the saved calibration values, not waiting candidates. When the next
   measurement needs a value just measured, for example Rabi after a new frequency, the agent
   asks you to approve saving that value first. If you decline, it stops and reports the value
   instead of measuring on the old one.
6. When the goal is reached, the agent reports each qubit's runs and candidates and which values
   were saved. To keep more values, approve the commit it proposes.

The agent refuses, without measuring, a step outside the session, a measurement that is still
running, and an exact repeat of a finished measurement it does not justify. QDash checks the same
itself, so two requests at once never start two measurements in one session. Another session is
needed when the session expired, was stopped, or used its measurements.

## When the agent stops for an expert

When the agent cannot continue on its own, it records in QDash why, what it tried, and its
question, and QDash pauses the session: nothing new starts in it until an expert answers. A
measurement already sent to the hardware finishes on its own. The agent stops when a result has
no documented next step, when retries or the session's limits run out, when an evaluation fails
or keeps judging the fit unreliable, when QDash or the hardware reports an error, and when the
next step would leave the session. While the session waits, the agent also refuses to run a
flow or pipeline on its qubits, and it refuses them whenever QDash cannot show that none of
your sessions is waiting, for example on an older QDash release. Asking an expert never uses a measurement of the session.

With [Slack notifications](./setup.md#notify-experts-of-agent-interventions-in-slack)
configured, the agent channel gets a message linking to the request; the agent also gives you the
link. Project members can open the page; answering needs editor permission.

1. Open the link from Slack or from the agent. The link names the project, and the page loads
   only after QDash selects that project; if your account is not a member of it, or has no
   project at all, the page says so instead of opening another project. The page shows the
   reason, the question, the task and targets, and the recent attempts with links to their
   **Execution**, **Result and figures**, and **Evaluation**.
2. Under **Guidance**, write what you found. The agent reads it as information for its next
   decision; it does not change the session's qubits, tasks, ranges, number of measurements, or
   expiry.
3. Choose one:
   - **Reactivate session** makes the session active again so the agent can continue.
   - **Stop session** cancels the session for good.

A request recorded on a session that already expired, was stopped, or used all its measurements
cannot be reactivated; the button then reads **Close**. If QDash cannot tell whether a
measurement started (its request was interrupted while it was being sent), the page says so and
the session can only be stopped. The page also shows whether the Slack message was sent;
**Retry Slack** posts an unsent message again. A post that timed out after Slack accepted it
cannot be told apart from a lost one, so a retry can occasionally post a second message. Slack
messages cannot be answered or acted on from Slack. How this works:
[Human interventions](../developer-guide/copilot/agentic-calibration.md#human-interventions).

## Continue after the expert answers

Tell the agent to continue, for example "The expert answered; continue the Q00 calibration."
This works in the same chat, in a new chat, and after pi was closed and started again: the agent
reads the session, the expert's answer, and every measurement so far from QDash, and finds your
session itself when you do not give its link. It continues within the session you approved and
does not repeat a finished measurement unless the results or the guidance call for it.

To continue as soon as the expert answers, ask the agent to wait for the answer. It then waits in
the same reply for at most an hour. Closing pi, stopping the reply, or ending the chat stops the
wait, and nothing resumes the calibration until you ask again; the answer stays in QDash.

Guidance that needs something outside the session, such as another task or a wider range, leads
the agent to tell you a new session is needed; approving that session is your decision. A
stopped, expired, or used-up session is never reactivated.

## Review and export the audit

Open the session page (the agent gives its link) to review a calibration step by step. The
**Experiment audit** section lists, oldest first, the session approval, each step the agent
proposed and why, each measurement with its requested settings, fitted values, quality metrics,
and gate result, the agent's decision on each result and its next step, commits and their
previous and new values, backend applies, and every expert question and answer. Each entry is
labeled **QDash record**, **Agent statement**, **Expert statement**, or **Evaluator output**,
so you can tell what QDash recorded from what the agent or a person said. **Not recorded** marks a
fact the records do not hold, for example a decision the agent never recorded in an older
session; QDash does not fill it in. A status marked **now** is live and can still change.

The section shows 50 entries at a time, all from one reading of the records, whose time it
shows; select **Load more** until it shows **End of the timeline**. While the agent is still
working, new entries appear after you select **Refresh**. If the records change before the next
50 entries are read, the section says the audit changed and stops; select **Read again from the
start** to read it anew. Select **Export JSON** to download the whole timeline as one file for
review or analysis; the export is never shortened, and QDash refuses one too large to export.
When the file is a newer reading than the timeline on screen, the section says so. Figures and
raw data stay with each result: follow **Result and figures** to open them. Any project member
can read and export the audit; only the session's creator, through the agent, adds decisions.

The audit is kept for review. Nothing turns it into skill or task-knowledge changes by itself.
How this works: [Experiment audit](../developer-guide/copilot/agentic-calibration.md#experiment-audit).

## Follow a session on the Execution page

Open **Execution** and expand the session's row to see the runs the agent started, or select
**Open journey** for the whole session. A run's details panel and its page also link to its
session with **Open journey**. The session's own page links back with **View the measurements
on the Execution page**.

The journey page shows the session's state and how many runs, proposals, decisions, and open
questions it has, then the steps in time order, left to right:

| Step | What it shows | Selecting it |
| --- | --- | --- |
| **Measurement** | One run, with its own status; a repeat is a separate step with its try number | Opens the result and figures in the side panel; **Execution** opens the run |
| **Rejected proposal** | A step the session did not allow; it never reached hardware | Shows the reason |
| **Agent decision** | The agent's assessment of earlier results and its next step | Shows the rationale, the results it cites, and the next step, with a link to the **Audit** |
| **Expert** | A question the agent asked and the expert's answer, if any | Shows the question, answer, and guidance, with a link to the **Intervention** |

A measurement step whose run an earlier step already holds, in this or another session, or whose
records name two different runs, shows that it was started but has no run of its own. Use
**Policy and audit** for its records.

Dashed lines only show the order in which runs were started. Solid lines are links the records
hold: the results a decision cites, the step it chose, and the question it raised. A dotted line
marks a declared repeat. A step is never linked to another only because it came later. The same
steps are listed in a table below the graph. The page refreshes every five seconds. It shows at
most the latest 1000 steps and says so when it leaves earlier ones out; the audit keeps all of
them. Use **Policy and audit** for the session's limits and the full audit, and **Answer the
expert request** while the session waits.

A run a session step started shows **Agent** · @user in the list and on its page. The user is
the recorded execution user, falling back to the session creator if no execution user was
recorded, then **Unknown** if neither is available. The session group row shows the session
creator. A run someone started by hand shows only its recorded user. Expert respondents and
people who approve changes remain separate actors in the session audit.

A run tagged with a session that no step of the session started, such as one from an older
version, stays in the list as its own run without the **Agent** label; its page says it is only
tagged.
How this works: [Execution grouping](../developer-guide/copilot/agentic-calibration.md#execution-grouping).

## Run a fixed plan from the command line

The `qdash-agent` command of the Python client runs a plan you write, step by step, in a session
you create. Use it when the steps must be fixed in advance and reproducible, for example in a
script; it does not choose steps from the results beyond the optional evaluation planner.

### Install and configure

Install the Python client, then configure a named profile as described in the
[Python client](../reference/clients/python.md#connect-to-a-deployment). The command reads credentials
from that profile and never prints them. In a secret-managed environment, set the documented
`QDASH_*` variables and replace `--profile local` below with `--from-env`.

```bash
pip install qdash-client
```

Writing accepted values back to the Qubex configuration files also needs the
GitHub configuration credentials of the deployment and a parameter-to-file mapping in the
application configuration (`workflow.params_updater.parameter_file_map`).

### Create a bounded session

A session fixes the chip, qubits, allowed tasks, parameter bounds, quality gates, action budget,
expiry, skill/model identity, and hardware-reconfiguration permission. Later actions must stay
within that scope.

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

Keep the returned `session_id`. Review the whole scope before authorising a plan on
hardware. Leave out `--allow-reconfigure` when the plan must not reconfigure the device.
The action budget counts proposed measurements; checking and committing a result do not use
actions.

### Run one step

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

The run appears on the **Execution** page as `agent:<task>`, inside the session's row, so it is
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

### Run a plan

`run-plan` runs an ordered plan of steps inside one approved session. Before the first
measurement it checks the qubit, the tasks, the candidate parameters, the reconfiguration
permission, and the remaining action budget against the session. A `rollback` or
`human_escalation` stops the plan at once, and every ending other than `pass` is recorded in
QDash as an intervention that pauses the session for an expert; see
[When the agent stops for an expert](#when-the-agent-stops-for-an-expert). Add
`--no-record-intervention` to leave the session active instead.

```bash
qdash-agent --profile local run-plan \
  --session-id SESSION_ID \
  --qid Q00 \
  --source-execution-id SOURCE_EXECUTION_ID \
  --commit-on-success \
  --idempotency-prefix operator-approved-plan-001 \
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

#### Recovery branches

Nodes may carry an `id`, `on_pass`, and `on_rollback` to form a small decision graph. Without
`on_pass` the next node follows; `$complete` ends the plan successfully; without
`on_rollback` a rejected candidate stops the plan. A rejected candidate is not carried into
the recovery node.

```bash
qdash-agent --profile local run-plan \
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

#### Committing

With `--commit-on-success`, nothing is written until the plan ends in `pass`; QDash then
re-checks the latest accepted value of each parameter and saves the set in one step with one
audit record. Any other ending leaves the values uncommitted. This option cannot be combined
with per-node `commit_candidate`, `apply_backend`, or `push_to_github`; without it, a node may set
those itself (`apply_backend` needs `commit_candidate`, and `push_to_github` needs both). A
candidate set commit updates the calibration state only; applying the whole set to the backend files
is a separate operation.

The runner retries by itself only failures that happen before a measurement has started, reusing
the same request so nothing runs twice. Once a measurement exists, a timeout returns `retry` to
you rather than measuring again. The result lists every step, execution, candidate, commit,
and planner decision, and the final set of carried parameters.

#### Autonomous plan

With `--planner evaluation`, each result's AI evaluation selects the next node through the
task knowledge's `next_actions` table; see [Knowledge Layout](../developer-guide/copilot/knowledge-layout.md).
The planner can only choose nodes already in the approved plan:

| Action | Effect |
| --- | --- |
| `continue` | Follow the plan |
| `retry` | Run the same node again |
| `run_task` | Jump to the node for the named task |
| `request_human` or an unlisted status | Stop for review |

The session must grant it. Create the session with `--autonomy auto`; the policy then records
that a person approved the plan, the bounds, and the budget once, and the command refuses any
other session. `--max-rounds-per-target` (default 3) caps how often one node may run on the
target. The plan also stops for a person when the same status comes back three times, when
the fit was judged unreliable twice in a row, when an evaluation does not complete, when a
suggested range falls outside the session's override bounds, or when the node budget runs out.

```bash
qdash-agent --profile local start-session \
  --chip-id chip-001 --qid Q00 \
  --task CheckRabi --task CheckChevron \
  --allowed-overrides '{"control_amplitude":{"minimum":0.01,"maximum":0.08},"qubit_frequency":{"minimum":7.4,"maximum":7.6}}' \
  --allow-reconfigure --autonomy auto --max-rounds-per-target 3 \
  --max-actions 12 ...

qdash-agent --profile local run-plan \
  --session-id SESSION_ID --qid Q00 --planner evaluation \
  --plan '[
    {"id":"rabi","task_name":"CheckRabi","candidate_parameter":"control_amplitude","on_pass":"$complete"},
    {"id":"chevron","task_name":"CheckChevron","candidate_parameter":"qubit_frequency","on_pass":"rabi-reconfigured"},
    {"id":"rabi-reconfigured","task_name":"CheckRabi","candidate_parameter":"control_amplitude","reconfigure_before_task":true,"on_pass":"$complete"}
  ]'
```

With CheckRabi's knowledge, `SUCCESS` completes the plan and `NO_SIGNAL` runs the
`chevron` node; its accepted `qubit_frequency` is carried into `rabi-reconfigured`, which
reconfigures the hardware and measures again. Every other CheckRabi status stops for a person.
The session's round budget (`--max-rounds-per-target` at `start-session`) bounds every node
on its own, whichever rule led back to it; a node past the budget stops the plan for a person.
Without `--max-node-executions` the whole plan is bounded by the plan length times that
budget. Per-node `commit_candidate`, `apply_backend`, and `push_to_github` are refused with
`--planner evaluation`, because the planner may stop the plan after a node whose value is
already written; use `--commit-on-success`. The output adds `evaluations`: for each decision, the evaluation id, the status, the suggested
range, the fit assessment, the chosen node, and the overrides it carried, so a reviewer can
retrace the run and record a verdict on each evaluation.

Any other planner, backed by a model, is injected through the
[Python API](../reference/clients/python.md#agent-calibration); without `--planner` the command
runs the plan as written. How this works:
[Agentic Calibration](../developer-guide/copilot/agentic-calibration.md).

### Resume a stopped plan

When a plan stops, `run-plan` prints the intervention under `intervention`, and the expert
answers on its page as described in
[When the agent stops for an expert](#when-the-agent-stops-for-an-expert). For a plan, the page
offers **Authorize resume** instead of **Reactivate session**: **Resume from** offers only nodes
of that plan, each with the runs it has left; measurements already made are not repeated. The
guidance is recorded with the expert's name and printed by `resume-plan`; the plan runner does
not act on it.

After **Authorize resume**, the session stays paused until the plan's runner continues it.
QDash does not start the runner. Run the command the page shows, on the machine where the
plan ran:

```bash
qdash-agent --profile local resume-plan \
  --session-id SESSION_ID --intervention-id INTERVENTION_ID
```

The command restores the plan, its idempotency prefix, and its visit counts from QDash,
re-reads the accepted values it carries, and continues from the chosen node within the same
session scope, budget, and expiry. It prints the expert's guidance with the result, records
the result on the intervention, and records a new intervention if the resumed plan stops
again. It prints a claim key when it starts; if the run is interrupted, run it again with
`--claim-key` and that key. When the run finished but QDash could not record its result,
the command exits with status 3 and prints a second command with `--record-outcome`; run
that one, not `resume-plan` again, so nothing is measured twice. Once the result is
recorded, `resume-plan` with the same claim key only prints it.

A resume is refused, with the reason on the page, when the session expired, used all its
actions, or still has a measurement, a calibration commit, or a backend apply in progress, or
when the plan used its node executions or the chosen node its runs. Expiry, the budget, and the
visit counts carry over to the resumed run: QDash counts each node's runs from its own records,
so a session accepts only the plan it first stopped with, and an expired or exhausted session
needs a newly authorized session. A plan stop has no plan to resume when QDash cannot confirm
the plan's progress from its own records, for example because steps were also run by hand or
by an agent in the same session. Its summary then ends with "QDash rejected the plan
checkpoint, so this intervention cannot resume the plan.", the output shows the reason under
`checkpoint_rejection`, and the button reads **Reactivate session**; to run the plan again,
start a newly authorized session.

## Before the first run on hardware

Backend verification proves that the Qubex configuration files match the committed value; the
next step builds the backend from those files, connects to the hardware, and reconfigures it only
when the session allows. Run a single-qubit canary under supervision first, and confirm the
chip, qubit, task, source execution, bounds, quality gates, action budget, reconfiguration
permission, commit behaviour, and Git branch before starting it. Unattended multi-qubit
calibration is not supported, by the agent or by plans.
