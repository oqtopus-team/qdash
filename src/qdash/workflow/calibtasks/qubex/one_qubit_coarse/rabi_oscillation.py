from typing import ClassVar

from qdash.datamodel.task import InputParameterModel, OutputParameterModel
from qdash.workflow.caltasks.base import (
    PostProcessResult,
    RunResult,
)
from qdash.workflow.caltasks.qubex.base import QubexTask
from qdash.workflow.engine.backend.qubex import QubexBackend
from qdash.workflow.engine.calibration.task.types import TaskTypes


class RabiOscillation(QubexTask):
    """Task to check the Rabi oscillation."""

    name: str = "RabiOscillation"
    task_type = TaskTypes.QUBIT
    input_parameters: ClassVar[dict[str, InputParameterModel]] = {}
    output_parameters: ClassVar[dict[str, OutputParameterModel]] = {}

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        pass

    def run(self, backend: QubexBackend, qid: str) -> RunResult:  # noqa: ARG002
        exp = self.get_experiment(backend)
        default_rabi_amplitudes = {label: 0.01 for label in exp.qubit_labels}
        exp.rabi_experiment(
            amplitudes=default_rabi_amplitudes,
            time_range=range(0, 201, 4),
            detuning=0.001,
            shots=300,
            interval=50_000,
        )
        self.save_calibration(backend)
        return RunResult(raw_result=None)
