# AI Evaluations

Use a recorded AI evaluation to judge task-result figures consistently, inspect what the model
received, and compare evaluation settings.

AI output is supporting evidence. Confirm every finding against the figure, raw data, task
knowledge, and current calibration context before changing parameters or excluding data.

## Prepare the Task Reference

The evaluation uses the selected task's reference in **Knowledge**. Before evaluating a new task
or failure mode:

1. Open **Knowledge** and select the task.
2. Review its expected plot, common failures, parameters to extract, and expert-labeled examples
   (used by **In-context** evaluation).
3. Open **Evaluation prompts** and select **Preview** to read the prompts the model will receive.

**Knowledge** is read-only. To evaluate with a changed reference or new examples, use a knowledge
draft as described below.

## Start an Evaluation

Use either entry point:

- On **Chip**, select a task and choose **Evaluate** to judge the displayed results across the
  topology. Under **Targets**, clear any qubits or couplings you do not want to include.
- On a task result, select **Ask AI**, then **Evaluate the figure** to judge that one result.

A result that is still running or has no figure cannot be selected.

Choose the evaluation settings before confirming:

| Setting | Choice | Use when |
| --- | --- | --- |
| **Who prepares the prompt** | **Fixed prompt** | You need a fast, reproducible prompt built directly by QDash. |
| | **Via Copilot** | You want Copilot to summarize the result and call the evaluation model. |
| **Examples** | **Zero-shot** | The task reference is enough. |
| | **In-context** | Expert-labeled examples should be shown before the result. |

Review the request summary, then confirm. QDash records the selected targets as one evaluation
run.

## Try a Knowledge Change Before Proposing It

Evaluate against a knowledge draft to see how an edited reference changes the judgments. The
draft is read only by the run you start with it; **Knowledge** stays the same for everyone.

1. On **Knowledge**, open the task and select **Download zip**. Edit `index.md` and
   `examples/` in the unzipped folder, then zip the folder again. The zip holds one task, either
   at the top or in one folder named after the task. It may contain only `.md`, `.png`, `.jpg`,
   `.jpeg` and `.webp` files, up to 200 files, 20 MB zipped and 50 MB unpacked.
2. Start an evaluation of that task as described above.
3. Drop the zip on **Knowledge**, or select that area to choose the file. The dialog shows the
   draft's statuses, parameters and example count, and lists any format warnings. A zip for a
   different task is refused.
4. Confirm. **Who prepares the prompt** is fixed to **Fixed prompt**, because Copilot reads the
   shared knowledge.
5. Compare the run with one that used the shared knowledge. The **Knowledge** row shows which
   run used the draft.

The run's page shows the draft under **Knowledge**. Select **Download zip** there to get the
zip exactly as it was uploaded, to inspect what the run read, propose it, or start the next
edit from it.

To read the prompts a draft turns into before evaluating, open the task in **Knowledge**, drop
the zip on the draft area under **Evaluation prompts**, then select **Preview**. Only project
editors can upload a draft.

When the draft improves the judgments, propose the change to the task-knowledge repository.

## Read a Run

Open **AI Evaluations** and select a run. Each evaluated target shows the model's reading of the
plot, outcome, significance, fit quality, extracted parameters, and status.

An evaluation is complete only when every required answer is present. A missing answer leaves it
incomplete and excludes it from completed totals.

Expand **Prompt sent to the model** to inspect the exact text and figures used for one target. The
run-level **Prompt** panel summarizes the reference version, example count, and prompt consistency
across the run.

## Record Agreement

Select **Agree** or **Disagree** on each evaluation after checking the underlying result. Add a
note when the verdict needs context. The run's agreement rate reflects these human decisions, so
do not mark agreement based only on whether the model reported success.

## Compare Two Runs

Use a comparison to measure the effect of a prompt, model, example, or result change:

1. On **AI Evaluations**, select two runs for the same task and choose **Compare**. You can also
   open one run and select **Compare with…**.
2. Review the highlighted setting differences and run totals.
3. Enable **Only differences** to focus on missing or conflicting judgments.
4. Expand a target to compare both diagnoses and the figure.
5. Open **Prompt A vs B** when the prompt change may explain the outcome.

A row marked as different results means the two runs judged different task results for that
target. Treat it as a result change, not only as a model disagreement.

How this works: [Calibration Evaluation](../developer-guide/copilot/evaluation.md).
