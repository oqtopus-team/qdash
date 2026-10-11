# Reviewing and Sharing Results

QDash connects task results, notes, issues, discussions, knowledge, and notifications inside the
active project.

## Record Result Context

Add a task-result note when the context applies to one measurement, such as an anomaly or the
reason for a parameter choice. Add a pinned chip, qubit, or coupling summary when the context
should remain visible for the selected cool-down or dashboard time range.

The dashboard notes summary gathers the current scoped notes and links back to their targets or
task results. See [Dashboard](./dashboard.md) for note scopes and fallback behavior.

## Track a Problem

Create an issue from a task result when a finding needs discussion or follow-up. The issue retains
the task-result context, including the execution, target, parameters, and output used during the
investigation. Participants can reply, mention other members, close the issue, and reopen it when
work resumes.

Use **Issues** to filter and review these result-specific discussions. Use **Forum** for broader
project topics such as control-stack behavior, system policy, or work spanning multiple results.

## Reuse Knowledge

Resolved investigations can be represented as issue-derived knowledge cases. **Knowledge** lets
users browse those cases by calibration task. **Task Knowledge** contains the maintained baseline
for each task: its physics, expected result, failure patterns, and analysis guidance.

These sources have different roles:

| Source | Scope | Best use |
| --- | --- | --- |
| Task Knowledge | Maintained task-level guidance | Understand expected behavior before analysis. |
| Issue Knowledge | Curated cases from investigations | Compare a result with known failure cases. |
| Issue | One task result and its discussion | Coordinate diagnosis and follow-up. |
| Forum | Project-wide topic | Discuss work not anchored to one result. |

## Request an AI Evaluation

The calibration evaluation model can judge the figure of a task result against the task's
maintained reference. Two entry points lead to the same record:

- **Chip page → Evaluate** evaluates the latest result of the selected task for every qubit or
  coupling of the chip (or the results of the selected day) as one run.
- **Task result → AI evaluation → Evaluate** evaluates that one result as a run of one.

Choose how to evaluate. **Direct** runs the evidence and evaluation tools as such, so the same
reference reaches the model every time. **Planner** lets the chat planner summarise the result and
call the evaluation itself, as Ask AI does, and records what it did and answered. An optional
question is passed to the evaluation model on top of the standard diagnosis.

Open **AI Evaluations** to follow a run and read each evaluation: the diagnosis (fit quality,
success, extracted parameters), which model and extension version judged, the exact text the model
saw, and, in planner mode, the planner's tools and answer. Mark each evaluation **Agree** or
**Disagree**, with a note when useful; the run's agreement rate is the ground truth for comparing
runs made with different extension versions, models or task references. The task result page lists
every evaluation of that result across runs.

## Ask Copilot

AI output is supporting evidence, not an automatic calibration decision. Confirm findings against
the task result, raw artifacts, task knowledge, and current calibration context before changing
parameters or excluding data. See [Copilot](./copilot.md) for the chat and analysis workflows.

## Follow Notifications

Mentions, replies, and system events appear in **Inbox**. The unread badge in the sidebar reflects
items that still need attention. Opening the linked record provides the project and result context;
mark notifications read after reviewing the underlying event.

## Share Calibration Data

Project membership is the access boundary for shared calibration records. Before sending a link,
confirm that the recipient belongs to the project and has the required role. For storage scope,
artifact paths, and upgrade behavior, see [Calibration Data Sharing](./calibration-data-sharing.md).
