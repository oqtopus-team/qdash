# Developer Guide

Start with [Setup](./setup.md), make a change, then follow [Development Flow](./development-flow.md)
to test it and open a pull request. For product operation, use the [User Guide](../user-guide/index.md).

## Make a First Change

1. Complete [Setup](./setup.md), then create a [work branch](./development-flow.md#branch-strategy).
2. Choose a change below and follow its component guide.
3. Run the component's focused test, then the [pre-push check](./development-flow.md#before-pushing).
4. Open a pull request against `develop` and describe the behavior and verification.

## Find the Right Area

| Change | Start here |
| --- | --- |
| Understand the system | [Architecture](./architecture.md) and [Codebase](./codebase.md) |
| API or stored data | [API design](./api/design.md) |
| Pages and interactions | [UI architecture](./ui/architecture.md) |
| Calibration execution | [Workflow engine](./workflow/engine-architecture.md) |
| Chat and AI evaluation | [Agent architecture](./agent/architecture.md) |
| Documentation | [Writing guidelines](./docs-guidelines.md) |

Use [Commands](./commands.md) for task names, [Testing](./testing.md) to choose checks,
and [Reference](../reference/index.md) for APIs and data models.

Shared code follows the [datetime](./conventions/datetime.md),
[logging](./conventions/logging.md), and [credential scanning](./conventions/credential-scan.md) rules.
