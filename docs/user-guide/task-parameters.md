# Task Parameters

Review inputs and output-saving settings before a run changes shared calibration state.

## Recognize the Parameter Types

| Type | Controls | Example |
| --- | --- | --- |
| Input | Calibration value consumed by a task | `qubit_frequency` |
| Run | Experiment settings | `shots` |
| Output | Value calculated by a task | `t1` |

## Use the Current Calibration Values

On **Tasks**, select the task, chip, and target, then select **Reload** to check availability and
preview current inputs. Reload fills the fields; those filled values become explicit overrides.
Leave an input field blank to resolve it from current calibration values at run time.

## Override a Value for One Run

Enter calibration inputs under **Input parameter overrides** and experiment settings under
**Run parameters**. An explicit input wins over current values and task fallbacks. A required
missing value stops the task.

For a sweep, choose a range form or **list**, then check the preview's points and endpoints.
Invalid sweeps block the run.

## Decide Whether to Update Calibration Values

Keep **Update calibration values** off for exploration. Results and artifacts are still saved.
Enable it when successful outputs should become current values for later tasks; mapped backend
configuration is also updated when enabled in the deployment.

## Re-run Previous Work

Re-running an execution uses current calibration inputs. To repeat one measurement, open its
full page from **Task Results** and select **Run again**. This opens **Tasks** with compatible
values restored; review skipped fields and overrides, then check **Update calibration values**
before **Run task**. Use **Reload** only when you want current calibration inputs to replace
the restored ones.

How this works: [Parameter Resolution](../developer-guide/workflow/parameter-resolution.md).
