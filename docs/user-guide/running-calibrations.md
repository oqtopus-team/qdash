# Running Calibrations

Use **Workflow** for a repeatable sequence of tasks, or use **Tasks** to run one calibration task
against a selected qubit or coupling.

Both routes use the active project and chip. Confirm both before starting because a run can update
the calibration values used by later tasks.

## Choose a Run Mode

| Goal | Start from |
| --- | --- |
| Run a saved task graph or schedule | **Workflow** |
| Run one task and inspect its result immediately | **Tasks** |
| Repeat a previous run with selected values restored | The source execution or task result |

Running a workflow or task requires project edit permission.

## Run a Workflow

1. Open **Workflow** and select a workflow. Follow [Creating Workflows](./creating-workflows.md)
   first if you need to create or change one.
2. Select **Edit** before changing the source, then select **Save**.
3. Select **Execute**.
4. Review the flow name, username, chip, and tags in the confirmation dialog.
5. Under **Calibration targets**, review the defaults from the saved workflow. To change them
   for this run, select **MUX IDs** or **Qubit IDs** and enter IDs separated by commas or spaces.
   For MUX targets, use **Excluded qubit IDs** to omit individual qubits. For a two-qubit workflow
   that groups selected directed pairs automatically, enter **Coupling pairs** instead, as described below.
6. Confirm the run, then open **Execution** to follow its progress.

Leaving the target fields unchanged preserves the workflow's code settings. **Use code defaults**
discards target edits. An explicit change replaces the initial calibration targets throughout the
current flow run; later filtering steps still apply. The saved workflow and schedules are unchanged.
A workflow that targets all MUXes, or targets couplings without offering **Coupling pairs**, stops
with an error when you change its targets.

**Coupling pairs** replaces the MUX and qubit fields for automatic pair workflows, such as
**2Q Automatic Pairs**. Workflows that choose pairs from qubits or build opaque step lists in
helper functions do not offer it. Write each pair as `control-target`, for example `63-85`,
and separate pairs with commas, spaces, or new lines. Direction matters: `85-63` calibrates
the opposite direction, and each directed pair must exist on the run's chip. QDash groups only
these pairs using the chip's hardware constraints and the step's parallelism cap. Later filters
can remove pairs whose qubits no longer qualify.

