from typing import ClassVar

from qdash.datamodel.task import ParameterModel, RunParameterModel
from qdash.workflow.calibtasks.base import (
    PostProcessResult,
    RunResult,
)
from qdash.workflow.calibtasks.qubex.base import QubexTask
from qdash.workflow.engine.backend.qubex import QubexBackend
from qubex.experiment.experiment_constants import CALIBRATION_SHOTS
from qubex.measurement.measurement import DEFAULT_INTERVAL


class CheckRabi(QubexTask):
    """Task to check the Rabi oscillation."""

    name: str = "CheckRabi"
    task_type: str = "qubit"
    input_parameters: ClassVar[dict[str, ParameterModel | None]] = {
        "qubit_frequency": None,  # Load from DB
        "control_amplitude": None,  # Load from DB
        "readout_amplitude": None,  # Load from DB
        "readout_frequency": None,  # Load from DB
    }
    run_parameters: ClassVar[dict[str, RunParameterModel]] = {
        "time_range": RunParameterModel(
            unit="ns",
            value_type="range",
            value=(0, 401, 8),
            description="Time range for Rabi oscillation",
        ),
        "shots": RunParameterModel(
            unit="a.u.",
            value_type="int",
            value=CALIBRATION_SHOTS,
            description="Number of shots for Rabi oscillation",
        ),
        "interval": RunParameterModel(
            unit="ns",
            value_type="int",
            value=DEFAULT_INTERVAL,
            description="Time interval for Rabi oscillation",
        ),
    }
    output_parameters: ClassVar[dict[str, ParameterModel]] = {
        "rabi_amplitude": ParameterModel(unit="a.u.", description="Rabi oscillation amplitude"),
        "rabi_frequency": ParameterModel(unit="MHz", description="Rabi oscillation frequency"),
        "rabi_phase": ParameterModel(unit="a.u.", description="Rabi oscillation phase"),
        "rabi_offset": ParameterModel(unit="a.u.", description="Rabi oscillation offset"),
        "rabi_angle": ParameterModel(unit="degree", description="Rabi angle (in degree)"),
        "rabi_noise": ParameterModel(unit="a.u.", description="Rabi oscillation noise"),
        "rabi_distance": ParameterModel(unit="a.u.", description="Rabi distance"),
        "rabi_reference_phase": ParameterModel(unit="a.u.", description="Rabi reference phase"),
    }

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        """Process the results of the task."""
        label = self.get_qubit_label(backend, qid)
        result = run_result.raw_result
        self.output_parameters["rabi_amplitude"].value = result.rabi_params[label].amplitude
        self.output_parameters["rabi_amplitude"].error = result.data[label].fit()["amplitude_err"]
        self.output_parameters["rabi_frequency"].value = (
            result.rabi_params[label].frequency * 1000
        )  # convert to MHz
        self.output_parameters["rabi_frequency"].error = (
            result.data[label].fit()["frequency_err"] * 1000
        )
        self.output_parameters["rabi_phase"].value = result.rabi_params[label].phase
        self.output_parameters["rabi_phase"].error = result.data[label].fit()["phase_err"]
        self.output_parameters["rabi_offset"].value = result.rabi_params[label].offset
        self.output_parameters["rabi_offset"].error = result.data[label].fit()["offset_err"]
        self.output_parameters["rabi_angle"].value = result.rabi_params[label].angle
        self.output_parameters["rabi_noise"].value = result.rabi_params[label].noise
        self.output_parameters["rabi_distance"].value = result.rabi_params[label].distance
        self.output_parameters["rabi_reference_phase"].value = result.rabi_params[
            label
        ].reference_phase
        output_parameters = self.attach_execution_id(execution_id)
        figures = [result.data[label].fit()["fig"]]
        raw_data = [result.data[label].data]
        return PostProcessResult(
            output_parameters=output_parameters, figures=figures, raw_data=raw_data
        )

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        """Run the task."""
        exp = self.get_experiment(backend)
        label = self.get_qubit_label(backend, qid)

        # Apply frequency override if qubit_frequency was explicitly provided
        with self._apply_frequency_override(backend, qid):
            result = exp.obtain_rabi_params(
                time_range=self.run_parameters["time_range"].get_value(),
                shots=self.run_parameters["shots"].get_value(),
                interval=self.run_parameters["interval"].get_value(),
                targets=label,
            )

        self.save_calibration(backend)
        r2 = result.rabi_params[label].r2 if result.rabi_params else None
        return RunResult(raw_result=result, r2={qid: r2})
