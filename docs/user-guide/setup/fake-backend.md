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
does not read Qubex hardware configuration or open a hardware session. Database records, task
results, figures, and other QDash state still persist in the paths configured in `.env`.

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
CheckRabi, CreateHPIPulse, CreatePIPulse, CheckT1, CheckT2Echo, and CheckRamsey in that order;
pass a `tasks` list to rerun a subset once the chip has been brought up.

Set the administrator credentials and any shared deployment options in
[Configure Shared Deployment Settings](../setup.md#configure-shared-deployment-settings), then
[start QDash](../setup.md#start-qdash).
