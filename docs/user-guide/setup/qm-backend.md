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

3. Copy the example QM configuration and the example settings to the directories of that
   chip, and point `qm.yaml` at the copied configuration:

   ```bash
   cp -r config/qm-config/example config/qm-config/<chip_id>
   mkdir -p config/qm-backend/<chip_id>
   cp config/qm-backend/example/qm-fake.yaml config/qm-backend/<chip_id>/
   sed 's|qm-config/example/|qm-config/<chip_id>/|' \
     config/qm-backend/example/qm.yaml > config/qm-backend/<chip_id>/qm.yaml
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

## Prepare the QM Configuration

Both backends run your native Quantum Machines configuration: a `configuration.py` that defines
a module-level `config` dictionary, the one you pass to `QuantumMachinesManager.open_qm(config)`
([QUA configuration](https://docs.quantum-machines.co/latest/docs/Introduction/config/)). QDash
reads `config` unchanged, so integer port keys, tuples, NumPy arrays, and waveforms computed in
Python keep the values your other QM scripts see with `from configuration import config`. QDash
supports the single-dictionary configuration that `qm-qua` 1.5.0 takes; it adds no keys of its
own to it.

Keep the file in `config/qm-config/<chip_id>/`. The example in `config/qm-config/example/`
defines a minimal one-qubit configuration for an OPX with controller `con1`. The configuration
can import helper modules from its own directory, such as `from pulses import gaussian`; give
them names that no installed package uses. Helpers of different chips do not affect each other.

The configuration is Python, and the workflow worker executes it with the worker's permissions
when a `qm` or `qm-fake` task starts. Only put files you trust in `config/qm-config/`. QDash
never runs code under `if __name__ == "__main__":`, so keep anything that connects to a QOP
server, runs a program, or plots there or in another script. A file that does not define
`config` as a dictionary, or that raises an error, fails the task with that error.

## Write the Settings File

QDash keeps its own settings for a chip in `config/qm-backend/<chip_id>/qm.yaml`, separate from
the QM configuration. Set `QDASH_QM_SETTINGS` to read another path. A missing file fails the
task; QDash does not look elsewhere. For hardware or simulator mode, start from the example and
point `qm_config_file` at the chip's configuration:

```bash
mkdir -p config/qm-backend/<chip_id>
sed 's|qm-config/example/|qm-config/<chip_id>/|' \
  config/qm-backend/example/qm.yaml > config/qm-backend/<chip_id>/qm.yaml
```

| Setting | Meaning | Default |
| --- | --- | --- |
| `mode` | `hardware` or `simulator`; see [Modes and the qm-fake Backend](#modes-and-the-qm-fake-backend) | Required |
| `connection.host` | QOP server host | Required |
| `connection.port` | QOP server port | SDK default |
| `connection.cluster_name` | QOP cluster name | SDK default |
| `connection.timeout` | Connection timeout in seconds | SDK default |
| `simulation.duration_ns` | Program time to simulate, a multiple of 4 ns and at most 1000000 | `40000` |
| `qm_config_file` | Path of the chip's `configuration.py`, relative to `qm.yaml`, such as `../../qm-config/<chip_id>/configuration.py` | Required |
| `qubits.<qid>.qubit_element` / `qubit_operation` | Element and operation in `config` that drive the qubit; the Rabi sweep scales this operation's amplitude | Required |
| `qubits.<qid>.readout_element` / `readout_operation` | Element and measurement operation in `config` of the readout resonator | Required |
| `qubits.<qid>.outputs` | One or two outputs of the readout element | `[out1, out2]` |
| `qubits.<qid>.integration_weights` | Four integration weights for two outputs, two for one output | `[cos, sin, minus_sin, cos]` |

QDash checks the file when the task connects: an unknown key, a missing mode or `connection`, or
an element or operation that `config` does not define fails the task before any program runs.

A `mode: mock` or `fake` value, or a `mock` section, fails the task with a pointer to the
`qm-fake` backend; the `qm` backend never falls back to the fake device.

Settings written for an earlier build of this integration fail with a message that names the
change: a `qua_config_file` or `qua_config` key, a `qm.yaml` or `qm-fake.yaml` under
`config/qm-config/<chip_id>/`, and the `QDASH_QM_CONFIG` and `QDASH_QM_FAKE_CONFIG` variables. To
migrate, write the QUA configuration as `config` in `configuration.py`, move the settings files
to `config/qm-backend/<chip_id>/`, replace `qua_config_file` with `qm_config_file`, and rename
the variables to `QDASH_QM_SETTINGS` and `QDASH_QM_FAKE_SETTINGS`.

## Write the qm-fake Settings File

The `qm-fake` backend reads `config/qm-backend/<chip_id>/qm-fake.yaml`. Set
`QDASH_QM_FAKE_SETTINGS` to read another path; `QDASH_QM_SETTINGS` does not apply to it. The file
names the chip's `qm.yaml`, and the fake device uses the same `configuration.py` and `qubits`
entries from it, checked by the same rules. It ignores the `mode`, `connection`, and
`simulation` of `qm.yaml`, so `qm-fake` needs no reachable QOP server. The file adds a `device`
entry for every qubit; `"0": {}` uses every default:

| Setting | Meaning | Default |
| --- | --- | --- |
| `qm_settings_file` | Path of the chip's `qm.yaml`, relative to `qm-fake.yaml` | Required |
| `seed` | Seed of the noise; a fixed seed repeats the same results in every session | New noise each session |
| `qop_version` | QOP major version, `2` or `3`, whose rules the SDK checks `config` against | `2` |
| `device.<qid>.pi_pulse_area` | Area of the drive pulse envelope, in V·ns, that rotates the qubit by π | `4.8` |
| `device.<qid>.ground_iq` | Readout signal (I, Q) of the ground state, in V | `[0.010, 0.002]` |
| `device.<qid>.excited_iq` | Readout signal (I, Q) of the excited state, in V | `[0.0025, 0.015]` |
| `device.<qid>.noise_per_shot` | Gaussian noise per quadrature on every measurement, in V | `0.01` |

Settings that reach a QOP server (`mode`, `connection`, and `simulation`) fail the task when
they appear in `qm-fake.yaml`, so a copied `qm.yaml` cannot connect the `qm-fake` backend to a
server; `qubits` and `qm_config_file` there fail too, because they belong in `qm.yaml`. A file
without a `device` entry for a listed qubit, or two qubits that share a drive or readout
element, also fails.

The fake device models an ideal qubit. Each played pulse rotates the qubit by π times the
amplitude scale times the pulse's envelope area, divided by `pi_pulse_area`, so changing the
drive waveform in `config` moves the π scale. Each measurement finds the qubit
excited with the probability that rotation gives, returns the ground or excited readout signal
plus noise, and resets the qubit. The readout signal is demodulated with the integration weights
of `config`. The model has no decoherence, leakage, pulse distortion, or timing,
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
