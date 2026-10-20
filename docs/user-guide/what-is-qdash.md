---
layout: doc
---

# What is QDash?

QDash keeps calibration execution, results, and operator context together for each quantum chip.

## What QDash Manages

Calibration work produces more than a final parameter value. Operators also need the inputs,
measurement artifacts, execution status, history, and discussion that explain where the value
came from. QDash records these parts in one project-scoped workspace.

| Concept | Meaning in QDash |
| --- | --- |
| Project | The access and storage boundary shared by a team. |
| Chip | The device whose calibration state is being maintained. |
| Workflow | A reusable graph of calibration tasks that can be run or scheduled. |
| Task | One calibration operation that measures or checks selected targets. |
| Execution | One run, including status, logs, task results, and artifacts. |
| Calibration state | The accepted parameters available to later calibration work. |

Select the active project and chip before starting work. Two projects can use the same chip ID
without sharing calibration state. [Projects and Data Sharing](./projects-and-sharing.md)
explains this boundary.

## Typical Calibration Loop

1. Select the project and chip that own the calibration state.
2. Run a reusable workflow or one task from the workbench.
3. Monitor the execution and inspect its task results and artifacts.
4. Compare the result with metric history and parameter provenance.
5. Record notes or open a forum thread when the result needs context or follow-up.
6. Use the resulting state as input to later calibration work.

[Running Calibrations](./running-calibrations.md) covers steps 1–3.
[Calibration Data and Provenance](./data-and-provenance.md) covers step 4, and
[Reviewing and Sharing Results](./reviewing-results.md) covers step 5.

## Ways to Work

Use the web application for interactive operation and investigation. The generated Python and
TypeScript clients provide the same API for scripts, notebooks, and integrations. Copilot can
help explore project data, but the operator remains responsible for checking evidence and making
hardware decisions.

## Demo

A 30-second tour of QDash: chip dashboard, chip topology, workflows, live executions, and
time-series analysis.

<video controls playsinline preload="metadata" poster="/images/qdash-demo-poster.png" src="/videos/qdash-demo.mp4" style="width: 100%; border-radius: 8px;"></video>

Continue with the [Application Tour](./application-tour.md) to find each feature, or
[set up QDash](./setup.md) for a lab. Developers can start with the
[system architecture](../developer-guide/architecture.md).
