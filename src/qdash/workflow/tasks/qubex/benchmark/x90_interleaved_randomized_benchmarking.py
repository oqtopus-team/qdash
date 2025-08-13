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
from qubex.measurement.measurement import DEFAULT_INTERVAL


class X90InterleavedRandomizedBenchmarking(BaseTask):
    """Task to perform X90 interleaved randomized benchmarking."""

    name: str = "X90InterleavedRandomizedBenchmarking"
    backend: str = "qubex"
    task_type: str = "qubit"
    timeout: int = 60 * 30
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
        "x90_gate_fidelity": OutputParameterModel(
            unit="a.u.",
            description="X90 gate fidelity",
        ),
        "x90_depolarizing_rate": OutputParameterModel(
            unit="a.u.",
            description="Depolarization error of the X90 gate",
        ),
    }

    def preprocess(self, session: QubexSession, qid: str) -> PreProcessResult:  # noqa: ARG002
        return PreProcessResult(input_parameters=self.input_parameters)

    def postprocess(
        self, session: QubexSession, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        exp = session.get_session()
        label = exp.get_qubit_label(int(qid))
        result = run_result.raw_result
        self.output_parameters["x90_gate_fidelity"].value = result[label]["gate_fidelity"]
        self.output_parameters["x90_gate_fidelity"].error = result[label]["gate_fidelity_err"]
        self.output_parameters["x90_depolarizing_rate"].value = result[label]["rb_fit_result"]["depolarizing_rate"]
        output_parameters = self.attach_execution_id(execution_id)
        figures = [result[label]["fig"]]
        return PostProcessResult(output_parameters=output_parameters, figures=figures)

    def run(self, session: QubexSession, qid: str) -> RunResult:
        """Run the X90 interleaved randomized benchmarking task with timeout."""
        exp = session.get_session()
        label = exp.get_qubit_label(int(qid))
        result = exp.interleaved_randomized_benchmarking(
            targets=label,
            interleaved_clifford="X90",
            n_trials=self.input_parameters["n_trials"].get_value(),
            save_image=False,
            shots=self.input_parameters["shots"].get_value(),
            interval=self.input_parameters["interval"].get_value(),
        )
        exp.calib_note.save()
        r2 = result[label]["rb_fit_result"]["r2"]
        return RunResult(raw_result=result, r2={qid: r2})

    def batch_run(self, session: QubexSession, qid: str) -> RunResult:
        """Batch run is not implemented."""
        raise NotImplementedError(f"Batch run is not implemented for {self.name} task. Use run method instead.")
