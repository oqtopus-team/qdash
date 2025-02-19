from typing import Any

from qcflow.subflow.protocols.base import BaseTask
from qcflow.subflow.task_manager import Data, TaskManager
from qcflow.subflow.util import convert_qid
from qubex.experiment import Experiment
from qubex.experiment.experiment_constants import CALIBRATION_SHOTS, PI_DURATION
from qubex.measurement.measurement import DEFAULT_INTERVAL


class CreatePIPulse(BaseTask):
    task_name: str = "CreatePIPulse"
    task_type: str = "qubit"
    output_parameters: dict = {"pi_amplitude": {}}

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

    def _preprocess(self, exp: Experiment, task_manager: TaskManager):
        for label in exp.qubit_labels:
            input_param = {
                "pi_length": self.input_parameters["pi_length"],
                "shots": self.input_parameters["shots"],
                "interval": self.input_parameters["interval"],
                "qubit_frequency": exp.targets[label].frequency,
                "control_amplitude": exp.params.control_amplitude[label],
                "readout_frequency": exp.resonators[label].frequency,
                "readout_amplitude": exp.params.readout_amplitude[label],
                "rabi_frequency": exp.rabi_params[label].frequency,
                "rabi_amplitude": exp.rabi_params[label].amplitude,
            }
            task_manager.put_input_parameters(
                self.task_name,
                input_param,
                self.task_type,
                qid=convert_qid(label),
            )
        task_manager.save()

    def _postprocess(self, exp: Experiment, task_manager: TaskManager, result: Any):
        for label in exp.qubit_labels:
            output_param = {
                "pi_amplitude": result.data[label].calib_value,
            }
            task_manager.put_output_parameters(
                self.task_name,
                output_param,
                self.task_type,
                qid=convert_qid(label),
            )
            task_manager.put_calib_data(
                qid=convert_qid(label),
                task_type=self.task_type,
                parameter_name="pi_amplitude",
                data=Data(value=result.data[label].calib_value),
            )
            task_manager.save_figure(
                task_name=self.task_name,
                task_type=self.task_type,
                figure=result.data[label].fit()["fig"],
                qid=convert_qid(label),
            )
        task_manager.save()

    def execute(self, exp: Experiment, task_manager: TaskManager):
        self._preprocess(exp, task_manager)
        result = exp.calibrate_pi_pulse(
            exp.qubit_labels,
            n_rotations=1,
        )
        exp.calib_note.save(file_path=task_manager.calib_dir)
        self._postprocess(exp, task_manager, result)
