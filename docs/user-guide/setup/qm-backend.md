# Quantum Machines Backend

QDash has two Quantum Machines (QM) backends. The `qm` backend runs calibration tasks on a
Quantum Machines OPX, or on the QOP simulator, through a Quantum Orchestration Platform (QOP)
server. The `qm-fake` backend runs the same tasks against a synthetic qubit response that QDash
computes locally, for testing without QM hardware. This is an initial integration: the only task
is **QMAmplitudeRabi**, a one-qubit amplitude Rabi sweep, and it calibrates one qubit at a time.
Qubex and Fake deployments are unaffected and need none of the packages below; the `fake`
backend stays a Qubex simulator and does not run QM tasks.

The Rabi experiment is the one in Quantum Machines' open-source `qualang-tools` package; QDash
configures and runs it rather than reimplementing it. Licenses of these packages:
[Third-Party Licenses](../../reference/third-party-licenses.md).

## Try QMAmplitudeRabi Without Hardware

The `qm-fake` backend runs **QMAmplitudeRabi** against a synthetic qubit response that QDash
computes on the workflow worker. It needs no OPX, no QOP server, no QM account, no network
access, and none of the Quantum Machines packages, so it runs on the standard workflow image. A
`qm-fake` run uses the task code of the `qm` backend and goes through the same fit, validation,
figure, raw data, and task history as a hardware run; only the device response is synthetic. It
checks QDash's pipeline and analysis; it does not compile a QUA program or check OPX pulse
timing or wiring.

