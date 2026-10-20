# Workflow Development

The workflow subsystem owns calibration execution, task lifecycle, scheduling, parameter
resolution, persistence, and the boundary between QDash and Prefect.

## Choose the Right Guide

| Goal | Read |
| --- | --- |
| Run or modify a small workflow example | [Workflow Engine Quickstart](./quickstart.md) |
| Understand engine responsibilities and extension points | [Workflow Engine Architecture](./engine-architecture.md) |
| Understand Prefect-facing services | [Workflow Services](./services.md) |
| Use the JSON pipeline contract | [Calibration Pipeline Spec](./calibration-pipeline.md) |
| Trace measured outputs into accepted state | [Calibration Data Lifecycle](./calibration-data-lifecycle.md) |
| Change task input or output resolution | [Parameter Resolution](./parameter-resolution.md) |
| Change frequency semantics | [Frequency Parameter Policy](./frequency-parameter-policy.md) |
| Select and run workflow tests | [Workflow Testing Guidelines](./testing.md) |
| Reuse fixtures and mocks | [Workflow Test Fixtures and Mocking](./testing-fixtures.md) |
| Follow component-level test patterns | [Workflow Component Tests](./testing-components.md) |

Scheduler-specific designs live under [Architecture Deep Dives](../architecture/index.md).

## Source and Tests

Workflow code lives under `src/qdash/workflow/`. Tests mirror it under `tests/qdash/workflow/`.
Run `task test-workflow` for focused behavior and `task test` when a change crosses shared model,
repository, or API boundaries.
