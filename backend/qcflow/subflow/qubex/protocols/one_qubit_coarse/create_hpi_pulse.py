from qcflow.subflow.qubex.manager import TaskManager
from qcflow.subflow.qubex.protocols.base import BaseTask
from qubex.experiment import Experiment
from qubex.experiment.experiment import CALIBRATION_SHOTS, HPI_DURATION
from qubex.measurement.measurement import DEFAULT_INTERVAL


class CreateHPIPulse(BaseTask):
    task_name: str = "CreateHPIPulse"
    output_parameters: dict = {"hpi_amplitude": {}}

    def __init__(
        self,
        hpi_length=HPI_DURATION,
        shots=CALIBRATION_SHOTS,
        interval=DEFAULT_INTERVAL,
    ):
        self.input_parameters = {
            "hpi_length": hpi_length,
            "shots": shots,
            "interval": interval,
            "qubit_frequency": {},
            "control_amplitude": {},
            "readout_frequency": {},
            "readout_amplitude": {},
            "rabi_params": {},
        }

    def execute(self, exp: Experiment, task_manager: TaskManager):
        self.input_parameters["qubit_frequency"] = {
            target: exp.targets[target].frequency for target in exp.qubit_labels
        }
        self.input_parameters["control_amplitude"] = {
            target: exp.params.control_amplitude[target] for target in exp.qubit_labels
        }
        self.input_parameters["readout_frequency"] = exp.resonators.values()
        self.input_parameters["readout_amplitude"] = {
            target: exp.params.readout_amplitude[target] for target in exp.qubit_labels
        }
        self.input_parameters["rabi_params"] = exp.rabi_params
        task_manager.put_input_parameters(self.task_name, self.input_parameters)
        hpi_result = exp.calibrate_hpi_pulse(
            exp.qubit_labels,
            n_rotations=1,
            shots=self.input_parameters["shots"],
            interval=self.input_parameters["interval"],
        )
        exp.save_defaults()
        hpi_amplitudes = {}
        for qubit in exp.qubit_labels:
            hpi_amplitudes[qubit] = (
                hpi_result.data[qubit].calib_value if qubit in hpi_result.data else None
            )
        self.output_parameters["hpi_amplitude"] = hpi_amplitudes
        task_manager.put_output_parameters(self.task_name, self.output_parameters)
