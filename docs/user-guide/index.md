# User Guide

Set up QDash, run calibrations, and review results. Start with
[What is QDash?](./what-is-qdash.md) for the calibration model and a demo.

## Set Up and Operate QDash

1. [Setup](./setup.md): choose a backend, configure `.env`, start QDash, and sign in. The
   [Fake backend](./setup/fake-backend.md) evaluates QDash without hardware; the
   [Qubex backend](./setup/qubex-backend.md) connects a supported control system; the
   [Qibocal emulator backend](./setup/qibocal-backend.md) runs a Qibocal measurement on one
   emulated qubit.
2. [Run Your First Calibration](./first-calibration.md): create a chip, run a workflow, and
   inspect its first result with the guide on **Home**.

[AI Setup](./setup/ai.md) connects the model endpoints for AI chat and evaluations; QDash runs
calibrations without it.

After setup, use [Operations](./operations.md) to control and troubleshoot services and
[System Updates](./system-updates.md) to deploy another stable release.

## Find Your Way Around

<a id="learn-the-application"></a>

Find pages and their guides in the [Application Tour](./application-tour.md).

## Run Calibrations

<a id="complete-calibration-work"></a>

| Goal | Guide |
| --- | --- |
| Run a workflow or one task | [Running Calibrations](./running-calibrations.md) |
| Create or change a workflow | [Creating Workflows](./creating-workflows.md) |
| Control inputs and saved outputs | [Task Parameters](./task-parameters.md) |
| Track cryostats, cool-downs, and wiring | [Cryostats and Cool-downs](./cryostats-and-cool-downs.md) |

## Review Results

| Goal | Guide |
| --- | --- |
| Scan chip health | [Dashboard](./dashboard.md) |
| Investigate state, history, or provenance | [Calibration Data and Provenance](./data-and-provenance.md) |
| Review, discuss, or hand off a result | [Reviewing and Sharing Results](./reviewing-results.md) |

## Collaborate and Manage Access

<a id="manage-access"></a>

Use [Projects and Data Sharing](./projects-and-data-sharing.md) for membership, roles, and project
boundaries, and [Authentication and Users](./authentication-and-users.md) for accounts and
passwords.

## Use AI Assistance

| Goal | Guide |
| --- | --- |
| Ask questions about project data, or investigate a failure | [AI Chat](./ai-chat.md) |
| Judge task-result figures and compare evaluation settings | [AI Evaluations](./ai-evaluations.md) |
| Let an agent you operate run bounded, gated single-qubit steps (experimental) | [Agent Calibration](./agent-calibration.md) |

AI output is supporting evidence; confirm it against the underlying results before changing
calibration state.

## Automate QDash

Scripts and integrations use the [Python client](../reference/clients/python.md) or the
[TypeScript client](../reference/clients/typescript.md). Calibration procedures themselves are
Python workflows that you write in **Workflow**, as [Creating Workflows](./creating-workflows.md)
describes.
