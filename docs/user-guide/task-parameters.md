# Task Parameters

Review task parameters before a run to control the experiment without accidentally replacing the
project's current calibration values.

## Recognize the Parameter Types

| Type | What it controls | Example |
| --- | --- | --- |
| Input parameter | An existing calibration value consumed by the task | `qubit_frequency` |
| Run parameter | How this experiment runs | `shots` |
| Output parameter | A value calculated by the task | `t1` |

## Use the Current Calibration Values

Use the default resolution when you want a task to start from the current state:

1. Open **Tasks** and select a task.
2. Select **Chip** and enter a **Qubit or coupling**.
3. Leave fields under **Input parameter overrides** blank.
4. Select **Reload** to preview the current values and check hardware availability.
5. Review the resolved values before selecting **Run task**.

An empty input override means “resolve this value for me”; it does not send an empty value to the
task. Selecting **Reload** copies the current values into the fields. Those populated fields are
explicit overrides for the run, but **Reload** does not change the calibration database.

## Override a Value for One Run

Enter an input value when this run must use a value other than the current calibration state.
Enter experiment settings such as shots or sweep limits under **Run parameters**.

A run parameter that sweeps a range shows a form selector next to its arguments. The default form
is marked **(default)**; the others are **np.linspace**, **np.logspace**, **np.arange**, **range**,
and **list**. Changing the form keeps the sweep: the linear forms and **list** exchange the same
points, so you can edit them one by one, and a change to or from **np.logspace** keeps the first
point, the last point, and the number of points. When the new form cannot express the sweep, for
example **range** with a fractional step, the arguments stay as typed and the line under the field
reports the result. That line shows how many points the sweep produces and its first and last
values. When it reports that the numbers produce no sweep, **Run task**
shows the problem instead of starting the run. The task result records the form the run used, and
re-running that result restores it.

QDash uses an entered input value before a current calibration value or a task fallback. A task
that requires a missing value stops with the parameter name instead of silently using zero.

## Decide Whether to Save Outputs

Leave **Save calibrated outputs to DB** off for an exploratory run. QDash records the result,
effective parameters, figures, and raw data without replacing current calibration values.

Enable it only when successful output parameters should become the current values for later
tasks. The warning below the setting confirms that the run can change shared state. Mapped backend
configuration is also updated when that integration is enabled.

## Re-run Previous Work

Re-running an execution restores its task and run context, then resolves calibration inputs from
the current state. Use this route to repeat a flow while intentionally picking up newer
calibration values.

Re-running one task result opens the current task definition with compatible values from the
source result. Review any skipped historical fields, then edit the restored values before
selecting **Run task**. Values entered in the form take priority.

Always check **Save calibrated outputs to DB** again on a re-run; reproducing a measurement and
accepting its outputs are separate decisions.

How this works: [Parameter Resolution](../developer-guide/workflow/parameter-resolution.md).
