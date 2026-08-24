# Reviewing and Sharing Results

QDash connects task results, notes, issues, discussions, knowledge, notifications, and AI reviews
inside the active project.

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

## Use AI Reviews

AI review requests analyze the task results selected from chip views. A review run groups the
request, while its target records contain the individual findings and referenced files. Open **AI
Reviews** to filter runs by chip or task and drill into a run.

AI output is supporting evidence, not an automatic calibration decision. Confirm findings against
the task result, raw artifacts, task knowledge, and current calibration context before changing
parameters or excluding data.

## Follow Notifications

Mentions, replies, and system events appear in **Inbox**. The unread badge in the sidebar reflects
items that still need attention. Opening the linked record provides the project and result context;
mark notifications read after reviewing the underlying event.

## Share Calibration Data

Project membership is the access boundary for shared calibration records. Before sending a link,
confirm that the recipient belongs to the project and has the required role. For storage scope,
artifact paths, and upgrade behavior, see [Calibration Data Sharing](./calibration-data-sharing.md).
