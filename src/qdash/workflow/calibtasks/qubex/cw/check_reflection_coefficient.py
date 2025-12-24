from typing import ClassVar

from qdash.datamodel.task import ParameterModel, RunParameterModel
from qdash.dbmodel.initialize import initialize
from qdash.workflow.calibtasks.base import (
    PostProcessResult,
    RunResult,
)
from qdash.workflow.calibtasks.qubex.base import QubexTask
from qdash.workflow.engine.backend.qubex import QubexBackend


class CheckReflectionCoefficient(QubexTask):
    """Task to check the reflection coefficient of a resonator."""

    name: str = "CheckReflectionCoefficient"
    task_type: str = "qubit"
    run_parameters: ClassVar[dict[str, RunParameterModel]] = {}
    output_parameters: ClassVar[dict[str, ParameterModel]] = {
        "resonator_frequency": ParameterModel(unit="GHz", description="Fine resonator frequency"),
        "kappa_external": ParameterModel(
            unit="MHz", description="External coupling rate (kappa_external)"
        ),
        "kappa_internal": ParameterModel(
            unit="MHz", description="Internal coupling rate (kappa_internal)"
        ),
    }

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        """Process the results of the task."""
        label = self.get_qubit_label(backend, qid)
        result = run_result.raw_result
        figures = [result[label]["fig"]]
        self.output_parameters["resonator_frequency"].value = result[label]["f_r"]
        self.output_parameters["kappa_external"].value = result[label]["kappa_ex"] * 1e3
        self.output_parameters["kappa_internal"].value = result[label]["kappa_in"] * 1e3
        output_parameters = self.attach_execution_id(execution_id)

        return PostProcessResult(output_parameters=output_parameters, figures=figures)

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        """Run the task."""
        exp = self.get_experiment(backend)
        label = self.get_qubit_label(backend, qid)
        result = exp.measure_reflection_coefficient(target=label)
        self.save_calibration(backend)
        return RunResult(raw_result=result)

    def batch_run(self, backend: QubexBackend, qids: list[str]) -> RunResult:
        """Run the task for a batch of qubits."""
        exp = self.get_experiment(backend)
        labels = [self.get_qubit_label(backend, qid) for qid in qids]
        results = {}
        initialize()
        for label, qid in zip(labels, qids, strict=False):
            result = exp.measure_reflection_coefficient(
                target=label,  # center_frequency=chip.qubits[qid].data["coarse_resonator_frequency"]["value"]
            )
            results[label] = result
        self.save_calibration(backend)
        return RunResult(raw_result=results)
