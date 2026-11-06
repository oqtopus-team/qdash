# Fake Backend Setup

Use the Fake backend to evaluate QDash pages, workflows, persistence, and result handling without
connecting quantum hardware.

Complete [Prepare the Host](../setup.md#prepare-the-host), then create `.env` from the default
example:

```bash
cp .env.example .env
```

Keep these backend values:

```dotenv
ENV=dev-fake
DEFAULT_BACKEND=fake
```

The Fake backend runs the Qubex calibration tasks against a simulator instead of hardware. It
never opens a hardware session or contacts a box. Database records, task results, figures, and
other QDash state still persist in the paths configured in `.env`.

## Create a Chip

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

To be guided from this dialog to the first inspected result, start
[Run Your First Calibration](../application-tour.md#run-your-first-calibration) from **Home**
instead.

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

The template targets MUXes, as the hardware templates do. The literal `MUX_IDS` list at the top
of the source selects MUX 0 to 15, all 64 qubits, and the execution dialog shows it as the
default targets. QDash finds the four qubits of each MUX in the chip's wiring, and the same
box-aware scheduler that runs a hardware chip runs them: MUXes that share no box run in
parallel, and the qubits of one MUX run one after another. Edit `MUX_IDS`, for example to
`[9, 15]` for qubits 36 to 39 and 60 to 63, to calibrate fewer qubits; pass `exclude_qids` to leave
qubits out of the selected MUXes, and a `tasks` list to rerun a subset once the chip has been
brought up. As on hardware, a `mux_ids` argument or a target override in the execution dialog
replaces `MUX_IDS` for one run, and a `qids` list without `mux_ids` runs only those qubits.
Flows saved from an earlier version of the template keep their own source and targets.

Set the administrator credentials and any shared deployment options in
[Configure Shared Deployment Settings](../setup.md#configure-shared-deployment-settings), then
[start QDash](../setup.md#start-qdash).
