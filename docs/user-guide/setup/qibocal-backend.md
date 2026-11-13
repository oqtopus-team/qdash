# Qibocal Emulator Backend

The Qibocal backend runs Qibocal's Rabi amplitude measurement on one emulated qubit, so you can
try QDash runs, task history, figures, and raw data with an upstream calibration library and no
hardware. Its results are synthetic and measurement-only: QDash stores them in task history, and
no setting makes them the current calibration values.

The deployment has one task, **QibocalRabiAmplitude**, on one qubit, `0`. The emulator has no
other qubits, MUXes, or couplings, and QDash does not present it as a larger device. Use the
[Fake backend](./fake-backend.md) to try multi-qubit workflows without hardware.

## Start a Qibocal Deployment

Start from the environment file of [Setup](../setup.md#create-the-environment-file), then start
QDash with the Qibocal overlay. The overlay adds the Qibocal runner to the workflow worker image
only; it makes that image about 1.35 GB larger, and Fake and Qubex deployments never build it.

```bash
cp .env.example .env
task deploy-local-qibocal
```

`task deploy-local-qibocal` starts the Compose project `dev-qibocal` with `DEFAULT_BACKEND=qibocal`.
Without Go Task, set the same values and pass both Compose files:

```bash
ENV=dev-qibocal DEFAULT_BACKEND=qibocal \
  docker compose -f compose.yaml -f compose.qibocal.yaml up -d --build
```

The values from the shell take precedence over `.env`. To keep a Qibocal deployment apart from
another one on the same host, also give it its own `UI_PORT` and data directories, as
[Run Several Deployments on One Host](../setup.md#run-several-deployments-on-one-host) describes.

Stop it with `task deploy-local-qibocal-down`, or with the same `ENV` and both Compose files:

```bash
ENV=dev-qibocal docker compose -f compose.yaml -f compose.qibocal.yaml down
```

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
