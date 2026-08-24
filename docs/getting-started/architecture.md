---
layout: doc
---

# Architecture

QDash consists of three major components.

- UI
  - Next.js frontend for workflow operation, monitoring, and analysis
- API
  - FastAPI backend that handles user requests, authentication, project access, and database access
- Workflow
  - Prefect-based calibration workflow runtime, deployment service, and user flow worker

![qdash-architecture](../diagrams/qdash-platform-architecture.drawio.png)

## Components

### QDash UI

The UI is the frontend for users, developed with Next.js and React. It provides pages for
dashboarding, chip/task inspection, workflow editing and execution, metrics, provenance, issue
tracking, file management, and Copilot-assisted analysis.

The UI client and standalone TypeScript client are generated with Orval from the API's OpenAPI
schema. API contract changes therefore require client regeneration with `task generate`.

![qdash-ui](/images/qdash-ui.png)

### QDash API

The API receives user requests, enforces authentication and project access, communicates with
MongoDB and Prefect, and exposes the OpenAPI schema used to generate the UI and standalone TypeScript clients.

![server-example](/images/server-example.png)

### QDash Workflow

The workflow component manages qubit calibration workflows. Prefect is the workflow engine, while
QDash stores user flow files, registers Prefect deployments through the deployment service, and
executes user flows with the user flow worker.

Calibration task implementations call the laboratory libraries they need, while QDash supplies
execution context, parameter resolution, persistence, scheduling, and status tracking.

![workflow-example](/images/qcflow-example.png)

### Calibration Flow

Calibration follows this flow.

1. The user selects a project, chip, targets, and workflow or task in the UI or client.
2. The API saves or loads the user flow and asks the deployment service to register a Prefect deployment.
3. The user flow worker executes the selected calibration tasks. Experimental libraries can be used from task implementations.
4. The workflow runtime acquires the applicable execution lock before hardware operations.
5. QDash creates an execution ID that links the run, task results, logs, and artifacts.
6. Task results and accepted calibration changes are stored in their project and chip context.
7. Parameter resolution can use the current accepted state as input to later tasks.
8. If a user cancels a running execution, the API sends a cancel request to Prefect, which terminates the worker process via SIGTERM. The `on_cancellation` hook then updates the execution and task statuses to `cancelled` and releases the execution lock.

![qdash-calibration-flow](../diagrams/calibration-flow.drawio.png)

The [Workflow Engine Architecture](../development/workflow/engine-architecture.md) describes the
runtime components in detail. [Calibration Data Sharing](../user-guide/calibration-data-sharing.md)
explains project-scoped state and artifacts.
