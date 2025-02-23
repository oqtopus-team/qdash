from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    import plotly.graph_objs as go
from qcflow.cal_util import qid_to_label
from qcflow.manager.task import Data
from qcflow.protocols.base import (
    BaseTask,
    OutputParameter,
    PostProcessResult,
    PreProcessResult,
    RunResult,
)
from qubex.experiment import Experiment


class ReadoutClassification(BaseTask):
    """Task to classify the readout."""

    name: str = "ReadoutClassification"
    task_type: str = "qubit"
    output_parameters: ClassVar[dict[str, OutputParameter]] = {
        "average_readout_fidelity": OutputParameter(
            unit="GHz",
            description="Average readout fidelity",
        ),
        "readout_fidelity_0": OutputParameter(
            unit="GHz",
            description="Readout fidelity with preparation state 0",
        ),
        "readout_fidelity_1": OutputParameter(
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
        op = self.output_parameters
        output_param = {
            "average_readout_fidelity": Data(
                value=result["average_readout_fidelity"][label],
                unit=op["average_readout_fidelity"].unit,
                description=op["average_readout_fidelity"].description,
                execution_id=execution_id,
            ),
            "readout_fidelity_0": Data(
                value=result["readout_fidelties"][label][0],
                unit=op["readout_fidelity_0"].unit,
                description=op["readout_fidelity_0"].description,
                execution_id=execution_id,
            ),
            "readout_fidelity_1": Data(
                value=result["readout_fidelties"][label][1],
                unit=op["readout_fidelity_1"].unit,
                description=op["readout_fidelity_1"].description,
                execution_id=execution_id,
            ),
        }
        figures: list[go.Figure] = []
        return PostProcessResult(output_parameters=output_param, figures=figures)

    def run(self, exp: Experiment, qid: str) -> RunResult:
        label = qid_to_label(qid)
        result = exp.build_classifier(targets=label)
        exp.calib_note.save()
        return RunResult(raw_result=result)
