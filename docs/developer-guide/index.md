# Developer Guide

Use this guide to understand, change, test, and contribute to QDash. Procedures for operating the
product are in the [User Guide](../user-guide/index.md).

## Make Your First Change

1. Read [Architecture](./architecture.md) to see the UI, API, and workflow boundaries.
2. Follow [Development Setup](./setup.md) to start a local environment.
3. Use [Codebase](./codebase.md) to find the owning package and generated files.
4. Choose commands from [Command Reference](./commands.md).
5. Run the checks selected by [Testing](./testing.md).
6. Follow [Development Flow](./development-flow.md) when preparing the pull request.

## Choose a Component

| Area | Owns | Start here |
| --- | --- | --- |
| API | Authentication, project access, persistence, and HTTP contracts | [API Design Guidelines](./api/design.md) |
| UI | Routes, interaction, server state, and presentation | [UI Architecture](./ui/architecture.md) |
| Workflow | Calibration execution, scheduling, parameters, and Prefect integration | [Workflow Engine Architecture](./workflow/engine-architecture.md) |
| Copilot | Chat, evaluation, agent execution, and the workspace | [Copilot Architecture](./copilot/architecture.md) |
| Cross-component design | Data flow, schedulers, topology, notes, and provenance | [Architecture](./architecture.md) |

Use the component groups in the sidebar to open implementation rules and focused test guides. Use
[Reference](../reference/index.md) when you need an exact schema, index, generated API, or client
contract.

## Apply Repository-Wide Conventions

The conventions for [datetime handling](./conventions/datetime.md),
[logging](./conventions/logging.md), and
[credential scanning](./conventions/credential-scan.md) apply across component boundaries.

Use [Documentation Guidelines](./docs-guidelines.md) for any page under `docs/`.
