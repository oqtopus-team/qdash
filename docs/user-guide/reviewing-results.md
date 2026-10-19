# Reviewing and Sharing Results

QDash connects task results, notes, forum threads, knowledge, and notifications inside the
active project.

## Record Result Context

Add a task-result note when the context applies to one measurement, such as an anomaly or the
reason for a parameter choice. Add a pinned chip, qubit, or coupling summary when the context
should remain visible for the selected cool-down or dashboard time range.

The dashboard notes summary gathers the current scoped notes and links back to their targets or
task results. See [Dashboard](./dashboard.md) for note scopes and fallback behavior.

## Track a Problem

Start a forum thread from a task result when a finding needs discussion or follow-up: **New thread**
on the result page opens the forum composer with the result, its chip and target prefilled, and the
thread links back to the result. The result page lists every thread about it, whatever its status.
Participants can reply, mention other members, move the thread through its workflow status, and
close it when the work is done.

Use **Forum** for everything else as well: control-stack behavior, system policy, or work spanning
multiple results. Threads can also be linked to a chip, a qubit or coupling, and a cool-down.

## Reuse Knowledge

**Knowledge** contains the maintained baseline for each calibration task: its background and
expert-labeled example plots. Every task's background follows the same template: a short intro,
**Expected plot**, **Common failures**, and **Parameters to extract**. Tasks are grouped by the
calibtasks package they live in. It is the reference the chat planner and the
evaluation model read; keep it current when a forum thread settles something that should hold
next time. The page edits the knowledge repository the way **Config** edits the Qubex
configuration. **Edit** on a task opens its Markdown source; a save takes effect in this QDash at
once, and **Create PR** opens a pull request so the change reaches
every deployment after review. **Pull** fetches what others merged. **Browse files** opens the
whole repository in the file editor for cases, images, and the README; Markdown files there have
a **Preview** and **Split** view, the explorer marks modified and untracked files, and the **Changes**
tab shows every saved edit as a diff against the last commit before you create the pull request.
**Pull** and the ZIP download sit in the repository menu (the branch button). The first heading of a
task's file is its name, so keep it unchanged; the knowledge repository rejects headings outside the
template.

## Request an AI Evaluation

The calibration evaluation model can judge the figure of a task result against the task's
reference in **Knowledge**. Two entry points lead to the same record:

- **Chip page → Evaluate** judges the latest result of the selected task for every qubit or
  coupling of the chip, or the results of the selected day, as one run. **Targets** lists the
  entities the grid shows a result for; untick some to narrow the run. An entity whose result is
  still running or has no figure cannot be ticked, and says why.
- **Task result → Ask AI** judges that one result as a run of one. The button is next to the
  result's figure in the task detail modals and on the **AI evaluation** section of the task
  result page, with the same choices as the chip page plus **Chat with Copilot**, which opens a
  conversation about the result instead of recording an evaluation.

Two settings describe an evaluation, and they are independent.

| Setting | Choice | Meaning |
| --- | --- | --- |
| Who prepares the prompt | **Fixed prompt** | QDash builds it from the result's summary and the task's reference, the same way every time, so runs are reproducible. |
| | **Via Copilot** | Copilot summarises the result and calls the evaluation itself, as AI Chat does. Slower; what Copilot did and answered is recorded too. |
| Examples | **Zero-shot** | The figure is judged against the reference alone. |
| | **In-context** | The task's expert-labeled example plots from **Knowledge** are shown before the figure, each with its diagnosis. A task without labeled examples is judged zero-shot even with this setting on; the run shows how many examples were shown. |

An optional question is passed to the evaluation model on top of the standard diagnosis. The
modal says, before you confirm, exactly what will run and with which settings.

### Read an evaluation

Open **AI Evaluations** to follow a run and read each evaluation: the diagnosis (fit quality,
success, extracted parameters), which model judged, the exact text it was given, and, via
Copilot, what Copilot did and answered. Mark each evaluation **Agree** or **Disagree**, with a
note when useful; the run's agreement rate is the ground truth for comparing runs. The task
result page lists every evaluation of that result across runs, including judgements Copilot made
on its own while answering a question (shown as **Chat** runs).

An answer is **complete** when it carries all six parts of the diagnosis. The model is asked once
more when its first answer is incomplete; an answer that still lacks parts is marked
**incomplete** with the parts it lacks, and an answer that is not a diagnosis at all is marked
**prose**. Both keep the text as returned, and neither counts as complete in the run's totals.

Each evaluation shows how long the model took and, when it was asked more than once, each call
with its duration and why it stopped. A run shows how long it took end to end and the mean per
evaluation, so two settings can be weighed on cost as well as on outcome.

### What the model was given

A run's **Prompt** panel says what the evaluation model received: the system prompt, the
reference (the task's knowledge as it was at the time, with a hash that tells two versions
apart), how many labeled examples and figures, the question, and whether these were the same
for every evaluation of the run. Via Copilot they can differ, because Copilot writes the context
and may pass a reference of its own. Each evaluation's **Prompt sent to the model** opens the
exact text, with the figures where they stood.

### Compare two runs

To see what a change made, tick two runs on **AI Evaluations** and press **Compare**, or open a
run and choose another run of the same task from **Compare with…**. The compare page shows the
two runs' settings side by side with the differing ones highlighted, the totals, and one row per
qubit or coupling with each side's fit quality, success and verdict. **Outcome** says whether
the two judgements agree; **Only differences** keeps the rows that disagree or are missing on
one side. A row marked **different results** means the runs judged different task results of
that entity, for example after a newer calibration. Expand a row to read both diagnoses next to
the figure, open **Prompt A vs B** to see the two prompts as a diff, and record your verdict on
either side. An incomplete or prose answer is shown as not comparable rather than as a
difference.

How this works: [Copilot architecture](../developer-guide/copilot/architecture.md).

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
