import numpy as np
from qcflow.subflow.protocols.base import BaseTask
from qcflow.subflow.task_manager import TaskManager
from qubex.experiment import Experiment


class CheckCrossResonance(BaseTask):
    task_name: str = "CheckCrossResonance"
    task_type: str = "coupling"
    output_parameters: dict = {
        "cr_amplitude": {},
        "cr_phase": {},
        "cancel_amplitude": {},
        "cancel_phase": {},
    }

    def __init__(self):
        pass

    @staticmethod
    def determine_cr_pair(exp: Experiment):
        qubit_frequencies = {target: exp.targets[target].frequency for target in exp.qubit_labels}
        sorted_qubits = sorted(qubit_frequencies.items(), key=lambda item: item[1])
        cr_control, cr_target = sorted_qubits[0][0], sorted_qubits[1][0]

        cr_pair = (cr_control, cr_target)
        cr_label = f"{cr_control}-{cr_target}"

        return cr_pair, cr_label

    def execute(self, exp: Experiment, task_manager: TaskManager):
        cr_labels = exp.get_cr_labels()
        for cr_label in cr_labels:
            cr_pair, cr_label = self.determine_cr_pair(exp)
            cr_result = exp.obtain_cr_params(
                *cr_pair,
                flattop_range=np.arange(0, 401, 20),
                cr_amplitude=1.0,
                cr_ramptime=50,
                n_iterations=4,
            )
            self.output_parameters["cr_amplitude"] = cr_result["cr_pulse"]["amplitude"]
            self.output_parameters["cr_phase"] = cr_result["cr_pulse"]["phase"]
            self.output_parameters["cancel_amplitude"] = cr_result["cancel_pulse"]["amplitude"]
            self.output_parameters["cancel_phase"] = cr_result["cancel_pulse"]["phase"]
            task_manager.put_output_parameters(self.task_name, self.output_parameters)
            exp.calib_note.save(file_path=task_manager.calib_dir)
            task_manager.put_calibration_value(
                cr_label, "cr_amplitude", cr_result["cr_pulse"]["amplitude"]
            )
            task_manager.put_calibration_value(cr_label, "cr_phase", cr_result["cr_pulse"]["phase"])
            task_manager.put_calibration_value(
                cr_label, "cancel_amplitude", cr_result["cancel_pulse"]["amplitude"]
            )
            task_manager.put_calibration_value(
                cr_label, "cancel_phase", cr_result["cancel_pulse"]["phase"]
            )
            note = f"CR pair: {cr_label}"
            task_manager.put_note_to_task(self.task_name, note)
