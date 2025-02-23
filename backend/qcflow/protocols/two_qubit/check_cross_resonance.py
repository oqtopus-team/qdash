from typing import ClassVar

from qcflow.protocols.base import (
    BaseTask,
    OutputParameter,
    PostProcessResult,
    PreProcessResult,
    RunResult,
)
from qubex.experiment import Experiment


class CheckCrossResonance(BaseTask):
    """Task to check the cross resonance pulse."""

    task_name: str = "CheckCrossResonance"
    task_type: str = "coupling"
    output_parameters: ClassVar[dict[str, OutputParameter]] = {
        "cr_amplitude": OutputParameter(unit="", description="Amplitude of the CR pulse."),
        "cr_phase": OutputParameter(unit="", description="Phase of the CR pulse."),
        "cancel_amplitude": OutputParameter(unit="", description="Amplitude of the cancel pulse."),
        "cancel_phase": OutputParameter(unit="", description="Phase of the cancel pulse."),
    }

    def __init__(self) -> None:
        pass

    # @staticmethod
    # def determine_cr_pair(exp: Experiment):
    #     qubit_frequencies = {target: exp.targets[target].frequency for target in exp.qubit_labels}
    #     sorted_qubits = sorted(qubit_frequencies.items(), key=lambda item: item[1])
    #     cr_control, cr_target = sorted_qubits[0][0], sorted_qubits[1][0]

    #     cr_pair = (cr_control, cr_target)
    #     cr_label = f"{cr_control}-{cr_target}"

    #     return cr_pair, cr_label

    # def execute(self, exp: Experiment, task_manager: TaskManager) -> None:
    #     cr_labels = exp.get_cr_labels()
    #     for cr_label in cr_labels:
    #         cr_pair, cr_label = self.determine_cr_pair(exp)
    #         cr_result = exp.obtain_cr_params(
    #             *cr_pair,
    #             flattop_range=np.arange(0, 401, 20),
    #             cr_amplitude=1.0,
    #             cr_ramptime=50,
    #             n_iterations=4,
    #         )
    #         self.output_parameters["cr_amplitude"] = cr_result["cr_pulse"]["amplitude"]
    #         self.output_parameters["cr_phase"] = cr_result["cr_pulse"]["phase"]
    #         self.output_parameters["cancel_amplitude"] = cr_result["cancel_pulse"]["amplitude"]
    #         self.output_parameters["cancel_phase"] = cr_result["cancel_pulse"]["phase"]
    #         task_manager.put_output_parameters(self.task_name, self.output_parameters)
    #         exp.calib_note.save()
    #         note = f"CR pair: {cr_label}"
    #         task_manager.put_note_to_task(self.task_name, note)

    def preprocess(self, exp: Experiment, qid: str) -> PreProcessResult:
        pass

    def postprocess(self, execution_id: str, run_result: RunResult, qid: str) -> PostProcessResult:
        pass

    def run(self, exp: Experiment, qid: str) -> RunResult:
        pass
