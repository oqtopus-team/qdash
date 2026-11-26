# Agent

Use **Agent** to ask about project data, investigate failures, and draft changes or runs for review.
An administrator must configure [AI endpoints](./setup/ai.md).

## Choose an Entry Point

| Entry point | Context |
| --- | --- |
| **Agent** | General project conversation |
| **Ask Agent** beside a page | Current page, including an open editor's draft |
| **Ask Agent** on a result | That result and its figures |
| **Investigate with AI** in an error log | Failed execution and recorded error |

## Start a Conversation

Confirm the project and chip, then ask a specific question. Name the time range when it matters;
chat does not automatically send it. Start a new chat when the goal changes substantially.

To use a calibration skill, type `/` at the start of the message. Select a skill, add the
chip, targets, and goal after its name, then send. Selecting a skill leaves the message
in the composer for review. For example, `/skill:qdash-zx90-optimization` guides a search
on one directed coupling. Supply the allowed parameter bounds and hardware time budget,
then review each proposed pipeline before it runs.

### Check What the Agent Uses

The labels above the message box show the **Result**, **Investigating**, or **Page** context
sent with your next message. A result or investigation stays with that chat; use **New chat**
on the main **Agent** page for a general conversation.

### Follow an Answer in Progress

The header shows what the assistant is doing or waiting for. Closing the sidebar, navigating,
or reloading does not stop it. Reopen the chat to reconnect; use **Stop** to end the answer.
A lost connection does not mean the underlying operation stopped.

### Split a Research Question

Ask the assistant to split independent lookups, for example: “Use subagents to investigate
Q01 and Q02 separately, then compare their calibration failures from today.”

Expand **Research subagents** in the answer's activity to follow each task. Open **Findings**
to read its result or **Error** to see why it failed. The assistant combines the findings
into its answer. Each child uses your project access and the chat's model, and can only read
QDash data; it cannot run calibrations or change settings.

Reloading keeps the tasks visible. **Stop** stops the parent answer and its children.
An **Interrupted** task did not finish; ask the assistant to investigate it again.
This feature is available in the web Agent when enabled by the administrator.

### Add to an Answer in Progress, or Continue One

Send a message while an answer runs to add guidance after its current step. Send figures in a
new message. If receipt is uncertain, use **Check again** rather than duplicating the request.

**Continue** resumes an eligible stopped or failed answer. **Retry** and **Regenerate** send
your last message again. Resolve pending questions, approvals, and proposed edits first.
If **Report this error** appears, review its draft before posting it yourself.

### Branch from an Answer

Use **Branch from here** on a completed answer to explore another direction. Branches share
workspace files as they are now and answer one at a time. Deleting the last chat using a
workspace removes it.

### Ask Agent Beside Any Page {#ask-ai-beside-any-page}

Open **Ask Agent** beside a workflow, metric script, or dashboard. The assistant can read unsaved
changes and propose a diff. **Apply to editor** or **Apply to draft** changes the local draft;
select **Save** on the page to store it.

### Save Answers and Files

Use **Save as Markdown** on a finished answer or **Download** on a code block. A file listed
under **Original write content from this answer** downloads that recorded write, not later
workspace edits.

### Calculations and Scripts

When enabled, the assistant has a chat workspace for calculations. It has no network or direct
QDash access. Files last until the chat and its branches are deleted.

### Thinking and Your Own Instructions

Choose the next message's model and **Thinking** level below the message box. Use
**Settings → Agent → Your instructions** for account-wide language or formatting preferences.
These instructions do not bypass approvals or change evaluation and forum prompts.

## Investigate a Failure

Select **Investigate with AI** in the **Error Log**, read its evidence and proposed next step,
and ask follow-up questions. The investigation does not apply a fix or rerun the task.
Missing logs and an unverified source revision limit its conclusions.

## Choose How a Calibration Runs

Specify either a reviewed workflow or a step-by-step calibration, for example “run the one_qubit
workflow on Q06” or “calibrate Q06 step by step.” The assistant asks if the choice is unclear.
Choosing a method does not approve its session, runs, or saved values.

## Run a Calibration Pipeline from Chat

Describe the targets and procedure. The assistant validates a plan and shows its exact steps
and tasks on an approval card. Nothing starts before approval. The run appears on **Execution**.

## Calibrate Qubits Step by Step

Ask for a supervised calibration of named qubits. Review the proposed scope and parameter-update
grants before approving. See [Agent Calibration](./agent-calibration.md) for measurements,
expert help, and commits; the assistant cannot invent numeric bounds for you.

## Follow a Calibration Objective

The assistant can propose a **Calibration session** to group work toward one goal. Approving
it records the objective only; each run or agent session still needs its own approval.

Open its card or **Execution → Calibration sessions** to see runs and audit records.
**Close session** prevents new work but does not cancel admitted runs or declare success.
Resolve active work and any **Start unknown** outcome before closing; an admitted run may still
start afterward. A new chat can continue the same objective.

## Ask Agent About a Task Result {#ask-ai-about-a-task-result}

Select **Ask Agent**, then **Chat with Agent** or **Evaluate the figure**. Viewers go directly
to chat. See [AI Evaluations](./ai-evaluations.md) for recorded figure reviews.

## Check AI Findings

Open the cited results and task knowledge, confirm their project and target, and check findings
before changing calibration state. Record consequential decisions in a note or discussion.
