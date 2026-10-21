# Reviewing and Sharing Results

Use **Task Results** to find one measurement, inspect its evidence, record context, and involve the
project when follow-up is needed.

## Find a Result

1. Open **Task Results**.
2. Filter by chip, execution, task, target, or status.
3. Select a row to preview its figure, message, and parameters.
4. Open the full result when you need artifacts, history, notes, discussion, or re-execution.

Start from **Execution** instead when task dependencies or run-wide progress matter. Start from
**Chip** when you want the latest result for one task across the topology.

## Inspect the Evidence

Review the status and message first, then compare the input, run, and output parameters. Open the
figure and download raw data when the task produced it. Check the execution and target before
comparing this result with another run.

<!-- MEDIA PLACEHOLDER
File: /images/guides/task-result-detail.gif
Start: Task Results filtered to one completed result with a figure.
Sequence: Open the result, inspect its figure and parameters, then scroll to AI evaluation, New thread, and Note.
Alt: Task Result detail showing its status, evidence, evaluation, discussion, and note sections.
-->

Use [Calibration Data and Provenance](./data-and-provenance.md) when you need parameter history or
the lineage of a saved value.

## Record Result Context

Add a result note for context that belongs to this measurement, such as an anomaly or the reason
for a parameter choice. Use a pinned dashboard summary when the context should remain visible for
a chip, qubit, or coupling in a selected cool-down or time range.

Notes are shared with the project. Write what another member needs to interpret the result, not a
private reminder that lacks the chip, target, or decision context.

## Start a Discussion

Select **New thread** from the result when a finding needs a decision or follow-up. QDash fills in
the result, chip, and target so the discussion links back to its evidence.

Use **Forum** to reply, mention another member, update the thread status, and close the thread when
the work is resolved. Create a standalone forum thread for topics that span multiple results or
concern project-wide policy.

## Reuse the Finding

Move a conclusion into the task's knowledge when it should guide future analysis of the same
task. **Knowledge** is read-only: changes go through the task-knowledge repository, so one person's
edit does not change what everyone else's evaluations and chats read.

1. On **Knowledge**, open the task and select **Download zip**.
2. Update the task background, expected plot, common failures, parameters to extract, or
   examples in the unzipped `index.md` and `examples/`. Keep the task title and required section
   headings unchanged.
3. Zip the folder again and evaluate with it as a knowledge draft; see
   [Try a Knowledge Change Before Proposing It](./ai-evaluations.md#try-a-knowledge-change-before-proposing-it).
4. Propose the change as a pull request to the task-knowledge repository. After it merges, the
   operator runs `task knowledge-pull` to update the deployment.

## Request an AI Review

Select **Ask AI** on one result to start a recorded evaluation or open a chat with that result's
context. Select **Evaluate** on **Chip** to evaluate the displayed task across eligible targets.

AI output is supporting evidence, not an automatic calibration decision. Confirm it against the
figure, raw data, task knowledge, and current calibration context. See
[AI Evaluations](./ai-evaluations.md) for the complete workflow.

## Follow Notifications

Mentions, replies, and system events appear in **Inbox**. Open the linked record to recover its
project and result context, then mark the notification read after reviewing the event.

## Share and Hand Off a Result

Before sending a QDash link, confirm that the recipient belongs to the active project. Project
membership controls access; removing a member revokes access without deleting the records they
produced.

When another member will continue the calibration:

1. Confirm the active project and chip.
2. Open **Task Results** and share the result link or start a forum thread from the result.
3. Record the execution, target, evidence, and next decision in the result note or thread.
4. Ask the recipient to confirm the same project and chip before starting the next task or
   workflow.

Saved calibrated outputs become the current state for later tasks in the same project. An
exploratory run with **Save calibrated outputs to DB** turned off remains available for review,
but later tasks do not use its outputs as current values. See
[Task Parameters](./task-parameters.md#decide-whether-to-save-outputs) for that choice.
