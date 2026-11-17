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

The model picker under the message box names the model your next message goes to; the default
is marked **default**. Choose another model there or in **Settings → Copilot → Default chat
model**; the two stay in step and your browser remembers the choice. The picker cannot be opened
while an answer is streaming, or when the deployment offers only one chat model. The list of
models comes from the deployment, plus the models of your own ChatGPT plan once you connect it
(see [Use Your ChatGPT Plan](#use-your-chatgpt-plan)), and is refreshed when you open a chat or
**Settings**, or return to the window. If your chosen deployment model is no longer offered,
chats use the default and **Settings** says so. A chosen ChatGPT model is never replaced this
way: until your connection offers it again, your messages fail with the reason.

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

## Use Your ChatGPT Plan

Connect your own ChatGPT account when you want your chats answered by a ChatGPT model with the
usage included in your ChatGPT plan or credits, instead of by a model the deployment provides.
Each QDash user connects their own account; nobody else's chats use it. Only chat messages you
send with a ChatGPT model use your plan. AI evaluations, forum replies, and the tools the assistant
calls during a chat keep using the deployment's models. The models the deployment provides stay available in the model picker.

1. Open **Settings → Copilot** and select **Continue with ChatGPT**.
1. Select **Open the ChatGPT sign-in page**, sign in to ChatGPT, and approve QDash. Approve the
   use of your ChatGPT plan; without it QDash keeps the sign-in but cannot use your plan.
1. ChatGPT sends your browser to an address that starts with `http://127.0.0.1:1455/auth/callback`.
   The page does not load; this is expected. Copy the whole address from the address bar.
1. Paste it into **Address from the browser** and select **Finish connecting** within 10 minutes.
1. Select **Got it** on **You're using your ChatGPT plan**, then choose one of your ChatGPT models
   in the model picker or under **Default chat model**.

While a ChatGPT model is selected, **Using ChatGPT plan · Manage usage** appears next to the model
picker. **Manage usage** opens ChatGPT's usage settings, where you review your usage and limit how
much QDash may use. When a limit is reached, the chat says **ChatGPT usage limit reached** and
**Settings → Copilot** shows **Usage limit reached**; the limit can apply to your whole plan or to
QDash alone. QDash does not retry or switch to another model; send the message again later or
choose another model.

| Status in **Settings → Copilot** | What to do |
| --- | --- |
| **Connected as** your email | Nothing; **Reload models** refreshes the list after ChatGPT adds models |
| **Signed in, but ChatGPT plan usage is not enabled** | Select **Enable ChatGPT plan usage** and approve it |
| **The ChatGPT session ended. Connect again.** | Select **Continue with ChatGPT**; this happens after about 30 days without use, when you remove QDash in ChatGPT's settings, or when renewing your sign-in failed in a way QDash could not confirm left it unchanged, for example a lost connection or a server error, and QDash ended it to keep it safe |
| **Disconnected** | Select **Continue with ChatGPT**, or **Use a different account** to connect another ChatGPT account |
| **ChatGPT connections are not set up on this QDash server** | Ask the person who runs QDash to enable them ([AI Setup](./setup/ai.md#let-users-connect-their-chatgpt-plan)) |

**Disconnect** stops using your plan, signs out of the ChatGPT session, and deletes QDash's copy
of your sign-in. If ChatGPT does not confirm the sign-out, QDash says so; remove QDash in
ChatGPT's settings to be sure. A message already being answered when you disconnect can finish.
Disconnecting also cancels a connection you have started but not finished. Only your most recent
sign-in can finish; if QDash says a newer sign-in or a disconnect replaced the
attempt, start again.

How this works: [ChatGPT plan connections](../developer-guide/copilot/chatgpt-plan.md).

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
