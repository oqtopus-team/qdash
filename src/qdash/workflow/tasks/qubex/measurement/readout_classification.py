from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    import plotly.graph_objs as go
from qdash.datamodel.task import InputParameterModel, OutputParameterModel
from qdash.workflow.core.session.qubex import QubexSession
from qdash.workflow.tasks.base import (
    BaseTask,
    PostProcessResult,
    PreProcessResult,
    RunResult,
)


class ReadoutClassification(BaseTask):
    """Task to classify the readout."""

    name: str = "ReadoutClassification"
    backend: str = "qubex"
    task_type: str = "qubit"
    input_parameters: ClassVar[dict[str, InputParameterModel]] = {}
    output_parameters: ClassVar[dict[str, OutputParameterModel]] = {
        "average_readout_fidelity": OutputParameterModel(
            unit="a.u.",
            description="Average readout fidelity",
        ),
        "readout_fidelity_0": OutputParameterModel(
            unit="a.u.",
            description="Readout fidelity with preparation state 0",
        ),
        "readout_fidelity_1": OutputParameterModel(
            unit="a.u.",
            description="Readout fidelity with preparation state 1",
        ),
    }

    def preprocess(self, session: QubexSession, qid: str) -> PreProcessResult:  # noqa: ARG002
        """Preprocess the task."""
        return PreProcessResult(input_parameters=self.input_parameters)

    def postprocess(
        self, session: QubexSession, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        exp = session.get_session()
        label = exp.get_qubit_label(int(qid))
        result = run_result.raw_result
        self.output_parameters["average_readout_fidelity"].value = result[
            "average_readout_fidelity"
        ][label]
        self.output_parameters["readout_fidelity_0"].value = result["readout_fidelties"][label][0]
        self.output_parameters["readout_fidelity_1"].value = result["readout_fidelties"][label][1]
        output_parameters = self.attach_execution_id(execution_id)

        figures: list[go.Figure] = []
        return PostProcessResult(output_parameters=output_parameters, figures=figures)

    def run(self, session: QubexSession, qid: str) -> RunResult:
        exp = session.get_session()
        label = exp.get_qubit_label(int(qid))
        result = exp.build_classifier(targets=label)
        exp.calib_note.save()
        return RunResult(raw_result=result)

    def batch_run(self, session: QubexSession, qid: str) -> RunResult:
        """Batch run is not implemented."""
        raise NotImplementedError(
            f"Batch run is not implemented for {self.name} task. Use run method instead."
        )
