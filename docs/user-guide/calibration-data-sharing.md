# Calibration Data Sharing

Use the same QDash project to continue calibration work with teammates without copying the latest
chip state between user accounts.

## Confirm the Sharing Boundary

The active project is the access and data boundary. Members of one project share the current
calibration state for each chip, while every execution and result keeps the user who produced it.

Two projects can use the same chip ID without sharing calibration values, execution history,
artifacts, notes, or discussions.

## Hand Work to a Teammate

1. Confirm the intended project in the project selector.
2. Confirm that the teammate is a member of that project with the required role.
3. Open **Task Results** and share the result link or start a forum thread from the result.
4. Tell the teammate which chip, execution, target, and result to continue from.
5. The teammate confirms the same project and chip before starting the next task or workflow.

When a run saves calibrated outputs, later tasks in the same project read those values as current
state. Earlier executions and their artifacts remain available in history.

## Share Without Changing Current State

Leave **Save calibrated outputs to DB** off when a run is exploratory. Other project members can
still inspect its result and artifacts, but later tasks do not use its outputs as current
calibration values.

Use a result note for measurement-specific context. Use a forum thread when the finding needs
discussion or follow-up.

## Switch Projects Safely

Switching the active project changes the visible chips, current parameters, classifiers,
executions, workflows, and discussions. Confirm the project after switching even when both
projects contain a chip with the same ID.

QDash does not provide a normal UI action to move calibration state between projects. Establish or
import the state in the intended project instead.

For membership and role changes, see [Projects and Data Sharing](./projects-and-data-sharing.md).
