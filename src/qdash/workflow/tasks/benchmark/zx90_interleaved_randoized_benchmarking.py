from typing import ClassVar

from qdash.datamodel.task import DataModel
from qdash.workflow.calibration.util import qid_to_label
from qdash.workflow.tasks.base import (
    BaseTask,
    InputParameter,
    OutputParameter,
    PostProcessResult,
    PreProcessResult,
    RunResult,
)
from qubex.experiment import Experiment
from qubex.experiment.experiment_constants import CALIBRATION_SHOTS
from qubex.measurement.measurement import DEFAULT_INTERVAL


class ZX90InterleavedRandomizedBenchmarking(BaseTask):
    """Task to perform ZX90 interleaved randomized benchmarking."""

    name: str = "ZX90InterleavedRandomizedBenchmarking"
    task_type: str = "coupling"
    input_parameters: ClassVar[dict[str, InputParameter]] = {
        "n_cliffords_range": InputParameter(
            unit="a.u.",
            value_type="np.arange",
            value=(0, 1001, 100),
            description="Number of cliffords range",
        ),
        "n_trials": InputParameter(
            unit="a.u.",
            value_type="int",
            value=30,
            description="Number of trials",
        ),
        "shots": InputParameter(
            unit="a.u.",
            value_type="int",
            value=CALIBRATION_SHOTS,
            description="Number of shots",
        ),
        "interval": InputParameter(
            unit="ns",
            value_type="int",
            value=DEFAULT_INTERVAL,
            description="Time interval",
        ),
    }
    output_parameters: ClassVar[dict[str, OutputParameter]] = {
        "zx90_gate_fidelity": OutputParameter(
            unit="",
            description="ZX90 gate fidelity",
        ),
    }

    def preprocess(self, exp: Experiment, qid: str) -> PreProcessResult:  # noqa: ARG002
        return PreProcessResult(input_parameters=self.input_parameters)

    def postprocess(self, execution_id: str, run_result: RunResult, qid: str) -> PostProcessResult:
        label = qid_to_label(qid)
        result = run_result.raw_result
        op = self.output_parameters
        output_param = {
            "zx90_gate_fidelity": DataModel(
                value=result["mean"][label],
                unit=op["zx90_gate_fidelity"].unit,
                description=op["zx90_gate_fidelity"].description,
                execution_id=execution_id,
            ),
        }
        figures = [result.data[label].fit()["fig"]]
        return PostProcessResult(output_parameters=output_param, figures=figures)

    def run(self, exp: Experiment, qid: str) -> RunResult:
        label = qid_to_label(qid)
        result = exp.randomized_benchmarking(
            target=label,
            n_cliffords_range=self.input_parameters["n_cliffords_range"].get_value(),
            n_trials=self.input_parameters["n_trials"].get_value(),
            x90=exp.drag_hpi_pulse[label],
            save_image=False,
            shots=self.input_parameters["shots"].get_value(),
            interval=self.input_parameters["interval"].get_value(),
        )
        exp.calib_note.save()
        return RunResult(raw_result=result)
