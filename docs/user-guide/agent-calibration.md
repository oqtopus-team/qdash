# Agent Calibration

Agent calibration runs one measurement at a time within a scope you approve. QDash records the
steps, checks candidate values, and pauses for expert help when needed. This is an experimental
single-qubit workflow.

## Before you start

Use the web **Agent**, or pi with `pi install npm:@oqtopus-team/pi-qdash` and a
[client profile](../reference/clients/python.md#connect-to-a-deployment). Match the extension to
your deployment. Approvals and expert answers require project edit permission.

## Ask for a calibration

1. State the goal, chip, and qubit: “Calibrate Q00 on chip-001 step by step; ask an expert if stuck.”
2. Review the proposed session: targets, allowed tasks, measurement budget, retry limit, expiry,
   evaluation policy, and **Parameter updates**.
3. Approve the scope. The agent can then measure within it without asking for every step.
4. Follow the results and review the final report of measured candidates and saved values.

Parameter-update grants allow the agent to save only named values after a passing assessment
and task checks. Without a grant, saving requires separate approval. Measurements themselves
never write calibration values. Ungranted outputs are reference-only, not failed measurements.

Each measurement uses saved calibration values. If the next task needs a candidate, the agent
must commit it first; declining that commit stops the sequence. Failed or uncertain results
pause for an expert. The assistant cannot set numeric bounds for you; use the CLI below when
you need them. New targets, tasks, or exhausted budgets require a new session.

## When the agent stops for an expert

Open the intervention link from the agent or configured [Slack notifications](./setup.md#notify-experts-of-agent-interventions-in-slack).
Review the attempts and evidence, enter **Guidance**, then choose **Reactivate session** or
**Stop session**. Guidance does not expand the approved scope.

No new step starts while paused; an already dispatched measurement may finish. Expired,
exhausted, or stopped sessions cannot reactivate. An unknown measurement-start outcome must be
investigated; the session can only be stopped. Slack links open QDash; replies in Slack do not
answer the intervention.

## Continue after the expert answers

Ask the agent to continue, in the same chat or a new one. It reads the saved session and guidance.
An expert answer or page reload does not start the agent automatically. **Continue session**
sends the continuation request; an active session alone does not mean the agent is working.

You can ask the agent to wait for the expert, for at most an hour. Stopping that answer ends the
wait, so ask again afterward.

## Stop a session

Open the session and select **Stop session**, give a reason, and confirm. This permanently blocks
new measurements, commits, and backend applies. It does not cancel a measurement already sent
to hardware; that result is recorded but cannot be committed from the stopped session.

## Review and export the audit

Open **Experiment audit** on the session page. It distinguishes **QDash record**, **Agent
statement**, **Expert statement**, and **Evaluator output**. Missing evidence is **Not recorded**;
reported model identity is not verified by QDash.

Use **Refresh** for new entries, **Load more** for older entries, and **Export JSON** for the
whole audit. Follow result links for figures and raw data. The audit does not automatically
change task knowledge or skills.

## Follow a session on the Execution page

Expand its row on **Execution**, or select **Open session graph**. The graph shows measurements,
rejected proposals, decisions, and expert requests. Dashed lines show start order, solid lines
recorded relationships, and dotted lines declared repeats. Use **Policy and audit** for the
complete history and approved limits.

## Run a fixed plan from the command line

Use `qdash-agent` when you want an explicit plan rather than chat-selected steps.

### Install and configure

Install `qdash-client` and configure a [profile](../reference/clients/python.md#connect-to-a-deployment).
Commands below use `local`; replace it with your profile. For environment-managed credentials,
use `--from-env` instead.

### Create a bounded session

Choose bounds and quality gates appropriate to your task; the numbers below are examples,
not recommended hardware limits.

```bash
qdash-agent --profile local start-session \
  --chip-id chip-001 --qid Q00 --task CheckT1 \
  --allowed-overrides '{"t1":{"minimum":1,"maximum":500}}' \
  --task-quality-gates '{"CheckT1":{"r2":{"minimum":0.9}}}' \
  --max-actions 20
```

Keep the returned `session_id`. The scope cannot change. Quality gates currently use task fit
`r2`; output-value bounds belong in `--allowed-overrides`. `--evaluation required` adds a
supporting evaluator requirement for commits; the default is `off`. Add `--allow-reconfigure`
only when hardware reconfiguration is authorized.

### Run one step

```bash
qdash-agent --profile local run-step \
  --session-id SESSION_ID --task CheckT1 --qid Q00 \
  --candidate-parameter t1
```

This measures and checks a candidate without saving it. Additional options:

| Option | Effect |
| --- | --- |
| `--source-execution-id` | Record decision provenance; does not restore old inputs |
| `--reconfigure-before-task` | Apply configuration before measuring, if the session permits |
| `--commit` | Save an accepted candidate |
| `--apply-backend` | Apply a committed value and verify mapped backend files |
| `--github-push` | Version the changed backend files |

Backend writes need the deployment's parameter-file mappings and configuration credentials.
File verification does not prove the hardware has loaded the value.

### Run a plan

The plan must fit the session's targets, tasks, bounds, and remaining budget:

```bash
qdash-agent --profile local run-plan \
  --session-id SESSION_ID --qid Q00 \
  --commit-on-success --idempotency-prefix approved-t1-plan-001 \
  --plan '[{"task_name":"CheckT1","candidate_parameter":"t1"}]'
```

| Transition | Next action |
| --- | --- |
| `pass` | Requested stages succeeded |
| `retry` | Check the existing measurement; do not blindly launch another |
| `rollback` | Candidate failed bounds or gates |
| `human_escalation` | Inspect policy, persistence, or backend failure before continuing |

Non-pass plan endings normally record an intervention and pause the session.
`--no-record-intervention` leaves it active instead. Accepted values carry to later nodes;
explicit overrides take priority and must fit session bounds.

#### Recovery branches

Nodes can use `id`, `on_pass`, and `on_rollback`; `$complete` ends successfully. Without
`on_pass`, the next node runs; without `on_rollback`, rejection stops the plan. Use
`--max-node-executions` to bound all visits, including loops, within the session budget.

#### Committing

`--commit-on-success` saves the final accepted parameter set only after the whole plan passes.
It cannot combine with per-node commit, apply, or push options. Backend application of the
whole set is separate. A timeout after a measurement starts returns `retry`, not a new run.

#### Autonomous plan

Create a session with `--autonomy auto` and run the plan with `--planner evaluation` to select
among its approved nodes using task knowledge. Unknown statuses, unreliable evaluations,
out-of-bounds suggestions, or exhausted budgets stop for review. Use `--commit-on-success`;
per-node writes are refused. See [Agentic Calibration](../developer-guide/agent/agentic-calibration.md).

### Resume a stopped plan

An expert selects **Authorize resume** and a permitted node on the intervention page. Then run
its displayed command on the original runner's machine:

```bash
qdash-agent --profile local resume-plan \
  --session-id SESSION_ID --intervention-id INTERVENTION_ID
```

The original scope, expiry, budget, and visit counts still apply. Guidance is printed for the
operator, not interpreted by the runner. If interrupted, reuse the printed `--claim-key`.
If the command exits with status 3, run its printed `--record-outcome` command instead of
restarting the measurement. A rejected checkpoint requires a newly authorized session.

## Before the first run on hardware

Run one supervised single-qubit canary. Confirm the target, tasks, bounds, gates, budget,
reconfiguration permission, commit policy, and configuration branch. Unattended multi-qubit
calibration is not supported.
