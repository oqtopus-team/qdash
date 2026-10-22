# Creating Workflows

Create a workflow from a built-in template when the same ordered calibration procedure must be
saved, shared, run, or scheduled for a project.

Creating and changing workflows requires project edit permission. Start with the Fake backend
when you are learning the editor or checking a new task sequence without laboratory hardware.

## Start from a Template

1. Confirm the active project, then open **Workflow**.
2. Select **New Flow**.
3. Under **TEMPLATE**, select the workflow closest to the procedure you need. **Simple
   Calibration** is the smallest general-purpose starting point.
4. Under **PROPERTIES**, enter a unique **Flow Name** using letters, numbers, and underscores.
5. Confirm **Entrypoint Function**, **Username**, and **Chip ID**. The entrypoint must match the
   function marked as the flow in the source.
6. Edit the source, then select **Save Flow**.

Selecting another template replaces the current editor contents. Choose the template before
making source changes.

| Property | Meaning |
| --- | --- |
| **Flow Name** | Project-unique name of the saved workflow; it cannot be renamed later |
| **Description** | Purpose and expected use of the workflow |
| **Entrypoint Function** | Function QDash starts when the workflow runs |
| **Username** | Required default shown in the editor; the signed-in user owns each execution |
| **Chip ID** | Chip reserved while the workflow runs |
| **Tags** | Comma-separated labels added to execution history |

Saving checks the Python syntax and entrypoint, then registers the workflow for execution. Correct
any reported source, entrypoint, or registration error and save again.

## Choose the Targets

Set either MUX targets or individual qubit targets in the template. Standard templates give MUX
targets priority when both are present.

| Source value | Use it for |
| --- | --- |
| `mux_ids` | All qubits belonging to one or more MUXes |
| `exclude_qids` | Qubits to remove from a MUX selection |
| `qids` | An explicit list of individual qubits |

The current **Execute Flow** dialog does not collect MUX or qubit targets. To run or schedule a
workflow from the application, give the template a safe default target. In **Simple Calibration**,
add this fallback immediately before the block that creates the targets:

```python
if mux_ids is None and qids is None:
    mux_ids = [0]
```

Replace `0` with the MUX that the saved workflow should use. To target individual qubits instead,
set `qids = ["0", "1"]`. If every caller supplies targets through an API, leave the template's
missing-target check unchanged instead of adding a fallback.

## Choose Tasks and Execution Order

The task list runs from top to bottom. Open **Tasks** in another tab to find the task names enabled
for the active backend, then replace the default list in the template:

```python
if tasks is None:
    tasks = [
        "Configure",
        "CheckT1",
        "CheckRamsey",
    ]
```

Keep configuration tasks and measurement tasks in their required order. A later task reads the
calibration state produced or applied by earlier tasks.

The `mode` value controls how one-qubit work is arranged:

| Mode | Behavior |
| --- | --- |
| `scheduled` | Groups work around hardware-sharing constraints; the default for **Simple Calibration** |
| `synchronized` | Runs the same task across the selected qubits before moving to the next task |
| `serial` | Runs the selected work sequentially |
| `simultaneous_spectroscopy` | Batches supported spectroscopy tasks across compatible targets |

Keep the template's mode unless the procedure requires a specific ordering. The selected tasks
must support the chosen mode and backend.

## Set Parameters for One Task

Add `task_parameters` to the workflow's calibration service when one named task needs different
run settings, calibration inputs, or output-saving behavior:

```python
task_parameters={
    "CheckRamsey": {
        "run": {
            "shots": {"value": 1024, "value_type": "int"},
            "detuning": {"value": 0.001, "value_type": "float"},
        },
        "input": {
            "control_frequency": 7.012,
        },
        "update_calibration_parameters": False,
    },
},
```

Values under `run` control the experiment. Values under `input` replace the current calibration
input for every selected target in that task. Set `update_calibration_parameters` to `False` for
an exploratory measurement whose outputs must remain in history without becoming the current
calibration values.

QDash rejects a parameter placed in the wrong section, a parameter the task does not declare, or
an input the task does not allow users to override. See [Task Parameters](./task-parameters.md)
before overriding calibration inputs or allowing outputs to update shared state.

## Save and Test the Workflow

1. Select **Save Flow** for a new workflow. For an existing workflow, select **Edit**, make the
   change, then select **Save**.
2. Confirm that **Flow saved successfully!** appears without a save error.
3. Select **Execute** and review **Flow Name**, **Username**, **Chip ID**, and **Tags**.
4. Confirm that no other run should use the chip. A workflow reserves the entire chip until all
   its steps finish.
5. Select **Execute**, then open **Execution** to follow task order, status, parameters, and
   results.

Use a small target and non-destructive task settings for the first run. Confirm the resulting task
order and effective parameters before adding a schedule or expanding the targets.

How this works: [Workflow Authoring Quickstart](../developer-guide/workflow/quickstart.md).
