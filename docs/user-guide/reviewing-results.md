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

Move a conclusion into **Knowledge** when it should guide future analysis of the same task.
Update the task background, expected plot, common failures, or parameters to extract, then preview
the evaluation prompts before saving.

Use the repository actions in **Knowledge** to pull reviewed changes or create a pull request for
other deployments. Keep the task title and required section headings unchanged.

## Request an AI Review

Select **Ask AI** on one result to start a recorded evaluation or open a chat with that result's
context. Select **Evaluate** on **Chip** to evaluate the displayed task across eligible targets.

AI output is supporting evidence, not an automatic calibration decision. Confirm it against the
figure, raw data, task knowledge, and current calibration context. See
[AI Evaluations](./ai-evaluations.md) for the complete workflow.

## Follow Notifications

Mentions, replies, and system events appear in **Inbox**. Open the linked record to recover its
project and result context, then mark the notification read after reviewing the event.

## Share a Result

Before sending a QDash link, confirm that the recipient belongs to the active project. Project
membership controls access; removing a member revokes access without deleting the records they
produced.

See [Calibration Data Sharing](./calibration-data-sharing.md) when another member will continue the
calibration from this result.
