from typing import ClassVar

from qdash.datamodel.task import InputParameterModel, OutputParameterModel
from qdash.workflow.calibration.util import qid_to_cr_label, qid_to_cr_pair
from qdash.workflow.tasks.base import (
    BaseTask,
    PostProcessResult,
    PreProcessResult,
    RunResult,
)
from qubex.clifford import Clifford
from qubex.experiment import Experiment
from qubex.experiment.experiment_constants import CALIBRATION_SHOTS
from qubex.measurement.measurement import DEFAULT_INTERVAL


class ZX90InterleavedRandomizedBenchmarking(BaseTask):
    """Task to perform ZX90 interleaved randomized benchmarking."""

    name: str = "ZX90InterleavedRandomizedBenchmarking"
    task_type: str = "coupling"
    input_parameters: ClassVar[dict[str, InputParameterModel]] = {
        "n_cliffords_range": InputParameterModel(
            unit="a.u.",
            value_type="np.arange",
            value=(0, 21, 2),
            description="Number of cliffords range",
        ),
        "n_trials": InputParameterModel(
            unit="a.u.",
            value_type="int",
            value=30,
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
        ),
    }

    def preprocess(self, exp: Experiment, qid: str) -> PreProcessResult:  # noqa: ARG002
        return PreProcessResult(input_parameters=self.input_parameters)

    def postprocess(self, execution_id: str, run_result: RunResult, qid: str) -> PostProcessResult:
        result = run_result.raw_result
        self.output_parameters["zx90_gate_fidelity"].value = result["gate_fidelity"]
        output_parameters = self.attach_execution_id(execution_id)
        figures = [result["fig"]]
        return PostProcessResult(output_parameters=output_parameters, figures=figures)

    def run(self, exp: Experiment, qid: str) -> RunResult:
        label = qid_to_cr_label(qid)
        control, target = qid_to_cr_pair(qid)
        result = exp.interleaved_randomized_benchmarking(
            target=label,
            interleaved_waveform=exp.zx90(control, target),
            interleaved_clifford=Clifford.ZX90(),
            n_cliffords_range=self.input_parameters["n_cliffords_range"].get_value(),
            n_trials=self.input_parameters["n_trials"].get_value(),
            save_image=False,
            shots=self.input_parameters["shots"].get_value(),
            interval=self.input_parameters["interval"].get_value(),
        )
        exp.calib_note.save()
        return RunResult(raw_result=result)
