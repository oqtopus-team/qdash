# Agent

Use the Agent to ask questions about a project's calibration data, investigate a failure, or have
the assistant draft a workflow change or a calibration run for you to approve. The assistant reads
QDash records with your permissions; it does not replace operator judgment.

The Agent needs a chat model endpoint; an administrator configures it as described in
[AI Setup](./setup/ai.md). Without one, the rest of QDash works unchanged.

## Choose an Entry Point

| Entry point | Use it for |
| --- | --- |
| **Agent** in the sidebar | A project-wide conversation with cited QDash records |
| **Ask Agent** on the right edge of any page | The same chat beside the page you are on |
| **Ask Agent** on a task result | Discussing or evaluating one result |
| **Investigate with AI** in an **Error Log** | Finding the likely cause of a failed execution or task |
| [Agent Calibration](./agent-calibration.md) | Running a separately authorized, bounded calibration plan through the client |

## Start a Conversation

Open **Agent** for a project-wide conversation. Start a new session when the chip,
investigation, or goal changes substantially. QDash stores sessions so you can return to earlier
analysis.

The assistant can inspect chips, metrics, task results, forum threads, workflows, and provenance.
Confirm the active project and chip, then check important conclusions against the cited records.

### Check What the Agent Uses

Above the message box, the chat lists what your next message carries besides its text. The list
shows only what QDash knows and sends; a general chat on the **Agent** page shows none.

| Item | Shown when | What it means |
| --- | --- | --- |
| **Result** | The chat is about one task result | The task, qubit, and chip saved with this chat; every message names them |
| **Investigating** | The chat investigates a failure | The failed execution, with the task, qubit, and chip when known, saved with this chat |
| **Page** | You chat from the **Ask Agent** sidebar or the floating window | The page you have open now; it follows you as you navigate, and adds **with editor code** on the **Workflow** editor and the metric script editor, and **with dashboard draft** on a dashboard you can edit |

Hover over an item for its full details. The link icon on **Result** or **Investigating** opens
the execution. The saved result or investigation cannot be removed from a chat; start a general
chat with **New chat** on the **Agent** page instead. In the sidebar and the floating window,
**New chat** keeps the result the current chat is about. The chat does not send a time range;
name one in your message when it matters.

### Follow an Answer in Progress

While an answer is written, the chat shows what the assistant is doing now, such as a tool it
runs or **Waiting for the expert's answer** while it waits on QDash. When the assistant has sent
nothing for 30 seconds, the line under the answer says **Connected · last update 4m 10s ago**: the
connection is fine, and the assistant is waiting or working without a new step to show. It does
not mean the assistant is stuck, and a session or execution page that shows progress does not by
itself mean the chat's answer is still running.

If the connection drops, the line says **Connection lost, reconnecting** with the time of the last
update, and the chat reconnects to the same answer by itself, without sending your message again.
Once back, it shows the answer from its start and goes on with it; nothing the assistant did runs
twice. If the assistant never received the message, the chat says so and asks you to send it
again. After about 10 minutes without a connection, the chat stops trying and says that the
assistant may still be working. **Stop** works throughout and stops only that answer.

Moving to another page, closing the sidebar or the floating window with its close button, or
reloading the page in the same browser tab does not stop an answer; only **Stop** does. Closing
only hides the chat: the answer goes on, and reopening the chat shows its progress or how it
ended. After a reload, the chat reconnects to the answer and shows it from its start, without
sending your message again; until then it shows **Reconnecting to the running answer** with what it last saw the assistant do and **last known update … ago**. An answer
that ended meanwhile is shown as it ended. If the chat cannot reconnect, it says so above the
message box and leaves the conversation as it was. An answer you started in another project keeps
running when you switch projects; the chat shows **Running in another project** and follows it
again when you switch back. Signing out forgets what the tab kept about running answers.

QDash saves the answer as it is written, whether or not a window shows it. Closing every
window, or the browser, does not stop the answer; only **Stop** does. Reopening the chat while
the answer runs shows it from its start and follows it; until it reconnects, the saved part of the
answer is marked **Answer in progress, saved by the server**. Reopening it after the answer ended
shows the whole answer. A reload or another browser shows the same saved conversation. If QDash
cannot save an answer, the chat says so and the window you sent it from keeps its own copy.
If QDash itself restarts while an answer runs, the answer keeps running in the assistant, and
reopening the chat reconnects to it and saves it.

The same chat open in another window or browser tab of yours, in the same project, shows the
answer in progress too, from its start, once that window is in front or within about 15 seconds
while it is shown. Nothing is sent again, and **Stop** works from either window. Only the window
where you sent the message shows its notifications. An answer that started and ended while the
other window was not checking appears there at its next check. A message sent from a window that
shows an older copy of the chat, such as one opened before another window's answer ended, is not
sent: the chat says that it changed in another window and shows the saved conversation, so you can
send the message again.

