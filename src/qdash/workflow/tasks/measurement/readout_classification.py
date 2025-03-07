from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    import plotly.graph_objs as go
from qdash.datamodel.task import OutputParameterModel
from qdash.workflow.calibration.util import qid_to_label
from qdash.workflow.tasks.base import (
    BaseTask,
    PostProcessResult,
    PreProcessResult,
    RunResult,
)
from qubex.experiment import Experiment


class ReadoutClassification(BaseTask):
    """Task to classify the readout."""

    name: str = "ReadoutClassification"
    task_type: str = "qubit"
    output_parameters: ClassVar[dict[str, OutputParameterModel]] = {
        "average_readout_fidelity": OutputParameterModel(
            unit="GHz",
            description="Average readout fidelity",
        ),
        "readout_fidelity_0": OutputParameterModel(
            unit="GHz",
            description="Readout fidelity with preparation state 0",
        ),
        "readout_fidelity_1": OutputParameterModel(
            unit="GHz",
            description="Readout fidelity with preparation state 1",
        ),
    }

    def __init__(self) -> None:
        pass

    def preprocess(self, exp: Experiment, qid: str) -> PreProcessResult:
        pass

    def postprocess(self, execution_id: str, run_result: RunResult, qid: str) -> PostProcessResult:
        label = qid_to_label(qid)
        result = run_result.raw_result
        self.output_parameters["average_readout_fidelity"].value = result[
            "average_readout_fidelity"
        ][label]
        self.output_parameters["readout_fidelity_0"].value = result["readout_fidelties"][label][0]
        self.output_parameters["readout_fidelity_1"].value = result["readout_fidelties"][label][1]
        output_parameters = self.attach_execution_id(execution_id)

        figures: list[go.Figure] = []
        return PostProcessResult(output_parameters=output_parameters, figures=figures)

    def run(self, exp: Experiment, qid: str) -> RunResult:
        label = qid_to_label(qid)
        result = exp.build_classifier(targets=label)
        exp.calib_note.save()
        return RunResult(raw_result=result)
