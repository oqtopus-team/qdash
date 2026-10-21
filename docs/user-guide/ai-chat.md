# AI Chat

QDash provides conversational analysis tools that use project calibration context without
replacing operator judgment.

## Choose a Tool

| Tool | Use it for |
| --- | --- |
| AI Chat | Explore a question interactively with project-aware tools and cited QDash records. |
| Analysis chat panel | Discuss the metric and filters already open on the Metrics page. |
| Agent calibration | Run a separately authorized, bounded calibration campaign through the client. |

Agent calibration performs hardware-affecting operations and is documented separately in
[Agent Calibration](./agent-calibration.md).

## AI Chat

Open **AI Chat** for a project-wide conversation. Start a new session when the chip, investigation,
or goal changes substantially. QDash stores sessions so you can return to prior analysis.

The assistant can use the project tools exposed by QDash to inspect records such as chips,
metrics, task results, forum threads, workflows, and provenance. Keep the active project and selected chip
in mind when interpreting an answer. Open referenced records to confirm important conclusions.

### Thinking and your own instructions

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

### Run a calibration pipeline from chat

When an operator enables write tools, the assistant can compose a calibration from QDash's step
catalog and run it as one execution. Ask for
the calibration in plain terms, for example "run the coarse one-qubit check on Q00 and Q01, then
measure T1 and T2 on the ones that pass". The assistant reads the available step types and tasks,
validates its plan with QDash, and shows an approval card listing the targets, the steps, and the
exact tasks each step will run. Nothing starts until you approve the card.

The plan can only use the step types and task names QDash exposes; it cannot contain code, and
every task result is judged by the same gates as a saved workflow. The execution appears on the
**Execution** page tagged `pipeline`. See
[Calibration Pipeline Spec](../developer-guide/workflow/calibration-pipeline.md) for the spec format.

## Metrics Analysis

The Metrics page includes a chat panel that opens with the selected task result as its context. Use it
when a question depends on the selected chip, metric, target direction, or time range. Changing those
filters can change the records available to the chat; state the intended comparison explicitly.

**Ask AI** on a task result offers two routes before anything starts. **Evaluate the figure**
creates a recorded evaluation with the settings described in
[AI Evaluations](./ai-evaluations.md). **Chat with Copilot** opens the conversation described
here. Viewers without edit rights go straight to the chat.

## Evaluate Findings

Treat AI output as supporting evidence. Before changing calibration state, excluding a result, or
starting another hardware run:

- open the underlying task result and artifacts;
- compare the finding with task knowledge;
- confirm the project, chip, target, and time context;
- use deterministic quality gates where the workflow provides them;
- record the decision in a note or a forum thread when others need the context.

Provider availability and model selection depend on the deployment configuration. A missing AI
provider disables that capability rather than the rest of QDash.
