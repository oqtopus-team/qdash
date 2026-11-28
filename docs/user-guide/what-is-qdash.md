# What is QDash?

QDash runs quantum-chip calibrations and keeps their results, parameters, and discussions together.

## What QDash Manages

| Term | Meaning |
| --- | --- |
| Project | A team's shared data and access boundary |
| Chip | The device being calibrated |
| Task | One measurement or calibration operation |
| Workflow | A reusable sequence of tasks |
| Execution | One run and its results |
| Calibration state | Accepted values used by later tasks |

Select the project and chip before working. Chips with the same ID in different projects do
not share calibration state.

## Typical Calibration Loop

1. [Run a workflow or task](./running-calibrations.md).
2. [Inspect the results](./reviewing-results.md) and [parameter history](./data-and-provenance.md).
3. Record findings and decide which values later tasks should use.

## Ways to Work

Use the web application for interactive work, the [clients](../reference/index.md) for scripts,
or the [Agent](./ai-chat.md) for assistance. Check AI findings against the recorded evidence.

## Demo

<video controls playsinline preload="metadata" src="/videos/qdash-demo.mp4" style="width: 100%; border-radius: 8px;"></video>

Continue with [Setup](./setup.md) or [Run Your First Calibration](./first-calibration.md).
