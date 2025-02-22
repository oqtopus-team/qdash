from typing import Any, ClassVar

from qcflow.subflow.protocols.base import BaseTask
from qcflow.subflow.task_manager import TaskManager
from qubex.experiment import Experiment


class OptimizeZX90(BaseTask):
    """Task to optimize the ZX90 pulse."""

    task_name: str = "OptimizeZX90"
    task_type: str = "coupling"

    output_parameters: ClassVar[list[str]] = [
        "cr_amplitude",
        "cr_phase",
        "cancel_amplitude",
        "cancel_phase",
    ]

    def __init__(self) -> None:
        pass

    @staticmethod
    def determine_cr_pair(exp: Experiment) -> tuple[tuple[str, str], str]:
        qubit_frequencies = {target: exp.targets[target].frequency for target in exp.qubit_labels}
        sorted_qubits = sorted(qubit_frequencies.items(), key=lambda item: item[1])
        cr_control, cr_target = sorted_qubits[0][0], sorted_qubits[1][0]

        cr_pair = (cr_control, cr_target)
        cr_label = f"{cr_control}-{cr_target}"

        return cr_pair, cr_label

    def execute(self, exp: Experiment, task_manager: TaskManager) -> None:
        cr_pair, cr_label = self.determine_cr_pair(exp)
        cr_result = exp.optimize_zx90(
            *cr_pair,
        )
        self.output_parameters["cr_amplitude"] = cr_result["cr_amplitude"]
        self.output_parameters["cr_phase"] = cr_result["cr_phase"]
        self.output_parameters["cancel_amplitude"] = cr_result["cancel_amplitude"]
        self.output_parameters["cancel_phase"] = cr_result["cancel_phase"]
        task_manager.put_output_parameters(self.task_name, self.output_parameters)
        exp.calib_note.save()
        note = f"CR pair: {cr_label}"
        task_manager.put_note_to_task(self.task_name, note)
