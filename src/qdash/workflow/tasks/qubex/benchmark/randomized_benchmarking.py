from typing import ClassVar

from qdash.datamodel.task import InputParameterModel, OutputParameterModel
from qdash.workflow.core.calibration.util import qid_to_label
from qdash.workflow.core.session.qubex import QubexSession
from qdash.workflow.tasks.base import (
    BaseTask,
    PostProcessResult,
    PreProcessResult,
    RunResult,
)
from qubex.experiment.experiment_constants import CALIBRATION_SHOTS
from qubex.measurement.measurement import DEFAULT_INTERVAL


class RandomizedBenchmarking(BaseTask):
    """Task to perform randomized benchmarking."""

    name: str = "RandomizedBenchmarking"
    backend: str = "qubex"
    task_type: str = "qubit"
    input_parameters: ClassVar[dict[str, InputParameterModel]] = {
        "n_trials": InputParameterModel(
            unit="a.u.",
            value_type="int",
            value=10,
            description="Number of trials",
        ),
        "shots": InputParameterModel(
            unit="a.u.",
            value_type="int",
            value=CALIBRATION_SHOTS,
            description="Number of shots",
        ),
        "interval": InputParameterModel(
            unit="ns",
            value_type="int",
            value=DEFAULT_INTERVAL,
            description="Time interval",
        ),
    }
    output_parameters: ClassVar[dict[str, OutputParameterModel]] = {
        "average_gate_fidelity": OutputParameterModel(
            unit="a.u.",
            description="Average gate fidelity",
        ),
        "depolarizing_rate": OutputParameterModel(
            unit="a.u.",
            description="Depolarization rate of the qubit",
        ),
    }

    def preprocess(self, session: QubexSession, qid: str) -> PreProcessResult:  # noqa: ARG002
        return PreProcessResult(input_parameters=self.input_parameters)

    def postprocess(self, execution_id: str, run_result: RunResult, qid: str) -> PostProcessResult:
        label = qid_to_label(qid)
        result = run_result.raw_result
        self.output_parameters["average_gate_fidelity"].value = result[label]["avg_gate_fidelity"]
        self.output_parameters["average_gate_fidelity"].error = result[label][
            "avg_gate_fidelity_err"
        ]
        self.output_parameters["depolarizing_rate"].value = result[label]["depolarizing_rate"]
        output_parameters = self.attach_execution_id(execution_id)
        figures = [result[label]["fig"]]
        return PostProcessResult(output_parameters=output_parameters, figures=figures)

    def run(self, session: QubexSession, qid: str) -> RunResult:
        label = qid_to_label(qid)
        exp = session.get_session()
        result = exp.randomized_benchmarking(
            targets=label,
            n_trials=self.input_parameters["n_trials"].get_value(),
            save_image=False,
            shots=self.input_parameters["shots"].get_value(),
            interval=self.input_parameters["interval"].get_value(),
        )
        exp.calib_note.save()
        r2 = result[label]["r2"]
        return RunResult(raw_result=result, r2={qid: r2})

    def batch_run(self, session: QubexSession, qid: str) -> RunResult:
        """Batch run is not implemented."""
        raise NotImplementedError(
            f"Batch run is not implemented for {self.name} task. Use run method instead."
        )
