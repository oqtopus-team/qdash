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

Agent calibration performs hardware-affecting operations and has its own guide.

## Start a Conversation

Open **AI Chat** for a project-wide conversation. Start a new session when the chip,
investigation, or goal changes substantially. QDash stores sessions so you can return to earlier
analysis.

The assistant can inspect records such as chips, metrics, task results, forum threads, workflows,
and provenance through the tools QDash gives it. Keep the active project and selected chip in mind
when you interpret an answer, and open the referenced records to confirm important conclusions.

### Ask AI Beside Any Page

**Ask AI** on the right edge opens the same chat as a sidebar next to the page you are on. The
assistant is told which page is open with every message, so "what am I looking at?" or "compare
this with last week" refer to the current page. Drag the sidebar's left edge to make it wider or
narrower; double-click the edge to restore the default width. The width is remembered in your
browser.

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
answer's trace shows each command, the file it wrote with the code typed out as it is written,
and the output of each run. Files stay for the rest of the chat and are deleted with it.

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

**What Copilot is told**, below the instructions, shows read-only what the application sends the
chat model: QDash's system prompt, your instructions as they are appended to it, and the tools the
chat offers. It is the running text, so it reflects the current skills, tools, and language
settings; the application's part is edited in the deployment, not in Settings.

## Investigate a Failure

Use **Investigate with AI** when an execution or a task failed and you want to know why. The
button appears in the **Error Log** of a failed execution on the **Execution** page and on its
detail page, in the **Error Log** of a failed task result, and on a failed task in an execution's
task details. It works when the execution failed before any task result was recorded.

1. Select **Investigate with AI** in the **Error Log** header.
2. The chat opens and sends the investigation for you. On the **Execution** pages, in task
   details, and in a task result preview, it opens in the floating chat window, so the details
   panel stays in view; on a task result's own page it opens in the chat sidebar. QDash adds the
   recorded error message and stack trace, and the execution, task, qubit, and chip identifiers
   to the chat.
3. Read the answer, then ask follow-up questions in the same chat.

The assistant reads available source code, starting from the code that raised the error. The
answer is short: the likely cause, the evidence
(a quoted log line and cited code locations), and one next step to check or a fix
to review. The assistant reads more code only when the evidence is unclear; ask a follow-up
question for a deeper analysis. It does not apply fixes or re-run anything.

QDash does not record which source revision an execution ran with. The answer names the revision
of the source it read, or says it is unknown, and says that it cannot confirm that this source
matches the failed run. When the logs are missing or too long, the answer says what is missing.

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

Available models depend on the deployment configuration. A missing AI provider disables that
capability, not the rest of QDash.
