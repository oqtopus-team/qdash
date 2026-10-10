# Copilot

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
metrics, task results, issues, workflows, and provenance. Keep the active project and selected chip
in mind when interpreting an answer. Open referenced records to confirm important conclusions.

### Run a calibration pipeline from chat

With the Pi backend and write tools enabled (`AGENT_RUNTIME_ENABLE_WRITE_TOOLS=true`), the
assistant can compose a calibration from QDash's step catalog and run it as one execution. Ask for
the calibration in plain terms, for example "run the coarse one-qubit check on Q00 and Q01, then
measure T1 and T2 on the ones that pass". The assistant reads the available step types and tasks,
validates its plan with QDash, and shows an approval card listing the targets, the steps, and the
exact tasks each step will run. Nothing starts until you approve the card.

The plan can only use the step types and task names QDash exposes; it cannot contain code, and
every task result is judged by the same gates as a saved workflow. The execution appears on the
**Execution** page tagged `pipeline`. See
[Calibration Pipeline Spec](../development/workflow/calibration-pipeline.md) for the spec format.

## Metrics Analysis

The Metrics page includes a chat panel with the current analysis context. Use it when a question
depends on the selected chip, metric, target direction, or time range. Changing those filters can
change the records available to the analysis; state the intended comparison explicitly.

## Evaluate Findings

Treat AI output as supporting evidence. Before changing calibration state, excluding a result, or
starting another hardware run:

- open the underlying task result and artifacts;
- compare the finding with task knowledge and known issue cases;
- confirm the project, chip, target, and time context;
- use deterministic quality gates where the workflow provides them;
- record the decision in a note, issue, or discussion when others need the context.

Provider availability and model selection depend on the deployment configuration. Operators
configure those providers in `.env`; missing provider credentials disable the corresponding AI
capability rather than the rest of QDash.
