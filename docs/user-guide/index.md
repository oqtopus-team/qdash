# User Guide

Use this guide to operate a QDash deployment and complete calibration work in the application.

## Set Up and Operate QDash

A new installation follows one path:

1. [Setup](./setup.md): choose a backend, configure `.env`, start QDash, and sign in. The
   [Fake backend](./setup/fake-backend.md) evaluates QDash without hardware; the
   [Qubex backend](./setup/qubex-backend.md) connects a supported control system.
2. [Run Your First Calibration](./first-calibration.md): create a chip, run a workflow, and
   inspect its first result with the guide on **Home**.

[AI Setup](./setup/ai.md) connects the model endpoints for AI chat and evaluations; QDash runs
calibrations without it.

After setup, use [Operations](./operations.md) to control and troubleshoot services and
[System Updates](./system-updates.md) to deploy another stable release.

## Learn the Application

Read [What is QDash?](./what-is-qdash.md) for the calibration model and watch the short demo.
Use the [Application Tour](./application-tour.md) to find each page and its task-specific guide.

## Complete Calibration Work

| Goal | Guide |
| --- | --- |
| Run a workflow or one task | [Running Calibrations](./running-calibrations.md) |
| Create or change a workflow | [Creating Workflows](./creating-workflows.md) |
| Control inputs and saved outputs | [Task Parameters](./task-parameters.md) |
| Scan chip health | [Dashboard](./dashboard.md) |
| Investigate state, history, or provenance | [Calibration Data and Provenance](./data-and-provenance.md) |
| Review, discuss, or hand off a result | [Reviewing and Sharing Results](./reviewing-results.md) |
| Track cryostats, cool-downs, and wiring | [Cryostats and Cool-downs](./cryostats-and-cool-downs.md) |
| Evaluate results with AI | [AI Evaluations](./ai-evaluations.md) |
| Use assisted calibration | [AI Chat](./ai-chat.md) or [Agent Calibration](./agent-calibration.md) |

## Manage Access

Use [Authentication and Users](./authentication-and-users.md) for accounts and passwords,
[Projects and Data Sharing](./projects-and-data-sharing.md) for membership, roles, and project
boundaries.

For automation, use the [Python client](../reference/clients/python.md) or
[TypeScript client](../reference/clients/typescript.md).