The chat's header says what its answer is doing: what the assistant runs, **Waiting for the
expert's answer**, **Reconnecting**, **Answer in progress** for a saved answer the chat does not
follow now, or, once the answer ended, **Answered**, **Waiting for your approval**, **Waiting for
your answer**, **Stopped**, or **Failed**. While the sidebar is closed,
a dot on **Ask Agent** shows that an answer is running, and **Ask Agent** opens that chat rather
than a new one.

A notification at the top of the page tells you when an answer is ready, needs your approval or
your answer, proposed a change, waits for an expert, or failed, unless that chat is already on
screen in a visible tab. Each happens once per answer, also after a reconnect or a reload, and
only for the project you have open. **Open chat** shows that chat; nothing is sent for you.
Notifications that need your input stay until you dismiss them or open the chat; press Escape to
dismiss one, or Alt+T to move to it. The notification goes, but the chat's header keeps saying
where the answer stands. Notifications play no sound unless you turn on **Settings → Copilot →
Chat notifications → Play a sound**; set its **Volume** and try it with **Preview**. The setting
applies to this browser only.

### Add to an Answer in Progress, or Continue One

You can type while an answer is still being written. Press Enter or the arrow button beside
**Stop**: the message goes to the answer in progress, which reads it after its current step,
such as a tool that is still waiting on a calibration, instead of starting a new answer. It shows
under the answer as **Read after the current step**, then moves into the conversation where the
assistant read it. Figures cannot go with such a message; send them as a new message. A message
that arrives after the assistant wrote its last step is answered next, after the current answer.

When you stop an answer, or the connection drops, before the chat sees whether the answer read a
message, the message shows **Checking whether the answer read it…** until QDash finds out. If the
assistant read it, the message moves into the conversation right after the answer it interrupted,
with the note **Sent while the answer above was written; it read this during or after that
answer**, and stays there after a reload. If QDash cannot find out, the message shows **Not
confirmed whether the answer read it** with **Check again**; it is not offered for sending again, because the assistant may have read it. Such a message stays shown after you reload the page in the same browser tab, and QDash checks it again.

If the assistant service stopped unexpectedly while a message waited to be read, the assistant reads it when
you next send a message in that chat, and answers it before your new message. The message and
the assistant's answer to it then move into the conversation before your new message, the
message with the same note.

An answer that the stopped service was still writing is not lost: sending a new message in that
chat resumes it, finishes it first, and then answers your message. **Continue** is refused for
such an answer because it is still the chat's current answer; send a new message instead. Until
then, the chat's other branches refuse new messages and say that another branch has unfinished
work; open the branch the answer belongs to and send a message there first, or delete that
branch, which stops its unfinished answer without running it.

A message the answer never read stays below the conversation with the reason: the answer had
already finished, was stopped, or ended with an error. **Send as new message** sends it on its
own, and **Dismiss** removes it.

When an answer was stopped or ended with an error, **Continue** lets the assistant go on from
where it ended without your message being sent again. **Retry** or **Regenerate** instead sends
your last message again. If the answer read a message you sent just before you stopped it,
Continue also answers that message. Continue is not offered after a complete answer, while a message you
sent during the answer is still being checked, and it is refused while a question, an approval
card, or a proposed edit waits for you; answer those instead.

When the latest answer ended with a server error, a connection that closed before the answer
was complete, or another error reported by the chat, **Report this error** shows a bug-report
draft that you can copy. The draft records the error category, the HTTP status, a known page
category with private path segments removed, and the time the draft was generated (not the
error occurrence time). Unrecognized errors have an unclassified source. The draft leaves
out the error text, which can contain private details, and has places for your steps and hypotheses. Review it, remove anything private, and
post it yourself with **Open the GitHub bug form**; QDash does not file issues. A refused
request (an HTTP 4xx answer, such as a sign-in, permission, or input problem) offers no report,
and neither does a failed measurement, a rejected value, or a declined approval inside an
answer. The assistant follows the same rule when a tool fails unexpectedly.

### Branch from an Answer

Use **Branch from here** under a completed answer to try a different direction without changing
the original chat. QDash opens a new chat with the conversation up to that answer; the assistant
remembers exactly what it knew at that answer, including tools it had loaded and values its
scripts had kept. The new chat appears in the session list with a branch icon.

The button explains two things before you use it, and the branched chat repeats them at the top:

- The branch shares the original chat's workspace files as they are now, not as they were at
  that answer. A file changed in either chat is changed in both.
- The original chat and its branches answer one at a time. While one of them answers, a message
  sent in another, or a new branch, is refused with a note that another branch is answering; try
  again when it has finished.

**Branch from here** is offered only for an answer that finished normally while nothing is
answering in the chat. It is not offered for a stopped or failed answer, an answer that ends with
a question, an approval card, or a proposed edit, or answers saved before QDash added branching.
The branch keeps the model you choose in the chat, not the model used for the original answer.

After **Retry**, **Regenerate**, or editing a message, the chat shows only the new exchange, but
the assistant still remembers the replaced one. A branch from a later answer remembers it too.

