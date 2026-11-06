"""Thermal excitation characterization task."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any, ClassVar

from qubex.experiment.experiment_constants import DEFAULT_SHOTS
from qubex.measurement.measurement_defaults import DEFAULT_INTERVAL

from qdash.datamodel.task import InputParameterSpec, OutputParameterSpec, RunParameterSpec
from qdash.workflow.calibtasks.base import PostProcessResult, RunResult
from qdash.workflow.calibtasks.qubex.base import QubexTask, readout_duration_run_parameter
from qdash.workflow.calibtasks.qubex.validation import (
    finite_value_error,
    first_validation_error,
    require_ef_configuration,
)

if TYPE_CHECKING:
    from qdash.workflow.engine.backend.qubex import QubexBackend


class CheckThermalExcitation(QubexTask):
    """Estimate the thermal excitation probability of a qubit."""

    name: str = "CheckThermalExcitation"
    task_type: str = "qubit"
    input_spec: ClassVar[dict[str, InputParameterSpec]] = {
        "control_frequency": InputParameterSpec.required_database(
            fallback_parameter_names=("qubit_frequency",), unit="GHz"
        ),
        "control_frequency_ef": InputParameterSpec.required_database(
            fallback_parameter_names=("ef_frequency",), unit="GHz"
        ),
        "hpi_amplitude": InputParameterSpec.required_database(unit="a.u."),
        "hpi_duration": InputParameterSpec.required_database(unit="ns"),
        "ef_pi_amplitude": InputParameterSpec.required_database(unit="a.u."),
        "ef_pi_duration": InputParameterSpec.required_database(unit="ns"),
        "readout_amplitude": InputParameterSpec.required_database(unit="a.u."),
        "readout_frequency": InputParameterSpec.required_database(
            fallback_parameter_names=("resonator_frequency",), unit="GHz"
        ),
    }
    run_spec: ClassVar[dict[str, RunParameterSpec]] = {
        "readout_duration": readout_duration_run_parameter(),
        "shots": RunParameterSpec(
            unit="a.u.",
            value_type="int",
            default=1024 * DEFAULT_SHOTS,
            description="Shots per thermal-excitation sequence",
        ),
        "interval": RunParameterSpec(
            unit="ns",
            value_type="float",
            default=DEFAULT_INTERVAL,
            description="Time interval between shots",
        ),
    }
    output_spec: ClassVar[dict[str, OutputParameterSpec]] = {
        "thermal_excitation_probability": OutputParameterSpec(
            unit="a.u.", description="Estimated thermal excitation probability"
        ),
    }

    def _run_kwargs(self) -> dict[str, Any]:
        shots = int(self.run_parameters["shots"].get_value())
        interval = float(self.run_parameters["interval"].get_value())
        if shots <= 0:
            msg = "shots must be positive"
            raise ValueError(msg)
        if not math.isfinite(interval) or interval <= 0:
            msg = "interval must be finite and positive"
            raise ValueError(msg)
        return {"n_shots": shots, "shot_interval": interval, "plot": False}

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        """Run the four thermal-excitation measurement sequences."""
        from qubex.contrib import measure_thermal_excitation

        run_kwargs = self._run_kwargs()
        exp = self.get_experiment(backend)
        label = self.get_qubit_label(backend, qid)
        require_ef_configuration(exp, label)
        exp.params.readout_amplitude[label] = self._get_calibration_value("readout_amplitude")
        with exp.modified_frequencies(
            {
                exp.ctx.resolve_ge_label(label): self._get_calibration_value("control_frequency"),
                exp.ctx.resolve_ef_label(label): self._get_calibration_value(
                    "control_frequency_ef"
                ),
                exp.ctx.resolve_read_label(label): self._get_calibration_value("readout_frequency"),
            }
        ):
            result = measure_thermal_excitation(
                exp,
                target=label,
                **run_kwargs,
            )
        return RunResult(raw_result=result)

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        """Publish the thermal excitation probability."""
        data = run_result.raw_result.data
        probability = float(data["p_ex"])
        self.output_parameters["thermal_excitation_probability"].value = probability
        validation_error = first_validation_error(
            finite_value_error(
                probability,
                "thermal excitation probability",
                minimum=0.0,
                maximum=1.0,
            ),
            finite_value_error(
                data["signal_amplitude"],
                "thermal signal amplitude",
                minimum=0.0,
            ),
            finite_value_error(
                data["reference_amplitude"],
                "thermal reference amplitude",
                minimum=0.0,
            ),
        )
        return PostProcessResult(
            output_parameters=self.attach_execution_id(execution_id),
            validation_error=validation_error,
        )
