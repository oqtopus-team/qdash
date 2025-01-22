from qcflow.subflow.qubex.manager import ExecutionManager
from qcflow.subflow.qubex.protocols.base import BaseTask
from qubex.experiment import Experiment
from qubex.experiment.experiment import CALIBRATION_SHOTS, PI_DURATION
from qubex.measurement.measurement import DEFAULT_INTERVAL


class CreatePIPulse(BaseTask):
    task_name: str = "CreatePIPulse"
    output_parameters: dict = {"pi_amplitude": {}}

    def __init__(
        self,
        pi_length=PI_DURATION,
        shots=CALIBRATION_SHOTS,
        interval=DEFAULT_INTERVAL,
    ):
        self.input_parameters = {
            "hpi_length": pi_length,
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
        pi_result = exp.calibrate_pi_pulse(
            exp.qubit_labels,
            n_rotations=1,
        )
        exp.save_defaults()
        pi_amplitudes = {}
        for qubit in exp.qubit_labels:
            pi_amplitudes[qubit] = (
                pi_result.data[qubit].calib_value if qubit in pi_result.data else None
            )
        self.output_parameters["pi_amplitude"] = pi_amplitudes
        execution_manager.put_output_parameters(self.task_name, self.output_parameters)
        for qubit in pi_amplitudes:
            execution_manager.put_calibration_value(qubit, "pi_amplitude", pi_amplitudes[qubit])