Deleting the original chat keeps its branches working. QDash removes the shared workspace and
the saved conversation only when you delete the last chat that uses them. Deleting a chat stops
its answer if one is running; other branches keep answering. If the assistant service cannot
remove them right away, QDash retries the next time it loads your chat list.

If a branch fails because the assistant service could not be reached, select **Branch from
here** again: QDash finishes the same branch rather than making a second one.

### Ask Agent Beside Any Page {#ask-ai-beside-any-page}

**Ask Agent** opens a sidebar with the current page as context. Drag its left edge to resize it, or
double-click to restore the default width. Your browser remembers the width. On a narrow screen
the sidebar covers the page instead; when you apply a proposed change, it closes so you can
review the change on the page, and **Ask Agent** on the right edge opens the chat again. A
proposal the page refuses leaves the sidebar open.

On the **Workflow** editor the assistant also sees the flow's code as it is in the editor,
unsaved changes included. Ask for a change in plain terms, for example "add a T2 echo check after
T1". The answer shows a diff against the editor; **Apply to editor** puts the new code into the
editor and unlocks it, **Discard** leaves it as it was. Nothing is saved until you select
**Save**, which checks the flow the same way as a hand-written one.
Apply is available only while the proposal's flow is open on the same chip.

The metric script editor works the same way: the assistant sees the script as it is in the
editor, checks its changes by validating and previewing the draft, and proposes them as a diff
that **Apply to editor** puts into the editor of that script. See
[Write a Script with the Agent](./metric-scripts.md#write-a-script-with-the-agent).

On a dashboard you can edit, and on a new dashboard from **Create with Agent**, the assistant sees
the unsaved draft and proposes a new one as a diff. **Apply to draft** puts it on the page;
**Save** on the page stores it. The empty chat there suggests dashboard requests, and nothing is
sent until you pick one or type your own. See
[Create a Dashboard with the Agent](./dashboards.md#create-a-dashboard-with-the-agent).

### Calculations and Scripts

When the deployment enables it, the assistant has a private workspace for each chat: a shell with
Python, NumPy, SciPy, pandas, Plotly and Matplotlib, no network, and no access to QDash. It uses
it for arithmetic, fitting and data wrangling, writing data from tool results into files. The
trace shows commands, generated code, and output. Files stay for the rest of the chat and are
deleted with it.

### Thinking and Your Own Instructions

The model picker under the message box names the model your next message goes to; the default
is marked **default**. Choose another model there or in **Settings → Copilot → Default chat
model**; the two stay in step and your browser remembers the choice. The picker cannot be opened
while an answer is streaming, or when the deployment offers only one chat model. The list of
models comes from the deployment and is refreshed when you open a chat or **Settings**, or
return to the window. If your chosen model is no longer offered, chats use the default and
**Settings** says so.

The **Thinking** menu next to the model picker sets how much the model reasons before it answers:
**Auto** (the model's configured default), **Off**, **Low**, **Medium**, or **High**. The choice
applies from the next message and is remembered in your browser. A model that always reasons,
such as Claude Opus 5.5, cannot turn it off: its menu omits **Off**. A previously saved
**Off** choice displays and runs as **Low** for that model.

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

## Choose How a Calibration Runs

A single-qubit calibration can run two ways: step by step, where the assistant picks each next
measurement from the last result inside a session you approve, or as a workflow, where it sets
out the whole sequence (a saved workflow, a template, or a pipeline) for you to review before it
runs. When you ask only "calibrate Q06", the assistant asks which you want before it proposes
anything. Say it in the request, for example "calibrate Q06 step by step from the results" or
"run the one_qubit workflow on Q06", and it does not ask; it keeps your answer for the rest of
the chat. Questions about stored results and remeasuring one property such as T1 never get this
question. Your answer only picks the way: every session, run, and saved value still needs its
own approval, and when the chosen way stops or fails, the assistant reports it and asks instead of
switching to the other way.

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

## Calibrate Qubits Step by Step

Ask for a supervised calibration of named qubits, for example "calibrate Q00 step by step and
ask an expert if it gets stuck". The assistant proposes a bounded session on an approval card,
which shows whether the calibration evaluator is used (**Evaluation** off or required) and each
value it may update without asking, decided by that task's own checks. The assistant cannot add
numeric bounds or quality gates to a session, even ones you state; to calibrate within bounds you
choose, create the session yourself with the qdash-agent CLI
([Create a bounded session](./agent-calibration.md#create-a-bounded-session)). Another value the
same task estimates, which the session does not grant, is kept for reference and does not hold up
the granted one;
once you approve it, it chooses each measurement from the last result without further cards,
keeps the values as candidates until you approve a commit (it asks before a measurement that
needs a new value), and asks an expert in QDash when it
cannot tell what to do next. To continue after the expert answers, tell it to continue, in the
same chat or a new one. See [Agent Calibration](./agent-calibration.md).

## Ask Agent About a Task Result {#ask-ai-about-a-task-result}

**Ask Agent** appears on a task result and in a metric's history on **Metrics**. It offers two routes
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