**2Q Automatic Pairs** requires a saved `coupling_pairs` selection or a selection in **Execute**.
**2Q Manual Rounds** uses the rounds and targets saved in its source and offers no target override;
see [Write Two-Qubit Rounds](./manual-execution-rounds.md#write-two-qubit-rounds).

If targets depend on runtime calculations or differ within the workflow, the dialog cannot show a
single default. Leave the fields unchanged to use the code, or enter an explicit selection for the
run. Separate nested workflow runs retain their own targets.

Use the workflow schedule panel when the same flow must run automatically. Manage schedules in
QDash so the workflow and its Prefect deployment remain aligned.

## Run One Task

<!-- MEDIA PLACEHOLDER
File: /images/guides/task-workbench.gif
Start: Tasks with no task or target selected.
Sequence: Select a task, chip, and target; select Reload; then show resolved inputs and run options without starting hardware.
Alt: Task workbench ready to run one calibration task with resolved inputs and run options.
-->

1. Open **Tasks** and select a task.
2. Under **Setup**, select **Chip** and enter a **Qubit or coupling** such as `0` or `0-1`.
3. Select **Reload** to check hardware availability and load the current input values.
4. Review **Input parameter overrides** and **Run parameters**. Leave an input override blank to
   use the current calibration value.
5. Enable **Reconfigure hardware first** when the current calibration configuration must be
   applied before the task starts.
6. Enable **Update calibration values** only when successful outputs should become the current
   calibration values. The run is saved in task history either way.
7. Select **Run task** and follow the status in **Results**.

The run button stays disabled while another execution holds the same hardware or until **Reload**
has checked a changed target. See [Task Parameters](./task-parameters.md) before overriding inputs
or saving outputs.

## Monitor a Run

Open **Execution** to inspect a run's status, task topology, timing, parameters, output, and
artifacts. Select a task in the topology to open its details, or select a node in the execution
flow to preview its result in the same side panel that **Task Results** uses; open the full
result from there. While a run is in progress, its details and its page show how many tasks have
finished and which one is being measured, and the running task shows its measurement progress.

Cancelling a run sends a cancellation request to the worker. A task that is inside an operation
that cannot be interrupted can take time to stop.

The activity chart groups the chip's runs by status over **7d**, **30d** (default), or **90d**:

- **30d** and **90d** show one column per day.
- **7d** shows 28 six-hour periods starting at 00:00, 06:00, 12:00, and 18:00 in the
  deployment's time zone, including the current period.

Empty periods keep their columns. The chart labels how many executions a full block represents;
a partially filled block holds fewer. Hover over or focus a column for exact counts. Select it
to filter the list to that day, even in the six-hour view; select the same day again to clear
the filter.

With **Group sessions** on (the default), each calibration objective and each agent calibration
session is one row of the list, holding the runs started for it. A calibration objective's row
shows the objective, its targets, how many pipeline runs and runs it holds and how many are
running or failed, the time from its first to its latest activity, and the recommendation when
one was recorded. **Open** or **Closed** says only whether it accepts new work, never whether the
objective was met. Expand it to list each pipeline run with its step runs, and each agent
session started in it as its own nested row. An agent session row shows the session's own state,
such as **Active** or **Paused for an expert**, not the state of its last run: a session waiting
between measurements or for an expert is not failed. Expand the row to list its runs and open one
in the same details panel as any other run; select **Open session graph** to see every step. The
count above the list gives runs and rows separately, because one row can hold several runs. With
a day selected, a row appears when it was created or started a run that day, and it still lists
all of its runs. A run belongs to a row only when it was started for that objective or by that
agent session; a run recorded before this grouping existed stays its own row. Turn the switch
off for the plain list of runs. See [Agent Calibration](./agent-calibration.md#follow-a-session-on-the-execution-page).

Every workflow, pipeline, or task you start belongs to a calibration session, and so does every
step it runs, unless your administrator turned automatic grouping off (see
[Turn Off Automatic Calibration Session Grouping](./operations.md#turn-off-automatic-calibration-session-grouping)).
When you start one without choosing an objective, QDash creates a session for that run alone,
marked **Automatic**. A saved workflow with several steps is therefore one row on the
grouped list, with each step listed under the run, and running it again adds another session
with its own run. Scheduled workflow runs are grouped the same way, one session per scheduled
run. Each run is labeled **Workflow**, **Pipeline**, or **Task**, and a scheduled one is marked
**Scheduled**. To collect several runs toward one goal, such as an agent's optimization trials,
start them in the same calibration session; the assistant does this for you. Runs recorded
before this grouping existed are not moved into a session. With automatic grouping off, a run
started without an objective is an ordinary row on the list, and a run started in a calibration
session is grouped as before.

A run shows its objective as a badge on its card. The details panel and the run's page say why
it belongs there and offer **Open calibration session**; an agent session row offers the same
link beside **Open session graph**. After you start a workflow in **Workflow**, the confirmation
offers **Open calibration session**.

The card names the user whose sign-in started the run. **Agent** marks a run an agent session
dispatched. **Agent tool, reported** marks a pipeline the assistant's tool started with your
approval: the tool reports this itself and QDash does not verify it, so the run stays yours.
Belonging to an objective does not make a run an agent run.

Select **Calibration sessions** at the top of the **Execution** page to list the objectives on
the selected chip, newest first. Filter them by **Open** or **Closed**, by origin
(**Created for an objective** or **Automatic**), or with **Only mine**, and remove the chip
filter to see every chip. Selecting an objective opens its page.

An objective's page shows **Search progression** when the assistant recorded experiments for it,
such as a ZX90 gate search: the stages reached (**Baseline**, **Screening**, **Confirmation**), a
comparison of each candidate's requested change with its measured gate time, fidelity with its
error, CR duration, and hardware time, the recorded recommendation, and the latest requested run
with how its executions ended. Measured values come from the runs' task results; the rationale
and the recommendation are statements of whoever recorded them. When the latest requested run's
candidate is not the recommended candidate, the page says so. It never shows which calibration
is on the hardware: QDash does not record hardware writes, and a run requested earlier can
finish later. **Audit** below lists every
decision, pipeline request, launch outcome, run, and agent session step in order, with what
QDash never received (such as an approval given in the chat) marked **Not recorded**; select
**Export JSON** to download it.

## Inspect a Result

Open **Task Results** when you know the chip, execution, task, target, or status you want to find.
Open an item to inspect its effective parameters, figures, raw data, notes, and linked discussion.

Use an execution detail when the dependency graph matters. Use **Task Results** when one
measurement or failure is the focus. See [Reviewing and Sharing Results](./reviewing-results.md)
for the review workflow.

## Edit Workflow Configuration

Open **Config** to edit the active project's Qubex configuration files. Save local changes before
pulling or creating a pull request; pulling can replace the working copy.

Figures and raw data stay associated with the project, chip, execution, and task result that
produced them. See
[Share and Hand Off a Result](./reviewing-results.md#share-and-hand-off-a-result) before handing a
run over to another project member.
