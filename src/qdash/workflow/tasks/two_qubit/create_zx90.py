from typing import ClassVar

from qdash.workflow.tasks.base import (
    BaseTask,
    InputParameter,
    OutputParameter,
    PostProcessResult,
    PreProcessResult,
    RunResult,
)
from qubex.experiment import Experiment


class CreateZX90(BaseTask):
    """Task to create ZX90 gate."""

    name: str = "CreateZX90"
    task_type: str = "coupling"
    input_parameters: ClassVar[dict[str, InputParameter]] = {}
    output_parameters: ClassVar[dict[str, OutputParameter]] = {
        "cr_amplitude": OutputParameter(unit="", description="Amplitude of the ZX90 gate."),
    }

    # @staticmethod
    # def determine_cr_pair(exp: Experiment) -> tuple:
    #     qubit_frequencies = {target: exp.targets[target].frequency for target in exp.qubit_labels}
    #     sorted_qubits = sorted(qubit_frequencies.items(), key=lambda item: item[1])
    #     cr_control, cr_target = sorted_qubits[0][0], sorted_qubits[1][0]

    #     cr_pair = (cr_control, cr_target)
    #     cr_label = f"{cr_control}-{cr_target}"

    #     return cr_pair, cr_label

    # def execute(self, exp: Experiment, task_manager: TaskManager) -> None:
    #     cr_pair, cr_label = self.determine_cr_pair(exp)
    #     cr_duration = 100
    #     cr_ramptime = 40
    #     cr_result = exp.calibrate_zx90(
    #         *cr_pair,
    #         duration=cr_duration,
    #         ramptime=cr_ramptime,
    #         amplitude_range=np.linspace(0.0, 1.0, 20),
    #         # x180=ex.drag_pi_pulse,
    #     )
    #     self.output_parameters["cr_amplitude"] = cr_result["calibrated_value"]
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
