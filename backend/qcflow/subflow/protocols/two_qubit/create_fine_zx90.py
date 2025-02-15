import numpy as np
from qcflow.subflow.manager import ExecutionManager
from qcflow.subflow.protocols.base import BaseTask
from qubex.experiment import Experiment


class CreateFineZX90(BaseTask):
    task_name: str = "CreateFineZX90"
    output_parameters: dict = {
        "cr_amplitude": {},
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

    def execute(self, exp: Experiment, execution_manager: ExecutionManager):
        cr_pair, cr_label = self.determine_cr_pair(exp)
        center = execution_manager.get_calibration_value(cr_label, "cr_amplitude")
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
        execution_manager.put_output_parameters(self.task_name, self.output_parameters)
        exp.save_defaults()
        execution_manager.put_calibration_value(
            cr_label, "cr_amplitude", cr_result["calibrated_value"]
        )
        note = f"CR pair: {cr_label}"
        execution_manager.put_note_to_task(self.task_name, note)
