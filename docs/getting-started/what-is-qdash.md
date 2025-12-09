---
layout: doc
---

# What is QDash?

QDash is a comprehensive web platform for managing and monitoring qubit calibration workflows. It provides a user-friendly interface to manage calibration processes, track observational data, and configure calibration parameters seamlessly.

::: warning
QDash is currently under development. Please check back later for updates.
:::

## Concept

To improve the accuracy of qubit calibration, it is essential to consolidate and analyze all related information systematically. QDash enables automatic management and analysis of calibration results—including when and with what settings measurements were obtained—contributing to improved calibration accuracy.

## Architecture

QDash follows a microservices architecture with three major components:

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

### Core Features

- **⚡ Workflows**: Centrally manage and track the progress of calibration workflows, from creation to completion.

- **📊 Observations**: Access and analyze the observational data utilized in calibration processes, ensuring transparency and insight.

- **⚙️ Settings**: Configure calibration parameters and adjust workflow settings to meet specific requirements seamlessly.

### Advanced Features

- **🔐 Authentication**: Secure user authentication with admin-only signup and JWT-based session management.

- **👥 Project Sharing**: Collaborate with team members by sharing projects and calibration data across users.

- **🐍 Python Flow Editor**: High-level Python API for creating custom calibration workflows with parallel execution support.

- **📈 Analysis Tools**: Time-series visualization, parameter correlation analysis, and CSV export functionality.

- **🔄 Remote Access**: Secure remote access via Cloudflare Tunnel integration.

## Screenshots

Here are some screenshots of QDash in action:

![qdash-demo](/images/qdash-demo.gif)

## Technology Stack

### Frontend

- **Framework**: Next.js 14, React 18
- **Language**: TypeScript
- **Styling**: Tailwind CSS, DaisyUI
- **Charts**: Plotly.js, React Flow
- **State Management**: TanStack Query

### Backend

- **Framework**: FastAPI
- **Language**: Python 3.10-3.12
- **Database**: MongoDB (Bunnet ODM), PostgreSQL
- **Authentication**: JWT

### Workflow Engine

- **Orchestration**: Prefect 2.20
- **Quantum Library**: qubex

## Learn More

- [Quick Start](./quick-start.md) - Get started with QDash
- [Architecture](./architecture.md) - Detailed architecture overview
- [Database Structure](/reference/database-structure.md) - Database schema reference