1. Start QDash and create a chip, as for the [Fake backend](./fake-backend.md#create-a-chip). Its
   qubit IDs must include `0`, the qubit of the example.
2. Copy the `qm-fake` example to the settings directory of that chip:

   ```bash
   mkdir -p config/qm-config/<chip_id>
   cp config/qm-config/example-fake/qm-fake.yaml config/qm-config/<chip_id>/
   ```

3. Run the task with the backend set to `qm-fake`:

   ```python
   from qdash.workflow import TaskCall
   from qdash.workflow.service import CalibService, resolve_calib_context
   from qdash.workflow.service.steps import CustomOneQubit
   from qdash.workflow.service.targets import QubitTargets

   context = resolve_calib_context("alice", "<chip_id>", backend="qm-fake")
   CalibService.from_context(context).run(
       QubitTargets(qids=["0"]),
       steps=[CustomOneQubit(step_name="rabi", tasks=[TaskCall(name="QMAmplitudeRabi")])],
   )
   ```

4. Open the task result. The figure title reads **QM-FAKE synthetic response, not measured** and shows
   the fitted π scale and R². `qm_pi_amplitude_scale` is listed as
   **Not applied to calibration database**, and the raw I/Q sweep is saved with the result.

The example sets a π scale of 0.6 for qubit `0` and 0.85 for qubit `1`, inside the default sweep
from 0 to 1.5. With the default 1000 shots the fit recovers the configured value. Fewer shots add
noise, and a run with very few shots can fail its R² check, as a noisy hardware run would.

## Requirements

These requirements apply to the `qm` backend; the `qm-fake` backend needs only its settings file.

- A QOP server that the workflow worker can reach, or a QM SaaS account for the QM cloud
  simulator. The QOP simulator runs on a server; the SDK has no offline simulator.
- The workflow `qm` extra, which installs `qm-qua` 1.5.0 and `qualang-tools` 0.23.0. For the
  cloud simulator, install the `qm-cloud` extra instead; it adds `qm-saas` 1.2.0, the oldest
  client version the service accepts:

  ```bash
  uv sync --package qdash-workflow --extra qm        # QOP server
  uv sync --package qdash-workflow --extra qm-cloud  # QM cloud simulator
  ```

  The workflow Docker image does not install these extras, so run the worker from an
  environment synchronized this way. Without them, a QM task fails when it connects and reports
  the command to run.
- A chip in QDash whose qubit IDs match the `qubits` keys of the settings file.

## Write the Settings File

The worker reads `config/qm-config/<chip_id>/qm.yaml`, where `<chip_id>` is the QDash chip ID.
Set `QDASH_QM_CONFIG` to read another path. For hardware or simulator mode, start from the
example, which pairs the settings with a minimal one-qubit QUA configuration:

```bash
cp -r config/qm-config/example config/qm-config/<chip_id>
```

| Setting | Meaning | Default |
| --- | --- | --- |
| `mode` | `hardware` or `simulator`; see [Modes and the qm-fake Backend](#modes-and-the-qm-fake-backend) | Required |
| `connection.host` | QOP server host; set `connection` or `cloud`, not both | Required with `connection` |
| `connection.port` | QOP server port | SDK default |
| `connection.cluster_name` | QOP cluster name | SDK default |
| `connection.timeout` | Connection timeout in seconds | SDK default |
| `cloud.qop_version` | QOP version of the cloud simulator, such as `v2_6_0`; see [Use the QM Cloud Simulator](#use-the-qm-cloud-simulator) | Required with `cloud` |
| `cloud.email_env` / `cloud.password_env` | Names of the environment variables that hold the QM SaaS email and password | `QM_SAAS_EMAIL` / `QM_SAAS_PASSWORD` |
| `cloud.host` / `cloud.port` | QM SaaS service address | `qm-saas.quantum-machines.co` / `443` |
| `simulation.duration_ns` | Program time to simulate, a multiple of 4 ns and at most 1000000 | `40000` |
| `qubits.<qid>.qubit_element` / `qubit_operation` | QUA element and operation that drive the qubit; the Rabi sweep scales this operation's amplitude | Required |
| `qubits.<qid>.readout_element` / `readout_operation` | QUA element and measurement operation of the readout resonator | Required |
| `qubits.<qid>.outputs` | One or two outputs of the readout element | `[out1, out2]` |
| `qubits.<qid>.integration_weights` | Four integration weights for two outputs, two for one output | `[cos, sin, minus_sin, cos]` |
| `qua_config_file` or `qua_config` | QUA configuration, as a JSON or YAML file relative to `qm.yaml` or inline | Required |

QDash checks the file when the task connects: an unknown key, a missing mode, both or neither of
`connection` and `cloud`, or an element or operation that the QUA configuration does not define
fails the task before any program runs.

A `mode: mock` or `fake` value, or a `mock` section, fails the task with a pointer to the
`qm-fake` backend; the `qm` backend never falls back to a synthetic response.

## Write the qm-fake Settings File

The `qm-fake` backend reads `config/qm-config/<chip_id>/qm-fake.yaml`, which can sit next to the
`qm.yaml` of the same chip. Set `QDASH_QM_FAKE_CONFIG` to read another path; `QDASH_QM_CONFIG`
does not apply to it. The file holds a seed and one entry per QDash qubit ID; `"0": {}` uses
every default:

| Setting | Meaning | Default |
| --- | --- | --- |
| `seed` | Seed of the noise; a fixed seed repeats the same results in every session | New noise each session |
| `qubits.<qid>.pi_amplitude_scale` | Amplitude scale of a π rotation, greater than 0 and less than 2 | `0.6` |
| `qubits.<qid>.iq_offset` | Averaged I/Q point of the ground state, in V | `[0.010, 0.002]` |
| `qubits.<qid>.contrast` | Distance from the ground to the excited I/Q point, in V | `0.015` |
| `qubits.<qid>.phase_deg` | Direction of the excited point from the ground point, in degrees | `120.0` |
| `qubits.<qid>.noise_per_shot` | Single-shot noise per quadrature, in V; the averaged noise is this value divided by √`shots` | `0.01` |

Settings that reach a QOP server (`mode`, `connection`, `cloud`, `simulation`, `qua_config`, and
`qua_config_file`) fail the task, so a copied `qm.yaml` cannot connect the `qm-fake` backend to a
server or the cloud. A qubit that the file does not list fails the task and names the
configured qubits.

The synthetic response is an ideal two-level qubit: the readout point moves along a straight
line from the ground point toward the excited point as `(1 - cos(π a / pi_amplitude_scale)) / 2`,
plus Gaussian noise. It has no decoherence, leakage, or pulse distortion, and `cooldown_time` has
no effect on it.

## Use the QM Cloud Simulator

The QM cloud simulator (QM SaaS) runs the QOP simulator on Quantum Machines' servers, so
simulator mode works without a QOP server of your own. It needs QM SaaS credentials from
Quantum Machines and outgoing access to ports 443 and 9510.

1. Install the `qm-cloud` extra, as in [Requirements](#requirements).
2. In `qm.yaml`, set `mode: simulator` and replace the `connection` block with a `cloud` block:

   ```yaml
   mode: simulator
   cloud:
     qop_version: v2_6_0
   ```

3. Export the credentials in the environment of the workflow worker. Keep them out of `qm.yaml`
   and out of version control:

   ```bash
   export QM_SAAS_EMAIL=<email>
   export QM_SAAS_PASSWORD=<password>
   ```

`qop_version` is required: QDash never picks the latest version, which could change the
simulated controller under an existing QUA configuration. A QOP 2 version simulates OPX+
controllers, as in the example configuration; a QOP 3 version simulates OPX1000 controllers and
needs a QUA configuration whose controllers declare `fems`. QDash rejects a version that does not
match the configuration or that the service does not offer, and lists the offered versions.
QOP 3 instances use the service's default cluster of OPX1000 controllers.

The `cloud` block is accepted only in simulator mode. When the task connects, QDash starts one
simulator instance and closes it when the session ends or the connection fails; it never closes
other instances of the account. The service limits each account to three instances and closes
an instance after 15 minutes; QDash starts a new instance when the previous one has expired.
QDash replaces credential values in the QM SaaS client's log messages. SDK exceptions and
server responses can contain additional details that this filter does not redact; review
tracebacks before sharing them.

## Modes and the qm-fake Backend

The mode of the `qm` backend is fixed per settings file; QDash never chooses it. The `qm-fake`
backend is selected by name and has no mode.

| | `qm`, `hardware` | `qm`, `simulator` | `qm-fake` |
| --- | --- | --- | --- |
| Runs the program on | The OPX | The QOP simulator | No program; QDash computes a synthetic response |
| Result | Averaged I/Q response for each amplitude scale | Simulated controller output waveforms | Synthetic averaged I/Q response for each amplitude scale |
| Figure | Response with its cosine fit and R² | Output waveforms, titled **SIMULATED waveforms** | Response with its cosine fit and R², titled **QM-FAKE synthetic response, not measured** |
| Raw data | I/Q sweep | One waveform per analog output | I/Q sweep, labelled as `qm-fake` |
| Calibration value | `qm_pi_amplitude_scale`, written to the calibration database | None | `qm_pi_amplitude_scale` in the task result only, never written to the calibration database |

Only hardware mode writes calibration values. Simulator and `qm-fake` runs never replace a value
measured on hardware, even when the run forces parameter updates.

The simulator reproduces the OPX outputs, which verifies pulse timing and amplitudes; it does not
model the qubit, so a simulated run never yields a Rabi response or a calibration value. A
simulated run fails when no analog output produced a non-zero sample within
`simulation.duration_ns`.

## Run QMAmplitudeRabi

Run the task like any other catalog task, with the backend set to `qm`. In a workflow, pass the
backend to the context:

```python
from qdash.workflow import TaskCall
from qdash.workflow.service import CalibService, resolve_calib_context
from qdash.workflow.service.steps import CustomOneQubit
from qdash.workflow.service.targets import QubitTargets

context = resolve_calib_context("alice", "my-opx-chip", backend="qm")
CalibService.from_context(context).run(
    QubitTargets(qids=["0"]),
    steps=[CustomOneQubit(step_name="rabi", tasks=[TaskCall(name="QMAmplitudeRabi")])],
)
```

To make `qm` the deployment default instead, set `DEFAULT_BACKEND=qm` in `.env`.

In simulator mode, run the short sweep that `simulator_run_parameters()` returns: four amplitude
scales from 0 to 1.5, three of which drive the qubit, one shot, and a 1 µs cooldown. With the
example QUA configuration one sweep lasts about 5 µs, inside the default 40 µs simulation:

```python
from qdash.workflow.calibtasks.qm import simulator_run_parameters

TaskCall(name="QMAmplitudeRabi", run=simulator_run_parameters())
```

The task defaults below describe a hardware calibration that lasts seconds. Before a simulation
starts, QDash estimates one sweep as the number of points times the drive pulse, readout pulse,
and cooldown lengths, and fails the run when that estimate plus 25% and 1 µs of headroom exceeds
`simulation.duration_ns`. The simulator
then cuts the program off at `simulation.duration_ns`. The preflight check estimates that one
sweep fits; it does not verify that every amplitude appears in the returned waveforms. The
figure title reports an estimated iteration count. Inspect the waveforms to confirm coverage. A
simulation checks waveforms; only a hardware run averages the shots into a measurement.

| Run parameter | Meaning | Default |
| --- | --- | --- |
| `amplitude_scale_range` | Evenly spaced, increasing scale factors for the qubit operation amplitude, `(start, stop, points)`, within [-2, 2); negative values are allowed | `(0.0, 1.5, 51)` |
| `shots` | Averaging iterations | `1000` |
| `cooldown_time` | Wait after each measurement in ns, a multiple of 4 and at least 16 | `100000` |

In hardware mode and on the `qm-fake` backend the task projects the I/Q response on its direction of largest
variance and fits `offset + A cos(2π f a)` over the amplitude scale `a`. It reports
`qm_pi_amplitude_scale`, half the fitted period: the scale factor of the configured operation
that gives a π rotation.
The response depends only on the magnitude of `a`, so the π scale is accepted when it lies
within the magnitudes the sweep covers, ends included: 0.5 to 1.5 for a sweep from 0.5 to 1.5 or
from -1.5 to -0.5, and 0 to 1 for a sweep from -1 to 1. The run fails, keeping its figure, when
the fit R² is below 0.7 or the π scale lies outside that interval. The value is relative to the
operation's amplitude in your QUA configuration; QDash does not change that configuration.
