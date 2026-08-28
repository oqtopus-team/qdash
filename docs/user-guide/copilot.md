# Copilot and AI Reviews

QDash provides conversational analysis and bulk AI review tools that use project calibration
context without replacing operator judgment.

## Choose a Tool

| Tool | Use it for |
| --- | --- |
| AI Chat | Explore a question interactively with project-aware tools and cited QDash records. |
| Analysis chat panel | Discuss the metric and filters already open on the Metrics page. |
| AI Reviews | Analyze a selected set of displayed task results and compare target-level findings. |
| Agent calibration | Run a separately authorized, bounded calibration campaign through the client. |

Agent calibration performs hardware-affecting operations and is documented separately in
[Agent Calibration](./agent-calibration.md).

## AI Chat

Open **AI Chat** for a project-wide conversation. Start a new session when the chip, investigation,
or goal changes substantially. QDash stores sessions so you can return to prior analysis.

The assistant can use the project tools exposed by QDash to inspect records such as chips,
metrics, task results, issues, workflows, and provenance. Keep the active project and selected chip
in mind when interpreting an answer. Open referenced records to confirm important conclusions.

## Metrics Analysis

The Metrics page includes a chat panel with the current analysis context. Use it when a question
depends on the selected chip, metric, target direction, or time range. Changing those filters can
change the records available to the analysis; state the intended comparison explicitly.

## Request an AI Review

From a chip task view, select the displayed qubit or coupling results and request an AI review.
The request creates a review run containing one record per reviewed target. Open **AI Reviews** to
filter runs by chip or task and inspect findings and referenced artifacts.

Review only the results currently displayed and verify target direction and selection before
submitting. A review run is a snapshot of that request; later calibration results do not rewrite
its findings.

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
