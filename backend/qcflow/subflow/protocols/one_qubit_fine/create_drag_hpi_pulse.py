from typing import Any, ClassVar

from qcflow.subflow.protocols.base import BaseTask
from qcflow.subflow.task_manager import Data, TaskManager
from qcflow.subflow.util import convert_qid
from qubex.experiment import Experiment
from qubex.experiment.experiment_constants import CALIBRATION_SHOTS, HPI_DURATION
from qubex.measurement.measurement import DEFAULT_INTERVAL


class CreateDRAGHPIPulse(BaseTask):
    """Task to create the DRAG HPI pulse."""

    task_name: str = "CreateDRAGHPIPulse"
    task_type: str = "qubit"
    output_parameters: ClassVar[list[str]] = ["drag_hpi_beta", "drag_hpi_amplitude"]

    def __init__(
        self,
        hpi_length=HPI_DURATION,
        shots=CALIBRATION_SHOTS,
        interval=DEFAULT_INTERVAL,
    ) -> None:
        self.input_parameters = {
            "hpi_length": hpi_length,
            "shots": shots,
            "interval": interval,
            "qubit_frequency": {},
            "control_amplitude": {},
            "readout_frequency": {},
            "readout_amplitude": {},
            "rabi_frequency": {},
            "rabi_amplitude": {},
        }

    def _preprocess(self, exp: Experiment, task_manager: TaskManager) -> None:
        for label in exp.qubit_labels:
            input_param = {
                "hpi_length": self.input_parameters["hpi_length"],
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

    def _postprocess(self, exp: Experiment, task_manager: TaskManager, result: Any) -> None:
        for label in exp.qubit_labels:
            output_param = {
                "drag_hpi_beta": Data(value=result["beta"][label]),
                "drag_hpi_amplitude": Data(value=result["amplitude"][label]),
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
                data=Data(value=result["beta"][label]),
            )
            task_manager.put_calib_data(
                qid=convert_qid(label),
                task_type=self.task_type,
                parameter_name="drag_hpi_amplitude",
                data=Data(
                    value=result["amplitude"][label],
                ),
            )
        task_manager.save()

    def execute(self, exp: Experiment, task_manager: TaskManager) -> None:
        self._preprocess(exp, task_manager)
        result = exp.calibrate_drag_hpi_pulse(
            exp.qubit_labels,
            n_rotations=4,
            n_turns=1,
            n_iterations=2,
            shots=self.input_parameters["shots"],
            interval=self.input_parameters["interval"],
        )
        exp.calib_note.save(file_path=task_manager.calib_dir)
        self._postprocess(exp, task_manager, result)
