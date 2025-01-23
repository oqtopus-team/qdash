import numpy as np
from qcflow.subflow.manager import ExecutionManager
from qcflow.subflow.protocols.base import BaseTask
from qubex.experiment import Experiment


class CreateZX90(BaseTask):
    task_name: str = "CreateZX90"
    output_parameters: dict = {
        "cr_amplitude": {},
    }

    def __init__(self):
        pass

    def execute(self, exp: Experiment, execution_manager: ExecutionManager):
        cr_control = exp.qubit_labels[0]
        cr_target = exp.qubit_labels[1]
        cr_pair = (cr_control, cr_target)
        cr_duration = 100
        cr_ramptime = 40
        cr_label = f"{cr_control}-{cr_target}"
        cr_result = exp.calibrate_zx90(
            *cr_pair,
            duration=cr_duration,
            ramptime=cr_ramptime,
            amplitude_range=np.linspace(0.0, 1.0, 20),
            # x180=ex.drag_pi_pulse,
        )
        self.output_parameters["cr_amplitude"] = cr_result["calibrated_value"]
        execution_manager.put_output_parameters(self.task_name, self.output_parameters)
        exp.save_defaults()
        execution_manager.put_calibration_value(
            cr_label, "cr_amplitude", cr_result["calibrated_value"]
        )
