from typing import ClassVar

from qdash.datamodel.task import InputParameterModel, OutputParameterModel
from qdash.workflow.core.session.qubex import QubexSession
from qdash.workflow.tasks.base import (
    BaseTask,
    PostProcessResult,
    PreProcessResult,
    RunResult,
)
from qubex.experiment.experiment_constants import CALIBRATION_SHOTS

# from qubex.measurement.measurement import DEFAULT_INTERVAL


class CreateHPIPulse(BaseTask):
    """Task to create the HPI pulse."""

    name: str = "CreateHPIPulse"
    backend: str = "qubex"
    task_type: str = "qubit"
    input_parameters: ClassVar[dict[str, InputParameterModel]] = {
        "duration": InputParameterModel(
            unit="ns", value_type="int", value=24, description="HPI pulse length"
        ),
        "shots": InputParameterModel(
            unit="",
            value_type="int",
            value=CALIBRATION_SHOTS,
            description="Number of shots for calibration",
        ),
        "interval": InputParameterModel(
            unit="ns",
            value_type="int",
            value=300 * 1024,
            description="Time interval for calibration",
        ),
    }
    output_parameters: ClassVar[dict[str, OutputParameterModel]] = {
        "hpi_amplitude": OutputParameterModel(unit="", description="HPI pulse amplitude")
    }

    def preprocess(self, session: QubexSession, qid: str) -> PreProcessResult:
        return PreProcessResult(input_parameters=self.input_parameters)

    def postprocess(
        self, session: QubexSession, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        exp = session.get_session()
        label = exp.get_qubit_label(int(qid))
        result = run_result.raw_result
        self.output_parameters["hpi_amplitude"].value = result.data[label].calib_value
        output_parameters = self.attach_execution_id(execution_id)
        figures = [result.data[label].fit()["fig"]]
        return PostProcessResult(output_parameters=output_parameters, figures=figures)

    def run(self, session: QubexSession, qid: str) -> RunResult:
        exp = session.get_session()
        labels = [exp.get_qubit_label(int(qid))]
        result = exp.calibrate_hpi_pulse(
            targets=labels,
            n_rotations=1,
            duration=self.input_parameters["duration"].get_value(),
            shots=self.input_parameters["shots"].get_value(),
            interval=self.input_parameters["interval"].get_value(),
        )
        exp.calib_note.save()
        r2 = result.data[exp.get_qubit_label(int(qid))].r2
        return RunResult(raw_result=result, r2={qid: r2})

    def batch_run(self, session: QubexSession, qid: str) -> RunResult:
        """Batch run is not implemented."""
        raise NotImplementedError(
            f"Batch run is not implemented for {self.name} task. Use run method instead."
        )
