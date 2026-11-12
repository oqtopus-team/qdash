# Quantum Machines Backend

QDash has two Quantum Machines (QM) backends. The `qm` backend runs calibration tasks on a
Quantum Machines OPX, or on the QOP simulator, through a Quantum Orchestration Platform (QOP)
server. The `qm-fake` backend runs the same tasks, and the same QM programs, against a fake
QOP device on the workflow worker, for testing without QM hardware or a QOP server. This is an
initial integration: the only task is **QMAmplitudeRabi**, a one-qubit amplitude Rabi sweep, and
it calibrates one qubit at a time. Qubex and Fake deployments are unaffected and need none of
the packages below; the `fake` backend stays a Qubex simulator and does not run QM tasks.

The Rabi experiment is the one in Quantum Machines' open-source `qualang-tools` package; QDash
configures and runs it rather than reimplementing it. Licenses of these packages:
[Third-Party Licenses](../../reference/third-party-licenses.md).

## Try QMAmplitudeRabi Without Hardware

The `qm-fake` backend runs **QMAmplitudeRabi** exactly as a hardware run does up to the device:
the task builds the Rabi program of `qualang-tools`, executes it, fetches the averaged I/Q
results, and fits them. In place of the OPX, a fake QOP device on the workflow worker checks the
QUA configuration with the QM SDK, reads the amplitudes, shots, elements, and result streams from
the program, and answers with the measurements of a simple qubit model. A program or setting
the fake device does not support fails the task instead of returning made-up data.

