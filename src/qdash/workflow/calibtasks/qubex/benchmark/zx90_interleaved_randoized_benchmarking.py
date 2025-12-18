from typing import ClassVar

from qdash.datamodel.task import InputParameterModel, OutputParameterModel
from qdash.workflow.calibtasks.base import (
    PostProcessResult,
    RunResult,
)
from qdash.workflow.calibtasks.qubex.base import QubexTask
from qdash.workflow.engine.backend.qubex import QubexBackend
from qubex.experiment.experiment_constants import CALIBRATION_SHOTS
from qubex.measurement.measurement import DEFAULT_INTERVAL
from qdash.workflow.engine.calibration.task.types import TaskTypes


class ZX90InterleavedRandomizedBenchmarking(QubexTask):
    """Task to perform ZX90 interleaved randomized benchmarking."""

    name: str = "ZX90InterleavedRandomizedBenchmarking"
    task_type = TaskTypes.COUPLING
    timeout: int = 60 * 30  # 25 minutes
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
        "zx90_gate_fidelity": OutputParameterModel(
            unit="a.u.",
            description="ZX90 gate fidelity",
            value_type="float",
        ),
        "zx90_depolarizing_rate": OutputParameterModel(
            unit="a.u.",
            description="Depolarization error of the ZX90 gate",
            value_type="float",
        ),
    }

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        exp = self.get_experiment(backend)
        label = "-".join(
            [exp.get_qubit_label(int(q)) for q in qid.split("-")]
        )  # e.g., "0-1" → "Q00-Q01"
        result = run_result.raw_result
        self.output_parameters["zx90_gate_fidelity"].value = result[label]["gate_fidelity"]
        self.output_parameters["zx90_gate_fidelity"].error = result[label]["gate_fidelity_err"]
        self.output_parameters["zx90_depolarizing_rate"].value = result[label]["rb_fit_result"][
            "depolarizing_rate"
        ]
        output_parameters = self.attach_execution_id(execution_id)
        figures = [result[label]["fig"]]
        return PostProcessResult(output_parameters=output_parameters, figures=figures)

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        exp = self.get_experiment(backend)
        label = "-".join(
            [exp.get_qubit_label(int(q)) for q in qid.split("-")]
        )  # e.g., "0-1" → "Q00-Q01"
        result = exp.interleaved_randomized_benchmarking(
            targets=label,
            interleaved_clifford="ZX90",
            n_trials=self.input_parameters["n_trials"].get_value(),
            save_image=False,
            shots=self.input_parameters["shots"].get_value(),
            interval=self.input_parameters["interval"].get_value(),
        )
        self.save_calibration(backend)
        r2 = result[label]["rb_fit_result"]["r2"]
        return RunResult(raw_result=result, r2={qid: r2})
