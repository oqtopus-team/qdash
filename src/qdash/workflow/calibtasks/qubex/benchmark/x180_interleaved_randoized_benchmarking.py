from typing import ClassVar

from qdash.datamodel.task import ParameterModel, RunParameterModel
from qdash.workflow.calibtasks.base import (
    PostProcessResult,
    RunResult,
)
from qdash.workflow.calibtasks.qubex.base import QubexTask
from qdash.workflow.engine.backend.qubex import QubexBackend
from qubex.experiment.experiment_constants import CALIBRATION_SHOTS
from qubex.measurement.measurement import DEFAULT_INTERVAL


class X180InterleavedRandomizedBenchmarking(QubexTask):
    """Task to perform X180 interleaved randomized benchmarking."""

    name: str = "X180InterleavedRandomizedBenchmarking"
    task_type: str = "qubit"
    timeout: int = 60 * 30
    run_parameters: ClassVar[dict[str, RunParameterModel]] = {
        "n_trials": RunParameterModel(
            unit="a.u.",
            value_type="int",
            value=10,
            description="Number of trials",
        ),
        "shots": RunParameterModel(
            unit="a.u.",
            value_type="int",
            value=CALIBRATION_SHOTS,
            description="Number of shots",
        ),
        "interval": RunParameterModel(
            unit="ns",
            value_type="int",
            value=DEFAULT_INTERVAL,
            description="Time interval",
        ),
    }
    output_parameters: ClassVar[dict[str, ParameterModel]] = {
        "x180_gate_fidelity": ParameterModel(
            unit="a.u.",
            description="X180 gate fidelity",
        ),
        "x180_depolarizing_rate": ParameterModel(
            unit="a.u.",
            description="Depolarization error of the X180 gate",
        ),
    }

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        self.get_experiment(backend)
        label = self.get_qubit_label(backend, qid)
        result = run_result.raw_result
        self.output_parameters["x180_gate_fidelity"].value = result[label]["gate_fidelity"]
        self.output_parameters["x180_gate_fidelity"].error = result[label]["gate_fidelity_err"]
        self.output_parameters["x180_depolarizing_rate"].value = result[label]["rb_fit_result"][
            "depolarizing_rate"
        ]
        output_parameters = self.attach_execution_id(execution_id)
        figures = [result[label]["fig"]]
        return PostProcessResult(output_parameters=output_parameters, figures=figures)

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        exp = self.get_experiment(backend)
        label = self.get_qubit_label(backend, qid)
        result = exp.interleaved_randomized_benchmarking(
            targets=label,
            interleaved_clifford="X180",
            n_trials=self.run_parameters["n_trials"].get_value(),
            save_image=False,
            shots=self.run_parameters["shots"].get_value(),
            interval=self.run_parameters["interval"].get_value(),
        )
        self.save_calibration(backend)
        r2 = result[label]["rb_fit_result"]["r2"]
        return RunResult(raw_result=result, r2={qid: r2})
