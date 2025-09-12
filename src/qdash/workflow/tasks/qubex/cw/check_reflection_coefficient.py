from typing import ClassVar

from qdash.datamodel.task import InputParameterModel, OutputParameterModel
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.initialize import initialize
from qdash.workflow.core.session.qubex import QubexSession
from qdash.workflow.tasks.base import (
    BaseTask,
    PostProcessResult,
    PreProcessResult,
    RunResult,
)


class CheckReflectionCoefficient(BaseTask):
    """Task to check the reflection coefficient of a resonator."""

    name: str = "CheckReflectionCoefficient"
    backend: str = "qubex"
    task_type: str = "qubit"
    input_parameters: ClassVar[dict[str, InputParameterModel]] = {}
    output_parameters: ClassVar[dict[str, OutputParameterModel]] = {
        "resonator_frequency": OutputParameterModel(unit="GHz", description="Fine resonator frequency"),
        "kappa_external": OutputParameterModel(unit="MHz", description="External coupling rate (kappa_external)"),
        "kappa_internal": OutputParameterModel(unit="MHz", description="Internal coupling rate (kappa_internal)"),
    }

    def preprocess(self, session: QubexSession, qid: str) -> PreProcessResult:  # noqa: ARG002
        """Preprocess the task."""
        return PreProcessResult(input_parameters=self.input_parameters)

    def postprocess(
        self, session: QubexSession, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        """Process the results of the task."""
        exp = session.get_session()
        label = exp.get_qubit_label(int(qid))
        result = run_result.raw_result
        figures = [result[label]["fig"]]
        self.output_parameters["resonator_frequency"].value = result[label]["f_r"]
        self.output_parameters["kappa_external"].value = result[label]["kappa_ex"] * 1e3
        self.output_parameters["kappa_internal"].value = result[label]["kappa_in"] * 1e3
        output_parameters = self.attach_execution_id(execution_id)

        return PostProcessResult(output_parameters=output_parameters, figures=figures)

    def run(self, session: QubexSession, qid: str) -> RunResult:
        """Run the task."""
        exp = session.get_session()
        label = exp.get_qubit_label(int(qid))
        result = exp.measure_reflection_coefficient(target=label)
        exp.calib_note.save()
        return RunResult(raw_result=result)

    def batch_run(self, session: QubexSession, qids: list[str]) -> RunResult:
        """Run the task for a batch of qubits."""
        exp = session.get_session()
        labels = [exp.get_qubit_label(int(qid)) for qid in qids]
        results = {}
        exp = session.get_session()
        initialize()
        chip = ChipDocument.get_current_chip(username="admin")
        for label, qid in zip(labels, qids):
            result = exp.measure_reflection_coefficient(
                target=label, center_frequency=chip.qubits[qid].data["coarse_resonator_frequency"]["value"]
            )
            results[label] = result
        exp.calib_note.save()
        return RunResult(raw_result=results)
