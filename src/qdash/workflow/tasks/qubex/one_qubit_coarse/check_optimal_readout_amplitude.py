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


class CheckOptimalReadoutAmplitude(QubexTask):
    """Task to check the Optimal Readout Amplitude"""

    name: str = "CheckOptimalReadoutAmplitude"
    task_type: str = "qubit"
    input_parameters: ClassVar[dict[str, InputParameterModel]] = {
        "amplitude_range": InputParameterModel(
            unit="a.u.",
            value_type="np.arange",
            value=(0.01, 0.21, 0.01),
            description="Readout amplitude range",
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
        "optimal_readout_amplitude": OutputParameterModel(unit="a.u.", description="Optimal Readout Amplitude"),
    }

    def postprocess(
        self, session: QubexSession, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        """Process the results of the task."""
        result = run_result.raw_result
        self.output_parameters["optimal_readout_amplitude"].value = result["optimal_amplitude"]
        output_parameters = self.attach_execution_id(execution_id)
        figures = [result["fig"]]
        return PostProcessResult(output_parameters=output_parameters, figures=figures)

    def run(self, session: QubexSession, qid: str) -> RunResult:
        """Run the task."""
        exp = self.get_experiment(session)
        label = self.get_qubit_label(session, qid)

        # Apply frequency override if qubit_frequency was explicitly provided
        with self._apply_frequency_override(session, qid):
            result = exp.find_optimal_readout_amplitude(
                target=label,
                amplitude_range=self.input_parameters["amplitude_range"].get_value(),
                shots=self.input_parameters["shots"].get_value(),
                interval=self.input_parameters["interval"].get_value(),
            )

        self.save_calibration(session)
        return RunResult(raw_result=result)
