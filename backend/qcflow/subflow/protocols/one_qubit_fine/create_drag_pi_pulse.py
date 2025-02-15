from qcflow.subflow.manager import ExecutionManager
from qcflow.subflow.protocols.base import BaseTask
from qubex.experiment import Experiment
from qubex.experiment.experiment import CALIBRATION_SHOTS, PI_DURATION
from qubex.measurement.measurement import DEFAULT_INTERVAL


class CreateDRAGPIPulse(BaseTask):
    task_name: str = "CreateDRAGPIPulse"
    output_parameters: dict = {"drag_pi_beta": {}, "drag_pi_amplitude": {}}

    def __init__(
        self,
        pi_length=PI_DURATION,
        shots=CALIBRATION_SHOTS,
        interval=DEFAULT_INTERVAL,
    ):
        self.input_parameters = {
            "pi_length": pi_length,
            "shots": shots,
            "interval": interval,
            "qubit_frequency": {},
            "control_amplitude": {},
            "readout_frequency": {},
            "readout_amplitude": {},
            "rabi_params": {},
        }

    def execute(self, exp: Experiment, execution_manager: ExecutionManager):
        self.input_parameters["qubit_frequency"] = {
            target: exp.targets[target].frequency for target in exp.qubit_labels
        }
        self.input_parameters["control_amplitude"] = {
            target: exp.params.control_amplitude[target] for target in exp.qubit_labels
        }
        self.input_parameters["readout_frequency"] = {
            target: resonator.frequency for target, resonator in exp.resonators.items()
        }
        self.input_parameters["readout_amplitude"] = {
            target: exp.params.readout_amplitude[target] for target in exp.qubit_labels
        }
        self.input_parameters["rabi_params"] = exp.rabi_params
        execution_manager.put_input_parameters(self.task_name, self.input_parameters)
        drag_pi_result = exp.calibrate_drag_pi_pulse(
            exp.qubit_labels,
            n_rotations=4,
            n_turns=1,
            n_iterations=2,
            shots=self.input_parameters["shots"],
            interval=self.input_parameters["interval"],
        )
        exp.save_defaults()
        self.output_parameters["drag_pi_amplitude"] = drag_pi_result["amplitude"]
        self.output_parameters["drag_pi_beta"] = drag_pi_result["beta"]
        execution_manager.put_output_parameters(self.task_name, self.output_parameters)
        for qubit in drag_pi_result["amplitude"]:
            execution_manager.put_calibration_value(
                qubit, "drag_pi_amplitude", drag_pi_result["amplitude"][qubit]
            )
            execution_manager.put_calibration_value(
                qubit, "drag_pi_beta", drag_pi_result["beta"][qubit]
            )
