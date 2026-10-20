# User Guide

This guide is for people who set up, run, and use QDash: everything from starting the stack to
reviewing a calibration result.

## Set Up and Operate

- [Setup](./setup.md): clone QDash, configure `.env` and Qubex, start Compose,
  and sign in.
- [Operations](./operations.md): start, stop, inspect logs, and handle common
  local failures.
- [System Updates](./system-updates.md): select and deploy a stable release from the host. An
  upgrade that changes stored data has its own page: [v1.8.0](./migrations/v1.8.0.md),
  [project-scoped calibration](./migrations/project-scoped-calibration.md).

## Work in QDash

Read in this order the first time; afterwards each page stands on its own.

- [Application Tour](./application-tour.md): the pages, what each is for, and who can do what.
- [Authentication](./authentication.md) and [Projects and Sharing](./projects-and-sharing.md):
  accounts, roles, and the project boundary that scopes everything else.
- [Roles and Permissions](./permissions.md): what each system and project role can do.
- [Dashboard](./dashboard.md): chip health at a glance.
- [Running Calibrations](./running-calibrations.md) and [Task Parameters](./task-parameters.md):
  workflows, one-off task runs, and how parameters are resolved.
- [Data and Provenance](./data-and-provenance.md): the data views and how to trace a parameter
  back to the measurement that produced it.
- [Reviewing Results](./reviewing-results.md): notes, forum threads, knowledge, and AI
  evaluations of task results.
- [Copilot](./copilot.md) and [Agent Calibration](./agent-calibration.md): the chat assistant,
  and bounded calibration runs driven by an agent.
- [Cryostats and Cool-downs](./cryo.md) and
  [Calibration Data Sharing](./calibration-data-sharing.md): the physical context and the
  storage boundary of calibration data.

Scripts and notebooks that read QDash data use the
[Python client](../reference/clients/python.md) or the [TypeScript client](../reference/clients/typescript.md).
