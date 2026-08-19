# Calibration Data Sharing

QDash shares calibration state by project and chip while retaining the user and execution that
produced each result.

## Data ownership model

Four identifiers describe the scope of calibration data:

| Identifier | Purpose |
| ---------- | ------- |
| Project | Collaboration and access boundary |
| Chip | Hardware whose current calibration state is being maintained |
| Execution | One calibration run and its results and artifacts |
| User | Actor recorded for audit and attribution |

The project is the primary isolation boundary. Two projects may use the same chip ID without
sharing calibration state. Within one project, all members work with the same state for a chip;
QDash does not maintain a separate copy for each user.

For example, if Alice calibrates qubit `0` on chip `chip-a`, Bob's next execution in the same
project reads the values saved by Alice. Bob's result becomes the new current state when that task
is configured to persist its output parameters. Both executions remain in the history with their
respective users.

## Shared current state

The following data is shared by members of the same project for each chip:

- Chip configuration and topology
- Current qubit and coupling parameters
- Parameter history and calibration notes
- Classifier files used by the calibration backend
- The execution counter used to allocate execution IDs

This allows one project member to continue calibration from another member's latest result. A user
must have the appropriate [project role](./projects-and-sharing.md#team-roles-and-permissions) to
update this state.

The user shown on a record identifies who performed the operation. It is an actor snapshot and
does not create a user-specific calibration namespace.

## Execution records and artifacts

Each run has its own execution record, task results, figures, and raw data. These records are
visible to project members but remain associated with the execution that produced them. Starting a
new execution does not overwrite an earlier execution's result or artifact references.

On a standard deployment, execution artifacts use this layout:

```text
calib_data/projects/{project_id}/chips/{chip_id}/executions/{execution_id}/
```

Classifier files are reusable chip state rather than execution output, so they use a shared path:

```text
calib_data/projects/{project_id}/chips/{chip_id}/shared/classifier/
```

These are deployment storage paths. Users normally access results through the QDash UI or client
instead of reading these directories directly.

## What happens during an execution

Quick Run and regular workflow executions use the same ownership model:

1. QDash resolves the project, chip, and target qubits or couplings for the execution.
2. The workflow loads the chip's current parameters from the selected project.
3. The backend receives those values and the project's shared classifier files.
4. Each task stores its result and artifacts under the current execution.
5. Output parameters update the project's current chip state only when parameter persistence is
   enabled for that execution and the task output is eligible for an update.

The output-parameter view can therefore show both the previous shared value and the new task
result. The previous value is the state read before the update, not a value owned by the current
user.

## Switching projects

The active project determines which chips, current parameters, classifiers, and execution history
QDash uses. Before starting a calibration, verify the selected project as well as the chip. Moving
to another project changes the calibration namespace even when a chip with the same ID exists
there.

Calibration data cannot currently be moved between projects through the user interface. Create the
chip and establish its calibration state separately when work needs a different access boundary.

## Existing installations

Upgrades migrate legacy user-scoped database records and calibration files into the project and
chip layout automatically during deployment. Operators should follow the
[project-scoped calibration migration guide](../reference/migration-project-scoped-calibration.md)
for backup, verification, duplicate handling, and recovery details.
