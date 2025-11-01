from typing import ClassVar

from qdash.datamodel.task import InputParameterModel, OutputParameterModel
from qdash.workflow.engine.session.qubex import QubexSession
from qdash.workflow.tasks.base import (
    PostProcessResult,
    RunResult,
)
from qdash.workflow.tasks.qubex.base import QubexTask
from qubex.experiment.experiment_constants import CALIBRATION_SHOTS
from qubex.measurement.measurement import DEFAULT_INTERVAL


class CheckRabi(QubexTask):
    """Task to check the Rabi oscillation."""

    name: str = "CheckRabi"
    task_type: str = "qubit"
    input_parameters: ClassVar[dict[str, InputParameterModel]] = {
        "time_range": InputParameterModel(
            unit="ns",
            value_type="range",
            value=(0, 401, 8),
            description="Time range for Rabi oscillation",
        ),
        "shots": InputParameterModel(
            unit="a.u.",
            value_type="int",
            value=CALIBRATION_SHOTS,
            description="Number of shots for Rabi oscillation",
        ),
        "interval": InputParameterModel(
            unit="ns",
            value_type="int",
            value=DEFAULT_INTERVAL,
            description="Time interval for Rabi oscillation",
        ),
    }
    output_parameters: ClassVar[dict[str, OutputParameterModel]] = {
        "rabi_amplitude": OutputParameterModel(unit="a.u.", description="Rabi oscillation amplitude"),
        "rabi_frequency": OutputParameterModel(unit="MHz", description="Rabi oscillation frequency"),
        "rabi_phase": OutputParameterModel(unit="a.u.", description="Rabi oscillation phase"),
        "rabi_offset": OutputParameterModel(unit="a.u.", description="Rabi oscillation offset"),
        "rabi_angle": OutputParameterModel(unit="degree", description="Rabi angle (in degree)"),
        "rabi_noise": OutputParameterModel(unit="a.u.", description="Rabi oscillation noise"),
        "rabi_distance": OutputParameterModel(unit="a.u.", description="Rabi distance"),
        "rabi_reference_phase": OutputParameterModel(unit="a.u.", description="Rabi reference phase"),
    }

    def postprocess(
        self, session: QubexSession, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        """Process the results of the task."""
        label = self.get_qubit_label(session, qid)
        result = run_result.raw_result
        self.output_parameters["rabi_amplitude"].value = result.rabi_params[label].amplitude
        self.output_parameters["rabi_amplitude"].error = result.data[label].fit()["amplitude_err"]
        self.output_parameters["rabi_frequency"].value = result.rabi_params[label].frequency * 1000  # convert to MHz
        self.output_parameters["rabi_frequency"].error = result.data[label].fit()["frequency_err"] * 1000
        self.output_parameters["rabi_phase"].value = result.rabi_params[label].phase
        self.output_parameters["rabi_phase"].error = result.data[label].fit()["phase_err"]
        self.output_parameters["rabi_offset"].value = result.rabi_params[label].offset
        self.output_parameters["rabi_offset"].error = result.data[label].fit()["offset_err"]
        self.output_parameters["rabi_angle"].value = result.rabi_params[label].angle
        self.output_parameters["rabi_noise"].value = result.rabi_params[label].noise
        self.output_parameters["rabi_distance"].value = result.rabi_params[label].distance
        self.output_parameters["rabi_reference_phase"].value = result.rabi_params[label].reference_phase
        output_parameters = self.attach_execution_id(execution_id)
        figures = [result.data[label].fit()["fig"]]
        raw_data = [result.data[label].data]
        return PostProcessResult(output_parameters=output_parameters, figures=figures, raw_data=raw_data)

    def run(self, session: QubexSession, qid: str) -> RunResult:
        """Run the task."""
        exp = self.get_experiment(session)
        label = self.get_qubit_label(session, qid)

        # Apply frequency override if qubit_frequency was explicitly provided
        with self._apply_frequency_override(session, qid):
            result = exp.obtain_rabi_params(
                time_range=self.input_parameters["time_range"].get_value(),
                shots=self.input_parameters["shots"].get_value(),
                interval=self.input_parameters["interval"].get_value(),
                targets=label,
            )

        self.save_calibration(session)
        r2 = result.rabi_params[label].r2 if result.rabi_params else None
        return RunResult(raw_result=result, r2={qid: r2})
