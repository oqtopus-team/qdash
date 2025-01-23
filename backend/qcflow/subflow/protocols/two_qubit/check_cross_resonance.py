import numpy as np
from qcflow.subflow.manager import ExecutionManager
from qcflow.subflow.protocols.base import BaseTask
from qubex.experiment import Experiment


class CheckCrossResonance(BaseTask):
    task_name: str = "CheckCrossResonance"
    output_parameters: dict = {
        "cr_amplitude": {},
        "cr_phase": {},
        "cancel_amplitude": {},
        "cancel_phase": {},
    }

    def __init__(self):
        pass

    def execute(self, exp: Experiment, execution_manager: ExecutionManager):
        cr_control = exp.qubit_labels[0]
        cr_target = exp.qubit_labels[1]
        cr_pair = (cr_control, cr_target)
        cr_label = f"{cr_control}-{cr_target}"
        cr_result = exp.obtain_cr_params(
            *cr_pair,
            flattop_range=np.arange(0, 401, 20),
            cr_amplitude=1.0,
            cr_ramptime=50,
            n_iterations=2,
        )
        self.output_parameters["cr_amplitude"] = cr_result["cr_pulse"]["amplitude"]
        self.output_parameters["cr_phase"] = cr_result["cr_pulse"]["phase"]
        self.output_parameters["cancel_amplitude"] = cr_result["cancel_pulse"]["amplitude"]
        self.output_parameters["cancel_phase"] = cr_result["cancel_pulse"]["phase"]
        execution_manager.put_output_parameters(self.task_name, self.output_parameters)
        exp.save_defaults()
        execution_manager.put_calibration_value(
            cr_label, "cr_amplitude", cr_result["cr_pulse"]["amplitude"]
        )
        execution_manager.put_calibration_value(
            cr_label, "cr_phase", cr_result["cr_pulse"]["phase"]
        )
        execution_manager.put_calibration_value(
            cr_label, "cancel_amplitude", cr_result["cancel_pulse"]["amplitude"]
        )
        execution_manager.put_calibration_value(
            cr_label, "cancel_phase", cr_result["cancel_pulse"]["phase"]
        )
