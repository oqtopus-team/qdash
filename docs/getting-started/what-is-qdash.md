---
layout: doc
---

# What is QDash?

QDash is a web platform for operating qubit calibration workflows, inspecting calibration state,
and sharing results within a project.

## Concept

To improve the accuracy of qubit calibration, it is essential to consolidate and analyze all related information systematically. QDash enables automatic management and analysis of calibration results—including when and with what settings measurements were obtained—contributing to improved calibration accuracy.

## Architecture

QDash has three main application components:

```
┌─────────────────────────────────────────────────────────────────┐
│                         QDash Platform                          │
├─────────────┬─────────────────────────┬─────────────────────────┤
│   Frontend  │        Backend          │    Workflow Engine      │
│  (Next.js)  │       (FastAPI)         │       (Prefect)         │
│             │                         │                         │
│  - React    │  - REST API             │  - Calibration flows    │
│  - TanStack │  - MongoDB (Bunnet)     │  - Python Flow Editor   │
│  - Plotly   │  - PostgreSQL           │  - qubex integration    │
│  - DaisyUI  │  - JWT Auth             │  - Deployment service   │
└─────────────┴─────────────────────────┴─────────────────────────┘
```

## Key Features

- **Calibration operation**: Create, schedule, and monitor workflows, or run one task from the
  task workbench.
- **State inspection**: Review chip topology, configured metrics, task results, artifacts,
  time-series data, and parameter provenance.
- **Project collaboration**: Share calibration state and files through explicit project roles,
  notes, issues, forum discussions, notifications, and knowledge cases.
- **Assisted analysis**: Use project-aware chat and AI review runs as supporting evidence during
  result analysis.
- **Client access**: Integrate through the REST API or the generated Python and TypeScript clients.

## Screenshots

Here are some screenshots of QDash in action:

![qdash-demo](/images/qdash-demo.gif)

## Technology Stack

### Frontend

- **Framework**: Next.js 16, React 19
- **Language**: TypeScript
- **Styling**: Tailwind CSS, DaisyUI
- **Charts**: Plotly.js, XYFlow
- **State Management**: TanStack Query

### Backend

- **Framework**: FastAPI
- **Language**: Python 3.10-3.12
- **Database**: MongoDB (Bunnet ODM), PostgreSQL
- **Authentication**: JWT

### Workflow Engine

- **Orchestration**: Prefect 3
- **Quantum Library**: qubex

Use [Operator Setup](../operator-guide/setup.md) to deploy QDash or
[Developer Setup](../development/setup.md) to prepare a development environment. The
[Application Tour](../user-guide/application-tour.md) maps the available features, while the
[Architecture](./architecture.md) and [Database Structure](../reference/database-structure.md)
describe the implementation.
