# Fake Backend

The Fake backend lets you evaluate QDash pages, workflows, persistence, and result handling
without connecting quantum hardware. It runs the Qubex calibration tasks against a simulator
instead of hardware and never opens a hardware session or contacts a box. Database records, task
results, figures, and other QDash state still persist in the paths configured in `.env`.

A Fake deployment needs no backend configuration before startup:
[Setup](../setup.md#create-the-environment-file) creates `.env` from `.env.example`, which already
sets `DEFAULT_BACKEND=fake`. This page explains what the simulator runs and how its chips are
created once QDash is running.

## What the Fake Backend Runs

The task list of the Fake backend holds one task of its own, **FakeBringUp**, and the Qubex
tasks **CheckChevron**, **CheckRabi**, **CreateHPIPulse**, **CheckHPIPulse**, **CreatePIPulse**,
**CheckPIPulse**, **CheckT1**, **CheckT2Echo**, and **CheckRamsey**. A Qubex task behaves on the
Fake backend as it does on hardware: it reads its inputs from the calibration database and
publishes its outputs there, with figures and parameters in the same shape.

**FakeBringUp** stands in for the hardware bring-up that the simulator does not emulate. Run it
first on a new chip: it writes the simulator's qubit frequency, resonator frequency, readout
amplitude, and control amplitude to the database, so the Qubex tasks after it find every input
they require. The **Fake Backend Calibration** workflow template runs FakeBringUp, CheckChevron,
CheckRabi, CreateHPIPulse, CreatePIPulse, CheckT1, CheckT2Echo, and CheckRamsey in that order.

### Targets of the Template

The template targets MUXes, as the hardware templates do. The literal `MUX_IDS` list at the top of
the source selects MUX 0 to 15, all 64 qubits, and the execution dialog shows it as the default
targets. QDash finds the four qubits of each MUX in the chip's wiring, and the same box-aware
scheduler that runs a hardware chip runs them: MUX groups in the same hardware stage run in parallel, and
the qubits of one MUX run one after another. Hardware stages run sequentially.

To calibrate fewer qubits or tasks, change the source or the run:

| Change | Effect |
| --- | --- |
| Edit `MUX_IDS`, for example to `[9, 15]` | Calibrates only those MUXes, here qubits 36 to 39 and 60 to 63 |
| Pass `exclude_qids` | Leaves those qubits out of the selected MUXes |
| Pass a `tasks` list | Reruns a subset of tasks once the chip has been brought up |
| Pass `mux_ids`, or set a target override in the execution dialog | Replaces `MUX_IDS` for one run |
| Pass `qids` without `mux_ids` | Runs only those qubits |

Flows saved from an earlier version of the template keep their own source and targets.

## Create a Chip

Create a chip after QDash is running and you have signed in as a project editor. For a first run,
follow [Run Your First Calibration](../first-calibration.md), which creates the chip from **Home**
and continues to a run and its result. Use the steps below to add another chip directly.

Every chip on a Fake deployment is the same virtual device: 64 qubits on 16 MUXes, with the
**Square Lattice with MUX** 64-qubit topology. The simulator and the generated configuration
describe the same device, so a run on any subset of qubits sees the parameters the full chip
gives them.

1. Open **Chip** and select **Create Chip**.
2. Enter a **Chip ID**. The dialog shows the virtual device, its topology, and its size as
   fixed information; there is no topology, wiring, or backend to choose.
3. Select **Create Chip**.

QDash then writes `<chip_id>/` in the configuration tree set by `CONFIG_PATH`
(`./config/qubex-config` in the example `.env`): chip, system, wiring, box, skew, and parameter
files for 16 virtual QuEL-1 boxes, one per MUX. Every file is labelled as virtual hardware, and
the box addresses are documentation-only addresses that no hardware backend can reach. When
`<chip_id>/` already exists, QDash keeps it unchanged and creates only the chip record.

The dialog blocks creation when no configuration tree is mounted, because a virtual chip cannot
run without its configuration; mount the tree and reopen the dialog. If the dialog cannot check
the deployment, it shows an error and blocks creation; close and reopen it to retry.

After the chip is created, select **Open template** in the confirmation to open the **Fake
Backend Calibration** template in **New Flow** with the new chip already selected.
