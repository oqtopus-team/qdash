# Reviewing and Sharing Results

Use **Task Results** to inspect a measurement, record findings, and share the next decision.

## Find a Result

1. Open **Task Results**.
2. Filter by chip, execution, task, target, or status.
3. Select a row for a preview, then open the full result if needed.

Use **Execution** for run-wide progress or **Chip** for the latest task results across the device.

## Inspect the Evidence

Check the status, message, parameters, and figure. Download raw data when available. For a saved
value's origin or history, follow [data and provenance](./data-and-provenance.md).

For **ReadoutClassification** and **EFReadoutClassification**, download the **Raw data**
NetCDF file when the run produced a Qubex classifier. It preserves that run’s classifier,
training shots, and confusion matrix even after a later run replaces the chip’s classifier.

## Record Result Context

Add a result note for an anomaly, interpretation, or parameter choice. Use a pinned chip or
target summary for context that should remain visible across measurements. Notes are shared.

## Start a Discussion

Select **New thread** on the result to keep the discussion linked to its evidence. Use **Forum**
for replies, mentions, and project-wide discussions; close a thread when resolved.

## Reuse the Finding

**Knowledge** is read-only. To improve a task reference:

1. Select **Download zip** on the task.
2. Edit its reference and examples, preserving required headings and identity fields.
3. Test it as an [evaluation draft](./ai-evaluations.md#try-a-knowledge-change-before-proposing-it).
4. Propose the change to the task-knowledge repository. After merge, ask the operator to update
   the deployment's knowledge.

## Request an AI Review

Select **Ask Agent** on one result or **Evaluate** on **Chip**. Check the judgment against the
actual evidence before changing calibration state. See [AI Evaluations](./ai-evaluations.md).

## Follow Notifications

Select the bell for recent notifications or **View all** for **Inbox**. Use **Unread only** to
focus on new items. Opening one marks it read; **Mark all read** affects every page.

## Share and Hand Off a Result

1. Confirm that the recipient [belongs to the project](./projects-and-data-sharing.md#share-results).
2. Share the result link or its forum thread.
3. Record the chip, target, evidence, and next decision.

Runs made with **Update calibration values** off remain in history but do not supply current
values to later tasks. See [Task Parameters](./task-parameters.md).
