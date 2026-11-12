"""Amplitude Rabi on a Quantum Machines OPX, using the qualang-tools Rabi experiment."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any, ClassVar

import numpy as np
import plotly.graph_objects as go

from qdash.common.raw_data import PreFitRawData
from qdash.datamodel import sweep as sweep_values
from qdash.datamodel.task import InputParameterSpec, OutputParameterSpec, RunParameterSpec
from qdash.workflow.calibtasks.base import PostProcessResult, PreProcessResult, RunResult
from qdash.workflow.calibtasks.qm.base import QMTask
from qdash.workflow.calibtasks.qm.rabi_experiment import (
    AMPLITUDE_SCALE_MAX,
    RabiFit,
    RabiIQResult,
    RabiSimulationResult,
    RabiSweep,
    covered_magnitude_range,
    fit_amplitude_rabi,
    project_iq,
    run_rabi_on_fake,
    run_rabi_on_hardware,
    simulate_rabi,
)
from qdash.workflow.engine.backend.qm_fake import QMFakeSession

if TYPE_CHECKING:
    from qdash.workflow.engine.backend.qm import QMBackend
    from qdash.workflow.engine.backend.qm_fake import QMFakeBackend

SIMULATION_NOTICE = (
    "QOP simulator output: controller waveforms and timing only. "
    "The simulator does not model the qubit, so no Rabi response or calibration value exists."
)
FAKE_NOTICE = (
    "QM-FAKE: synthetic response generated locally by QDash, not measured on a device. "
    "The value is kept in the run history and never replaces a calibration value."
)
FIGURE_MODE_LABEL = {
    "hardware": "hardware",
    "fake": "QM-FAKE synthetic response, not measured",
}

# Relative slack on the swept interval, so a fit at the first or last point is accepted
# despite floating-point noise.
BOUNDARY_TOLERANCE = 1e-6


def simulator_run_parameters() -> dict[str, Any]:
    """Short QMAmplitudeRabi run for the QOP simulator, as ``TaskCall.run`` takes it.

    Four amplitude scales (0, 0.5, 1.0, 1.5; three drive the qubit), one shot and a
    1 us cooldown. With the example QUA configuration one sweep lasts about 5 us, well
    inside the default 40 us ``simulation.duration_ns``. The task defaults (51 points,
    1000 shots, 100 us cooldown) describe a hardware calibration lasting seconds and
    do not fit a simulation.
    """
    return {
        "amplitude_scale_range": sweep_values.linspace(0.0, 1.5, 4),
        "shots": 1,
        "cooldown_time": 1_000,
    }


class QMAmplitudeRabi(QMTask):
    """Sweep the drive amplitude scale on a Quantum Machines OPX and fit the Rabi response.

    The QUA program is the Rabi experiment of qualang-tools ``QUA_calibrations``: the
    configured qubit operation is played with ``amp(a)`` for each amplitude scale ``a``,
    then the resonator is measured with dual demodulation. In hardware mode the
    averaged I/Q response is projected on its principal axis and fitted with a cosine
    to give the amplitude scale of a pi rotation. On the qm-fake backend a local
    synthetic I/Q response replaces the measurement and goes through the same fit; its
    result is labelled as fake and stays in the run history. In simulator mode the task records
    the simulated controller outputs and publishes no calibration value; use
    ``simulator_run_parameters()`` for a run short enough to simulate.

    Sweeps may be signed. The response depends on ``|a|`` only, so a fitted pi scale is
    accepted when it lies within the magnitudes the sweep covers.
    """

    name: str = "QMAmplitudeRabi"
    task_type: str = "qubit"
    timeout: int = 60 * 30

    input_spec: ClassVar[dict[str, InputParameterSpec]] = {}
    run_spec: ClassVar[dict[str, RunParameterSpec]] = {
        "amplitude_scale_range": RunParameterSpec(
            unit="a.u.",
            value_type="np.linspace",
            default=(0.0, 1.5, 51),
            description=(
                "Scale factors applied to the configured qubit operation amplitude, "
                "within the QUA amp() range [-2, 2)"
            ),
        ),
        "shots": RunParameterSpec(
            unit="a.u.",
            value_type="int",
            default=1000,
            description="Number of averaging iterations",
        ),
        "cooldown_time": RunParameterSpec(
            unit="ns",
            value_type="int",
            default=100_000,
            description="Wait after each measurement, a multiple of 4 ns and at least 16 ns",
        ),
    }
    output_spec: ClassVar[dict[str, OutputParameterSpec]] = {
        "qm_pi_amplitude_scale": OutputParameterSpec(
            unit="a.u.",
            description=(
                "Amplitude scale of the configured QM qubit operation that gives a pi "
                "rotation; written to the calibration database in hardware mode only"
            ),
        ),
    }

    def preprocess(self, backend: QMBackend | QMFakeBackend, qid: str) -> PreProcessResult:
        """The task has no calibration inputs; QM settings carry the pulse definitions."""
        return PreProcessResult(input_parameters=self.input_parameters)

    def sweep(self) -> RabiSweep:
        """Validated sweep built from the run parameters."""
        return RabiSweep.create(
            amplitude_scales=self.run_parameters["amplitude_scale_range"].get_value(),
            shots=self.run_parameters["shots"].get_value(),
            cooldown_ns=self.run_parameters["cooldown_time"].get_value(),
        )

    def run(self, backend: QMBackend | QMFakeBackend, qid: str) -> RunResult:
        """Run the sweep on hardware, the simulator or the qm-fake device, as the backend selects."""
        sweep = self.sweep()
        session = backend.get_instance()
        if isinstance(session, QMFakeSession):
            measurement = run_rabi_on_fake(session, qid, sweep)
        elif session.is_simulator:
            # No r2: the simulator returns waveforms, not a response to fit.
            return RunResult(raw_result=simulate_rabi(session, qid, sweep))
        else:
            measurement = run_rabi_on_hardware(session, qid, sweep)
        fit = fit_amplitude_rabi(measurement.amplitude_scales, project_iq(measurement.iq))
        return RunResult(raw_result={"measurement": measurement, "fit": fit}, r2={qid: fit.r2})

    def extract_raw_data(self, run_result: RunResult) -> list[Any]:
        """Persist the I/Q sweep (measured or fake), or the simulated controller outputs."""
        raw = run_result.raw_result
        if isinstance(raw, RabiSimulationResult):
            artifacts: list[Any] = []
            for port, samples in raw.analog.items():
                rate = raw.analog_sampling_rate.get(port, 1e9)
                artifacts.append(
                    PreFitRawData(
                        target=port,
                        data=np.asarray(samples),
                        axes={"time_ns": np.arange(len(samples)) * 1e9 / rate},
                        source_type="qm.simulator.analog_samples",
                    )
                )
            return artifacts
        measurement: RabiIQResult = raw["measurement"]
        return [
            PreFitRawData(
                target=measurement.target,
                data=measurement.iq,
                axes={"amplitude_scale": measurement.amplitude_scales},
                source_type=measurement.source_type,
            )
        ]

    def postprocess(
        self,
        backend: QMBackend | QMFakeBackend,
        execution_id: str,
        run_result: RunResult,
        qid: str,
    ) -> PostProcessResult:
        """Report the fitted pi amplitude scale of a hardware or fake response.

        The output is produced for both; ``BackendSaver`` writes it to the calibration
        database only for a hardware backend. A fake output carries ``FAKE_NOTICE`` in
        its description.
        """
        raw = run_result.raw_result
        if isinstance(raw, RabiSimulationResult):
            return self._postprocess_simulation(raw, qid)
        measurement: RabiIQResult = raw["measurement"]
        if measurement.mode != backend.mode:
            raise RuntimeError(
                f"{measurement.mode.capitalize()} Rabi result received from a backend in "
                f"{backend.mode} mode"
            )

        fit: RabiFit = raw["fit"]
        figure = self._response_figure(measurement, fit, qid)
        pi_scale = fit.pi_amplitude_scale
        low, high = covered_magnitude_range(measurement.amplitude_scales)
        validation_error = None
        if not math.isfinite(pi_scale) or pi_scale <= 0:
            validation_error = f"Rabi fit gave no usable pi amplitude scale: {pi_scale}"
        elif (
            not low * (1 - BOUNDARY_TOLERANCE) <= pi_scale <= high * (1 + BOUNDARY_TOLERANCE)
            or pi_scale >= AMPLITUDE_SCALE_MAX
        ):
            validation_error = (
                f"Fitted pi amplitude scale {pi_scale:.4g} lies outside the swept range "
                f"(|a| from {low:.4g} to {high:.4g}); adjust amplitude_scale_range"
            )
        if validation_error is not None:
            return PostProcessResult(
                output_parameters={}, figures=[figure], validation_error=validation_error
            )

        output = self.output_parameters["qm_pi_amplitude_scale"]
        output.value = pi_scale
        output.error = (
            fit.pi_amplitude_scale_error if math.isfinite(fit.pi_amplitude_scale_error) else 0.0
        )
        if measurement.mode == "fake":
            output.description = f"{FAKE_NOTICE} {output.description}"
        return PostProcessResult(
            output_parameters=self.attach_execution_id(execution_id), figures=[figure]
        )

    def _postprocess_simulation(self, raw: RabiSimulationResult, qid: str) -> PostProcessResult:
        figure = self._simulation_figure(raw, qid)
        validation_error = None
        if raw.simulated_iterations < 1:
            validation_error = (
                f"The simulated {raw.duration_ns} ns do not cover one sweep "
                f"(at least {raw.iteration_ns} ns); raise simulation.duration_ns"
            )
        elif not raw.has_output():
            validation_error = (
                f"The simulator produced no analog output in {raw.duration_ns} ns; "
                "check the QUA configuration or the simulation duration"
            )
        # Never publish calibration values from simulated waveforms.
        return PostProcessResult(
            output_parameters={}, figures=[figure], validation_error=validation_error
        )

    @staticmethod
    def _response_figure(measurement: RabiIQResult, fit: RabiFit, qid: str) -> go.Figure:
        scales = measurement.amplitude_scales
        dense = np.linspace(float(scales.min()), float(scales.max()), 500)
        figure = go.Figure()
        figure.add_trace(
            go.Scatter(x=scales, y=project_iq(measurement.iq), mode="markers", name="Data")
        )
        figure.add_trace(go.Scatter(x=dense, y=fit.evaluate(dense), mode="lines", name="Fit"))
        figure.update_layout(
            title={
                "text": (
                    f"QM amplitude Rabi : Q{qid} ({FIGURE_MODE_LABEL[measurement.mode]}) — "
                    f"pi scale = {fit.pi_amplitude_scale:.4g}, R² = {fit.r2:.3f}"
                ),
                "x": 0.5,
            },
            xaxis_title="Amplitude scale (a.u.)",
            yaxis_title="Projected I/Q signal (V)",
            width=800,
            height=450,
        )
        if measurement.mode == "fake":
            figure.update_layout(
                annotations=[
                    {
                        "text": (
                            "QM-FAKE: synthetic response generated locally by QDash, "
                            "not measured. "
                            f"{measurement.shots} shots, seed {measurement.metadata.get('seed')}."
                            "<br>Never written to the calibration database."
                        ),
                        "xref": "paper",
                        "yref": "paper",
                        "x": 0.5,
                        "y": 1.08,
                        "showarrow": False,
                    }
                ]
            )
        return figure

    @staticmethod
    def _simulation_figure(raw: RabiSimulationResult, qid: str) -> go.Figure:
        figure = go.Figure()
        for port, samples in raw.analog.items():
            rate = raw.analog_sampling_rate.get(port, 1e9)
            time_ns = np.arange(len(samples)) * 1e9 / rate
            values = np.asarray(samples)
            if np.iscomplexobj(values):
                figure.add_trace(go.Scatter(x=time_ns, y=values.real, name=f"{port} (I)"))
                figure.add_trace(go.Scatter(x=time_ns, y=values.imag, name=f"{port} (Q)"))
            else:
                figure.add_trace(go.Scatter(x=time_ns, y=values, name=port))
        figure.update_layout(
            title={
                "text": (
                    f"QM amplitude Rabi : Q{qid} (SIMULATED waveforms) — "
                    f"{raw.amplitude_scales.size} points, about {raw.simulated_iterations} of "
                    f"{raw.shots} iterations in {raw.duration_ns} ns"
                ),
                "x": 0.5,
            },
            xaxis_title="Time (ns)",
            yaxis_title="Output (V)",
            annotations=[
                {
                    "text": SIMULATION_NOTICE,
                    "xref": "paper",
                    "yref": "paper",
                    "x": 0.5,
                    "y": 1.08,
                    "showarrow": False,
                }
            ],
            width=900,
            height=450,
        )
        return figure
