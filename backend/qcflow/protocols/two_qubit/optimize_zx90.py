from typing import ClassVar

from qcflow.protocols.base import (
    BaseTask,
    InputParameter,
    OutputParameter,
    PostProcessResult,
    PreProcessResult,
    RunResult,
)
from qubex.experiment import Experiment


class OptimizeZX90(BaseTask):
    """Task to optimize the ZX90 pulse."""

    name: str = "OptimizeZX90"
    task_type: str = "coupling"
    input_parameters: ClassVar[dict[str, InputParameter]] = {}
    output_parameters: ClassVar[dict[str, OutputParameter]] = {
        "cr_amplitude": OutputParameter(unit="", description=""),
        "cr_phase": OutputParameter(unit="", description=""),
        "cancel_amplitude": OutputParameter(unit="", description=""),
        "cancel_phase": OutputParameter(unit="", description=""),
    }

    # @staticmethod
    # def determine_cr_pair(exp: Experiment) -> tuple[tuple[str, str], str]:
    #     qubit_frequencies = {target: exp.targets[target].frequency for target in exp.qubit_labels}
    #     sorted_qubits = sorted(qubit_frequencies.items(), key=lambda item: item[1])
    #     cr_control, cr_target = sorted_qubits[0][0], sorted_qubits[1][0]

    #     cr_pair = (cr_control, cr_target)
    #     cr_label = f"{cr_control}-{cr_target}"

    #     return cr_pair, cr_label

    # def execute(self, exp: Experiment, task_manager: TaskManager) -> None:
    #     cr_pair, cr_label = self.determine_cr_pair(exp)
    #     cr_result = exp.optimize_zx90(
    #         *cr_pair,
    #     )
    #     self.output_parameters["cr_amplitude"] = cr_result["cr_amplitude"]
    #     self.output_parameters["cr_phase"] = cr_result["cr_phase"]
    #     self.output_parameters["cancel_amplitude"] = cr_result["cancel_amplitude"]
    #     self.output_parameters["cancel_phase"] = cr_result["cancel_phase"]
    #     task_manager.put_output_parameters(self.name, self.output_parameters)
    #     exp.calib_note.save()
    #     note = f"CR pair: {cr_label}"
    #     task_manager.put_note_to_task(self.name, note)

    def preprocess(self, exp: Experiment, qid: str) -> PreProcessResult:
        pass

    def postprocess(self, execution_id: str, run_result: RunResult, qid: str) -> PostProcessResult:
        pass

    def run(self, exp: Experiment, qid: str) -> RunResult:
        pass
