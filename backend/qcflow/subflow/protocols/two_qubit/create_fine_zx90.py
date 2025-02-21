from typing import Any, ClassVar

import numpy as np
from qcflow.subflow.protocols.base import BaseTask
from qcflow.subflow.task_manager import TaskManager
from qubex.experiment import Experiment


class CreateFineZX90(BaseTask):
    """Task to create a fine ZX90 pulse."""

    task_name: str = "CreateFineZX90"
    task_type: str = "coupling"

    output_parameters: ClassVar[list[str]] = ["cr_amplitude"]

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
        center = task_manager.get_calibration_value(cr_label, "cr_amplitude")
        cr_duration = 100
        cr_ramptime = 40

        cr_result = exp.calibrate_zx90(
            *cr_pair,
            duration=cr_duration,
            ramptime=cr_ramptime,
            amplitude_range=np.linspace(center - 0.1, center + 0.1, 50),
            n_repetitions=3,
        )
        self.output_parameters["cr_amplitude"] = cr_result["calibrated_value"]
        task_manager.put_output_parameters(self.task_name, self.output_parameters)
        exp.calib_note.save()
        task_manager.put_calibration_value(cr_label, "cr_amplitude", cr_result["calibrated_value"])
        note = f"CR pair: {cr_label}"
        task_manager.put_note_to_task(self.task_name, note)
