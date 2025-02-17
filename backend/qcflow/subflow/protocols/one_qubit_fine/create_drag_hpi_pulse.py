from typing import Any

from qcflow.subflow.protocols.base import BaseTask
from qcflow.subflow.task_manager import TaskManager
from qcflow.subflow.util import convert_qid
from qubex.experiment import Experiment
from qubex.experiment.experiment_constants import CALIBRATION_SHOTS, HPI_DURATION
from qubex.measurement.measurement import DEFAULT_INTERVAL


class CreateDRAGHPIPulse(BaseTask):
    task_name: str = "CreateDRAGHPIPulse"
    task_type: str = "qubit"
    output_parameters: dict = {"drag_hpi_beta": {}, "drag_hpi_amplitude": {}}

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

    def _preprocess(self, exp: Experiment, task_manager: TaskManager):
        for label in exp.qubit_labels:
            input_param = {
                "hpi_length": self.input_parameters["hpi_length"],
                "shots": self.input_parameters["shots"],
                "interval": self.input_parameters["interval"],
                "qubit_frequency": exp.targets[label].frequency,
                "control_amplitude": exp.params.control_amplitude[label],
                "readout_frequency": exp.resonators[label].frequency,
                "readout_amplitude": exp.params.readout_amplitude[label],
                "rabi_params": exp.rabi_params[label],
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
                "drag_hpi_beta": result[label].calib_value,
                "drag_hpi_amplitude": result[label].calib_value,
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
                parameter_name="drag_hpi_beta",
                value=result[label].calib_value,
            )
            task_manager.put_calib_data(
                qid=convert_qid(label),
                task_type=self.task_type,
                parameter_name="drag_hpi_amplitude",
                value=result[label].calib_value,
            )
        task_manager.save()

    def execute(self, exp: Experiment, task_manager: TaskManager):
        self._preprocess(exp, task_manager)
        drag_hpi_result = exp.calibrate_drag_hpi_pulse(
            exp.qubit_labels,
            n_rotations=4,
            n_turns=1,
            n_iterations=2,
            shots=self.input_parameters["shots"],
            interval=self.input_parameters["interval"],
        )
        exp.save_defaults()
        self.output_parameters["drag_hpi_amplitude"] = drag_hpi_result["amplitude"]
        self.output_parameters["drag_hpi_beta"] = drag_hpi_result["beta"]
        for qubit in exp.qubit_labels:
            task_manager.put_output_parameters(
                self.task_name,
                self.output_parameters,
                self.task_type,
                qid=convert_qid(qubit),
            )
            task_manager.put_calb_data(
                qid=convert_qid(qubit),
                task_type=self.task_type,
                parameter_name="drag_hpi_amplitude",
                value=drag_hpi_result["amplitude"][qubit],
            )
            task_manager.put_calb_data(
                qid=convert_qid(qubit),
                task_type=self.task_type,
                parameter_name="drag_hpi_beta",
                value=drag_hpi_result["beta"][qubit],
            )
