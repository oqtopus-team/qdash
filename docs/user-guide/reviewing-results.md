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
once (the task's JSON is regenerated), and **Create PR** opens a pull request so the change reaches
every deployment after review. **Pull** fetches what others merged. **Browse files** opens the
whole repository in the file editor for cases, images, and the README; Markdown files there have
a **Preview** and **Split** view, the explorer marks modified and untracked files, and the **Changes**
tab shows every saved edit as a diff against the last commit before you create the pull request.
**Pull** and the ZIP download sit in the repository menu (the branch button). The first heading of a
task's file is its name, so keep it unchanged; the knowledge repository rejects headings outside the
template.

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

**Show labeled examples** adds the task's expert-labeled example plots from Knowledge before the
figure, each followed by its diagnosis, the way the QCalEval papers evaluate in context. Off is
zero-shot. The run records which examples were shown, so two runs of the same results, with and
without examples, compare the two settings on the same ground truth.

Open **AI Evaluations** to follow a run and read each evaluation: the diagnosis (fit quality,
success, extracted parameters), which model and extension version judged, the exact text the model
saw, and, in planner mode, the planner's tools and answer. Mark each evaluation **Agree** or
**Disagree**, with a note when useful; the run's agreement rate is the ground truth for comparing
runs made with different extension versions, models or task references. The task result page lists
every evaluation of that result across runs, including judgements the chat planner made on its
own while answering a question (shown as **Chat** runs).

### Compare two runs

To see what a change made, pick two runs on **AI Evaluations** (the checkbox next to each run)
and press **Compare**, or open a run and choose another run of the same task from **Compare
with…**. The compare page shows the two runs' settings side by side with the differing ones
highlighted (mode, labeled examples, model, extension version, question), the totals, and one
row per qubit or coupling with each side's fit quality, success and verdict. **Outcome** says
whether the two judgements agree on fit quality and success; **Only differences** keeps the rows
that disagree or are missing on one side. A row marked **different results** means the runs
judged different task results of that entity, for example after a newer calibration. Expand a
row to read both diagnoses next to the figure and record your verdict on either side.

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
