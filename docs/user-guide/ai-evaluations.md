# AI Evaluations

Use recorded evaluations to review task figures and compare models or prompts. Verify AI findings
against the underlying evidence before changing calibration state.

Starting an evaluation requires Editor or Owner access and configured [AI endpoints](./setup/ai.md).
If you only have Viewer access, ask an editor to run the evaluation.

## Prepare the Task Reference

Open the task in **Knowledge**. Check its expected plot, failures, and examples. Use
**Evaluation prompts → Preview** to read the prompt. Knowledge is read-only; test changes as a draft.

## Start an Evaluation

1. Select **Evaluate** on **Chip**, or **Ask Agent → Evaluate the figure** on a result.
2. Choose targets that have finished and have figures.
3. Select the model and settings below, review the request, then confirm.

| Setting | Choices |
| --- | --- |
| **Who prepares the prompt** | **Fixed prompt** for direct evaluation; **Via Agent** for agent preparation |
| **Examples** | **Zero-shot** for the reference alone; **In-context** to include labeled examples |

Use **Cancel** to stop unfinished evaluations. **Retry unfinished** retries failed, interrupted,
or cancelled items without repeating completed ones, using the same model.

## Try a Knowledge Change Before Proposing It

1. On **Knowledge**, select **Download zip** for the task.
2. Edit `task.md` and `examples/`, preserving required headings and identity fields, then zip them.
3. Start an evaluation and upload the zip under **Knowledge**.
4. Review warnings and confirm. Drafts use **Fixed prompt**.
5. Compare with a run using shared knowledge before proposing a repository change.

The zip must contain one task, with only Markdown and PNG/JPEG/WebP images: at most 200 files,
20 MB zipped, and 50 MB unpacked. Only project editors upload drafts. The draft affects this run
only; its page retains the original zip for download.

## Find a Run

Open **AI Evaluations** and filter by **Chip** or **Task**. Use **Next** and **Previous** for older runs.

## Read a Run

Open a run to inspect judgments and extracted values. Incomplete answers do not count as
**Complete**. Expand **Prompt sent to the model** for the actual text and figures used.

Check warnings about missing examples, changed figures, or context limits. If a prompt is too
large, use fewer examples, **Zero-shot**, or a model with a larger context window.

## Record Agreement

After checking the result, select **Agree** or **Disagree**. For a disagreement, choose the issue
and add useful context. Review history is retained.

## Compare Two Runs

1. Select two runs for the same task and choose **Compare**, or use **Compare with…** in a run.
2. Review setting differences and enable **Only differences** if useful.
3. Expand a target to compare judgments; use **Prompt A vs B** to inspect inputs.

When the runs judged different task results, the difference may come from the measurement rather
than the model. How this works: [Calibration Evaluation](../developer-guide/agent/evaluation.md).
