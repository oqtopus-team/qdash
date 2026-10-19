# Developer Guide

This guide is for people changing QDash code. Procedures for running and using QDash are in the
[User Guide](../user-guide/index.md); this guide explains how the system is built and how to
change it.

## Start Here

- [Architecture](./architecture.md): the three components and how a
  calibration flows through them.
- [Setup](./setup.md): a working local stack for development.
- [Codebase](./codebase.md): where API, UI, workflow, and shared code live, and what is generated.
- [Commands](./commands.md): the `task` commands used day to day.
- [Testing](./testing.md): which checks to run for which change.
- [Development Flow](./development-flow.md) and
  [Docs Guidelines](./docs-guidelines.md): branches, commits, and how
  documentation is organised and written.

## Conventions

Rules that hold across the code: [datetime handling](./conventions/datetime.md),
[logging](./conventions/logging.md), [QID validation](./conventions/qid-validation.md),
[credential scanning](./conventions/credential-scan.md).

## Components

Each component has its design, its architecture, and its own testing page.

- API: [design guidelines](./api/design.md), [contracts](./api/contracts.md), [code structure](./api/structure.md), [testing](./api/testing.md),
  [endpoint testing](./api/testing-endpoints.md)
- UI: [architecture](./ui/architecture.md), [guidelines](./ui/guidelines.md),
  [components and state](./ui/components.md), [styling](./ui/styling.md),
  [TypeScript](./ui/typescript.md), [API integration](./ui/api-integration.md),
  [design policy](./ui/design-policy.md), [testing](./ui/testing.md)
- Workflow: [quickstart](./workflow/quickstart.md),
  [engine architecture](./workflow/engine-architecture.md),
  [services](./workflow/services.md),
  [calibration data lifecycle](./workflow/calibration-data-lifecycle.md),
  [parameter resolution](./workflow/parameter-resolution.md),
  [testing](./workflow/testing.md), [fixtures](./workflow/testing-fixtures.md),
  [component tests](./workflow/testing-components.md)
- Copilot: [architecture](./copilot/architecture.md),
  [agent platform](./copilot/agent-platform.md),
  [knowledge layout](./copilot/knowledge-layout.md),
  [sandbox](./copilot/sandbox.md), [streaming](./copilot/streaming.md)

## Architecture Deep Dives

Cross-component designs: [schedulers and ordering](./architecture/index.md),
[notes](./architecture/notes.md), [provenance](./architecture/provenance.md).

## Reference

[Database structure](../reference/database-structure.md) with its
[data models](../reference/data-models.md) and document pages,
[database indexes](../reference/database-indexes.md), [OpenAPI](../reference/openapi.md), and the
[Python](../reference/clients/python.md) and [TypeScript](../reference/clients/typescript.md)
client packages.
