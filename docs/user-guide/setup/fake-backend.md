# Fake Backend

The Fake backend simulates calibration without hardware. It still saves results and calibration
values. Start with `.env.example` as described in [Setup](../setup.md).

## What the Fake Backend Runs

**FakeBringUp** seeds the inputs required by the supported Qubex tasks. Run it first on a new
chip, or use **Fake Backend Calibration**, which includes bring-up, pulse calibration, and
coherence measurements.

### Targets of the Template

The template's `MUX_IDS` defaults to MUX 0 to 3: qubits 0 to 15. List MUX 0 to 15 to calibrate
all 64 qubits; 16 MUXes run at once and need far more memory for Docker than four. Edit it to
choose other MUXes, use `exclude_qids` to omit qubits, or pass `qids` without `mux_ids` for
individual targets.
The execution dialog can override targets for one run. Previously saved flows retain their
own source and defaults.

## Create a Chip

As a project editor:

1. Open **Chip → Create Chip**.
2. Enter a **Chip ID**.
3. Select **Create Chip**, then **Open template** to continue to a workflow.

Every Fake chip uses the same 64-qubit virtual device and **Square Lattice with MUX** topology.
QDash creates virtual configuration under `CONFIG_PATH` (the example uses
`./config/qubex-config`), preserving an existing chip directory. Creation is blocked if this
configuration tree is not mounted.

For the guided path from chip creation to a result, use [Run Your First Calibration](../first-calibration.md).
