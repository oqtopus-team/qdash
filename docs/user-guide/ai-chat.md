# AI Chat

Use AI chat to ask questions about a project's calibration data, investigate a failure, or have
the assistant draft a workflow change or a calibration run for you to approve. The assistant reads
QDash records with your permissions; it does not replace operator judgment.

AI chat needs a chat model endpoint; an administrator configures it as described in
[AI Setup](./setup/ai.md). Without one, the rest of QDash works unchanged.

## Choose an Entry Point

| Entry point | Use it for |
| --- | --- |
| **AI Chat** in the sidebar | A project-wide conversation with cited QDash records |
| **Ask AI** on the right edge of any page | The same chat beside the page you are on |
| **Ask AI** on a task result | Discussing or evaluating one result |
| **Investigate with AI** in an **Error Log** | Finding the likely cause of a failed execution or task |
| [Agent Calibration](./agent-calibration.md) | Running a separately authorized, bounded calibration plan through the client |

## Start a Conversation

Open **AI Chat** for a project-wide conversation. Start a new session when the chip,
investigation, or goal changes substantially. QDash stores sessions so you can return to earlier
analysis.

The assistant can inspect chips, metrics, task results, forum threads, workflows, and provenance.
Confirm the active project and chip, then check important conclusions against the cited records.

### Ask AI Beside Any Page

**Ask AI** opens a sidebar with the current page as context. Drag its left edge to resize it, or
double-click to restore the default width. Your browser remembers the width.

On the **Workflow** editor the assistant also sees the flow's code as it is in the editor,
unsaved changes included. Ask for a change in plain terms, for example "add a T2 echo check after
T1". The answer shows a diff against the editor; **Apply to editor** puts the new code into the
editor and unlocks it, **Discard** leaves it as it was. Nothing is saved until you select
**Save**, which checks the flow the same way as a hand-written one.
Apply is available only while the proposal's flow is open on the same chip.

### Calculations and Scripts

When the deployment enables it, the assistant has a private workspace for each chat: a shell with
Python, NumPy, SciPy, pandas, Plotly and Matplotlib, no network, and no access to QDash. It uses
it for arithmetic, fitting and data wrangling, writing data from tool results into files. The
trace shows commands, generated code, and output. Files stay for the rest of the chat and are
deleted with it.

### Thinking and Your Own Instructions

The **Thinking** menu next to the model picker sets how much the model reasons before it answers:
**Auto** (the model's configured default), **Off**, **Low**, **Medium**, or **High**. The choice
applies from the next message and is remembered in your browser.

**Settings → Copilot → Your instructions** holds instructions added to every chat you start, after
QDash's own rules: language, tone, and formats such as "answer in Japanese, conclusion first" or
"put numbers in a table with units". They are stored with your account, so they follow you across
devices. They do not apply to AI evaluations or forum replies, which stay the same for everyone,
and they cannot skip the approval of write operations. A **Your instructions** link in the chat
composer shows when they are on.

**What Copilot is told** shows the current system prompt, your appended instructions, and
available tools. The application-owned text is read-only; change it in the deployment.

## Investigate a Failure

Use **Investigate with AI** in an **Error Log** to investigate a failed execution or task,
even when no task result was recorded.

1. Select **Investigate with AI**. QDash opens a chat and sends the recorded error, stack trace,
   and execution context. It uses a floating window to keep details visible, or the sidebar on
   a task result's own page.
2. Read the likely cause, supporting logs and source references, and proposed next step.
3. Ask follow-up questions for deeper analysis. The assistant does not apply fixes or re-run tasks.

The answer identifies missing or truncated logs and the source revision it inspected. QDash
does not record the source revision of a failed run, so the assistant cannot confirm a match.

Selecting the button again for the same failure reopens that chat instead of starting a new one.
To run the investigation again from the start, select **New chat** while the investigation chat is
open, then select **Investigate with AI**. The earlier chat stays in your chat history.

## Run a Calibration Pipeline from Chat

The assistant can compose a calibration from QDash's step catalog and run it as one execution
with your approval and project permissions. Ask for the calibration in plain terms, for example
"run the coarse one-qubit check on Q00 and Q01, then
measure T1 and T2 on the ones that pass". The assistant reads the available step types and tasks,
validates its plan with QDash, and shows an approval card listing the targets, the steps, and the
exact tasks each step will run. Nothing starts until you approve the card.

The plan can only use the step types and task names QDash exposes; it cannot contain code, and
every task result is judged by the same gates as a saved workflow. The execution appears on the
**Execution** page tagged `pipeline`. See
[Calibration Pipeline Spec](../developer-guide/workflow/calibration-pipeline.md) for the spec format.

## Ask AI About a Task Result

**Ask AI** appears on a task result and in a metric's history on **Metrics**. It offers two routes
before anything starts:

- **Evaluate the figure** creates a recorded evaluation with the settings described in
  [AI Evaluations](./ai-evaluations.md).
- **Chat with Copilot** opens a chat with that result and its figures as context.

Viewers without edit rights go straight to the chat. When the question depends on the chip,
metric, target direction, or time range, state the intended comparison explicitly.

## Check AI Findings

Treat AI output as supporting evidence. Before changing calibration state, excluding a result, or
starting another hardware run:

1. Open the underlying task result and its artifacts.
2. Compare the finding with the task's knowledge.
3. Confirm the project, chip, target, and time context.
4. Use the deterministic quality gates that the workflow provides.
5. Record the decision in a note or a forum thread when others need the context.
