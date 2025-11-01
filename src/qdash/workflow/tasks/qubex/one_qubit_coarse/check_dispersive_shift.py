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


class CheckDispersiveShift(QubexTask):
    """Task to check the Dispersive Shift"""

    name: str = "CheckDispersiveShift"
    task_type: str = "qubit"
    input_parameters: ClassVar[dict[str, InputParameterModel]] = {
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
        "optimal_readout_frequency": OutputParameterModel(unit="GHz", description="Optimal Readout Frequency"),
        "dispersive_shift": OutputParameterModel(unit="MHz", description="Dispersive shift"),
    }

    def postprocess(
        self, session: QubexSession, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        """Process the results of the task."""
        result = run_result.raw_result
        self.output_parameters["optimal_readout_frequency"].value = result["optimal_frequency"]
        self.output_parameters["dispersive_shift"].value = result["dispersive_shift"] * 1000  # convert to MHz
        output_parameters = self.attach_execution_id(execution_id)
        figures = [result["fig"]]
        return PostProcessResult(output_parameters=output_parameters, figures=figures)

    def run(self, session: QubexSession, qid: str) -> RunResult:
        """Run the task."""
        exp = self.get_experiment(session)
        label = self.get_qubit_label(session, qid)

        # Apply frequency override if qubit_frequency was explicitly provided
        with self._apply_frequency_override(session, qid):
            electrical_delay = exp.measure_electrical_delay(target=label)
            result = exp.measure_dispersive_shift(
                electrical_delay=electrical_delay,
                shots=self.input_parameters["shots"].get_value(),
                interval=self.input_parameters["interval"].get_value(),
                target=label,
            )

        self.save_calibration(session)
        return RunResult(raw_result=result)
