# Qibocal Emulator Backend

The Qibocal backend runs Qibocal's Rabi amplitude measurement on one emulated qubit, so you can
try QDash runs, task history, figures, and raw data with an upstream calibration library and no
hardware. Its results are synthetic and measurement-only: QDash stores them in task history, and
no setting makes them the current calibration values.

The deployment has one task, **QibocalRabiAmplitude**, on one qubit, `0`. The emulator has no
other qubits, MUXes, or couplings, and QDash does not present it as a larger device. Use the
[Fake backend](./fake-backend.md) to try multi-qubit workflows without hardware.

## Start a Qibocal Deployment

Create `.env` from the Qibocal example, set the administrator password as
[Setup](../setup.md#configure-shared-deployment-settings) describes, and start QDash:

```bash
cp .env.example.qibocal .env
task deploy-local-qibocal
```

`cp` replaces an existing `.env`. Stop a deployment that runs from this checkout before replacing
its `.env`, because Compose reads the project name from `.env`. The example sets these values; the
other values match `.env.example`:

| Variable | Value in `.env.example.qibocal` |
| --- | --- |
| `ENV` | `dev-qibocal`, the Docker Compose project name |
| `DEFAULT_BACKEND` | `qibocal` |
| `COMPOSE_FILE` | `compose.yaml:compose.qibocal.yaml`, so every `docker compose` command includes the Qibocal overlay |
| `UI_PORT` | `5794`; the Fake and Qubex examples use `5714` |
| `POSTGRES_DATA_PATH` / `MONGO_DATA_PATH` / `CALIB_DATA_PATH` | `./qibocal_data/postgres`, `./qibocal_data/mongo`, and `./qibocal_data/calib`, instead of the directories of the other examples |

The overlay `compose.qibocal.yaml` adds the Qibocal runner to the workflow worker image only; it
makes that image about 1.35 GB larger, and Fake and Qubex deployments never build it. Because
`.env` sets `COMPOSE_FILE`, `docker compose up -d --build` and the commands in
[Operations](../operations.md) work unchanged; open QDash at <http://localhost:5794/login>.
Stop it with `task deploy-local-qibocal-down` or `docker compose down`.

`ENV` and the data directories keep the containers, named volumes, databases, and calibration
data of a Qibocal deployment apart from those of a Fake or Qubex deployment, including when one
checkout switches between the examples. Both deployments still use what Compose mounts from the
checkout: the source directories and `./config`, which holds the Qibocal runner settings and
platform. A checkout holds one `.env`, so run a Qibocal deployment beside another one from a
separate checkout, as [Run Several Deployments on One Host](../setup.md#run-several-deployments-on-one-host)
describes; its `UI_PORT` already differs from the default `5714`.

The Qibocal deployment needs no backend configuration and no Qubex configuration tree.

## Create the Emulator Chip

Create the chip after signing in as a project editor. [Run Your First Calibration](../first-calibration.md)
does this from **Home**; the guide then opens the **Qibocal Emulator Rabi Amplitude** template.
To add a chip directly:

1. Open **Chip** and select **Create Chip**.
2. Enter a **Chip ID**. The dialog shows **Qibocal emulator qubit** with the **Qibocal emulator
   backend**, the one-qubit topology, and **1 qubit**; there is nothing to choose.
3. Select **Create Chip**.
4. Select **Open template** in the confirmation to open the **Qibocal Emulator Rabi Amplitude**
   template in **New Flow** with the new chip selected.

QDash writes no configuration files for this chip; the emulator reads its own platform.

## Run the Measurement

Run the template as a workflow: save it in **New Flow** and select **Execute**, as in
[Run a Workflow](../running-calibrations.md#run-a-workflow). It runs **QibocalRabiAmplitude** on qubit `0`.

To run the task alone, follow [Run One Task](../running-calibrations.md#run-one-task) with the
task **QibocalRabiAmplitude**, the emulator chip, and qubit `0`. **Update calibration values**
has no effect for this task.

| Run parameter | Default | Meaning |
| --- | --- | --- |
| `min_amp` | `0.01` | First drive amplitude; must be greater than 0 |
| `max_amp` | `0.5` | Last drive amplitude |
| `step_amp` | `0.01` | Amplitude step; the sweep needs at least five points |
| `nshots` | `1024` | Shots per amplitude |
| `relaxation_time` | `0.0` | Wait between shots, in ns |
| `seed` | `1234` | Random seed; the same seed gives the same result |

A run on any qubit other than `0` fails before the measurement starts. A run with the default
parameters takes a few seconds; a finer sweep takes longer, up to the runner timeout of 600 s.

## Read the Result

The result appears in **Execution** and in task history like any other task result:

- **qibocal_pi_amplitude**, the fitted pi-pulse amplitude, and **qibocal_rabi_chi2**, the reduced
  chi-squared of the fit, each marked as not applied to the calibration values, with the reason
  and the run's provenance: emulator, platform, seed, and library versions.
- Qibocal's own figure, titled as synthetic emulator data.
- Two raw-data files: the excited-state probability and its error against amplitude.

A run whose fit fails, or whose amplitude falls outside the sweep, fails and keeps its figure and
raw data. Cancelling a run stops the emulator within seconds.

How this works: [Qibocal Emulator Backend](../../developer-guide/workflow/qibocal-backend.md).