The backend needs no OPX, no QOP server, and no network access, but it needs the same `qm`
extra as the `qm` backend (see [Requirements](#requirements)). The standard workflow image does
not include it, so a `qm-fake` run fails there with the install command. A `qm-fake` run does
not compile the program for the OPX or check pulse timing, waveforms, or wiring.

1. Start QDash and create a chip, as for the [Fake backend](./fake-backend.md#create-a-chip). Its
   qubit IDs must include `0`, the qubit of the example.
2. Run the workflow worker from an environment with the `qm` extra installed:

   ```bash
   uv sync --package qdash-workflow --extra qm
   ```

3. Copy the `qm-fake` example to the settings directory of that chip and point it at the QUA
   configuration of the `qm` example:

   ```bash
   mkdir -p config/qm-config/<chip_id>
   cp config/qm-config/example/qua_config.yaml config/qm-config/<chip_id>/
   sed 's|../example/qua_config.yaml|qua_config.yaml|' \
     config/qm-config/example-fake/qm-fake.yaml > config/qm-config/<chip_id>/qm-fake.yaml
   ```

4. Run the task with the backend set to `qm-fake`:

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

5. Open the task result. The figure title reads **QM-FAKE device model, not measured** and shows
   the fitted π scale and R². `qm_pi_amplitude_scale` is listed as
   **Not applied to calibration database**, and the raw I/Q sweep is saved with the result.

In the example the drive pulse of qubit `0` is 0.2 V for 40 ns and a π rotation takes 4.8 V·ns,
so the π scale is 0.6, inside the default sweep from 0 to 1.5. With the default 1000 shots the
fit recovers that value. Fewer shots add noise, and a run with very few shots can fail its R²
check, as a noisy hardware run would.

## Requirements

The QM packages apply to both backends; the QOP server and the chip apply to the `qm` backend.

- A QOP server that the workflow worker can reach, for both modes of the `qm` backend. The QOP simulator runs on
  that server; the SDK has no offline simulator, and QDash neither hosts nor provisions one. To
  test without a server, use the [`qm-fake` backend](#try-qmamplituderabi-without-hardware).
- The workflow `qm` extra, which installs `qm-qua` 1.5.0 and `qualang-tools` 0.23.0:

  ```bash
  uv sync --package qdash-workflow --extra qm
  ```

  The workflow Docker images do not install this extra, so run the worker from an
  environment synchronized this way, or build a custom worker image that installs it. Without
  the packages, a task on the `qm` or `qm-fake` backend fails when it connects and reports the
  command to run.
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
| `connection.host` | QOP server host | Required |
| `connection.port` | QOP server port | SDK default |
| `connection.cluster_name` | QOP cluster name | SDK default |
| `connection.timeout` | Connection timeout in seconds | SDK default |
| `simulation.duration_ns` | Program time to simulate, a multiple of 4 ns and at most 1000000 | `40000` |
| `qubits.<qid>.qubit_element` / `qubit_operation` | QUA element and operation that drive the qubit; the Rabi sweep scales this operation's amplitude | Required |
| `qubits.<qid>.readout_element` / `readout_operation` | QUA element and measurement operation of the readout resonator | Required |
| `qubits.<qid>.outputs` | One or two outputs of the readout element | `[out1, out2]` |
| `qubits.<qid>.integration_weights` | Four integration weights for two outputs, two for one output | `[cos, sin, minus_sin, cos]` |
| `qua_config_file` or `qua_config` | QUA configuration, as a JSON or YAML file relative to `qm.yaml` or inline | Required |

QDash checks the file when the task connects: an unknown key, a missing mode or `connection`, or
an element or operation that the QUA configuration does not define fails the task before any
program runs.

A `mode: mock` or `fake` value, or a `mock` section, fails the task with a pointer to the
`qm-fake` backend; the `qm` backend never falls back to the fake device.

## Write the qm-fake Settings File

The `qm-fake` backend reads `config/qm-config/<chip_id>/qm-fake.yaml`, which can sit next to the
`qm.yaml` of the same chip. Set `QDASH_QM_FAKE_CONFIG` to read another path; `QDASH_QM_CONFIG`
does not apply to it. The file takes the QUA configuration and `qubits` entries in the same form
as `qm.yaml`, checked by the same rules, plus a `device` entry for every qubit; `"0": {}` uses
every default:

| Setting | Meaning | Default |
| --- | --- | --- |
| `qua_config_file` or `qua_config` | QUA configuration, as in `qm.yaml`; point it at the same file | Required |
| `qubits.<qid>.*` | Elements, operations, outputs, and integration weights, as in `qm.yaml` | Required |
| `seed` | Seed of the noise; a fixed seed repeats the same results in every session | New noise each session |
| `qop_version` | QOP major version, `2` or `3`, whose rules the SDK checks the QUA configuration against | `2` |
| `device.<qid>.pi_pulse_area` | Area of the drive pulse envelope, in V·ns, that rotates the qubit by π | `4.8` |
| `device.<qid>.ground_iq` | Readout signal (I, Q) of the ground state, in V | `[0.010, 0.002]` |
| `device.<qid>.excited_iq` | Readout signal (I, Q) of the excited state, in V | `[0.0025, 0.015]` |
| `device.<qid>.noise_per_shot` | Gaussian noise per quadrature on every measurement, in V | `0.01` |

Settings that reach a QOP server (`mode`, `connection`, and `simulation`) fail the task, so a
copied `qm.yaml` cannot connect the `qm-fake` backend to a server. A file without a `device`
entry for a listed qubit, or two qubits that share a drive or readout element, also fails.

The fake device models an ideal qubit. Each played pulse rotates the qubit by π times the
amplitude scale times the pulse's envelope area, divided by `pi_pulse_area`, so changing the
drive waveform in the QUA configuration moves the π scale. Each measurement finds the qubit
excited with the probability that rotation gives, returns the ground or excited readout signal
plus noise, and resets the qubit. The readout signal is demodulated with the integration weights
of the QUA configuration. The model has no decoherence, leakage, pulse distortion, or timing,
and `cooldown_time` has no effect on it. The fake device runs only the statements of the
amplitude Rabi program; any other statement or stream processing fails the task.

## Modes and the qm-fake Backend

The mode of the `qm` backend is fixed per settings file; QDash never chooses it. The `qm-fake`
backend is selected by name and has no mode.

| | `qm`, `hardware` | `qm`, `simulator` | `qm-fake` |
| --- | --- | --- | --- |
| Runs the program on | The OPX | The QOP simulator | A fake QOP device on the worker, using a qubit model |
| Result | Averaged I/Q response for each amplitude scale | Simulated controller output waveforms | Averaged I/Q response of the model for each amplitude scale |
| Figure | Response with its cosine fit and R² | Output waveforms, titled **SIMULATED waveforms** | Response with its cosine fit and R², titled **QM-FAKE device model, not measured** |
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
