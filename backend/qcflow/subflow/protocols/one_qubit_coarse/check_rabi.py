from typing import Any, ClassVar

from qcflow.subflow.protocols.base import BaseTask
from qcflow.subflow.task_manager import Data, TaskManager
from qcflow.subflow.util import convert_label
from qubex.experiment import Experiment
from qubex.experiment.experiment import RABI_TIME_RANGE
from qubex.measurement.measurement import DEFAULT_INTERVAL, DEFAULT_SHOTS


class CheckRabi(BaseTask):
    """Task to check the Rabi oscillation."""

    task_name: str = "CheckRabi"
    task_type: str = "qubit"
    output_parameters: ClassVar[list[str]] = ["rabi_amplitude", "rabi_frequency"]

    def __init__(
        self,
        time_range=RABI_TIME_RANGE,
        shots=DEFAULT_SHOTS,
        interval=DEFAULT_INTERVAL,
    ) -> None:
        self.input_parameters: dict = {
            "time_range": time_range,
            "shots": shots,
            "interval": interval,
            "qubit_frequency": {},
            "control_amplitude": {},
            "readout_frequency": {},
            "readout_amplitude": {},
        }

    def _preprocess(self, exp: Experiment, task_manager: TaskManager, qid: str) -> None:
        label = convert_label(qid)
        input_param = {
            "time_range": self.input_parameters["time_range"],
            "shots": self.input_parameters["shots"],
            "interval": self.input_parameters["interval"],
            "qubit_frequency": exp.targets[label].frequency,
            "control_amplitude": exp.params.control_amplitude[label],
            "readout_frequency": exp.resonators[label].frequency,
            "readout_amplitude": exp.params.readout_amplitude[label],
        }
        task_manager.put_input_parameters(
            self.task_name,
            input_param,
            self.task_type,
            qid=qid,
        )
        task_manager.save()

    def _postprocess(
        self, exp: Experiment, task_manager: TaskManager, result: Any, qid: str
    ) -> None:
        label = convert_label(qid)
        output_param = {
            "rabi_amplitude": Data(value=result.rabi_params[label].amplitude),
            "rabi_frequency": Data(value=result.rabi_params[label].frequency, unit="GHz"),
        }
        task_manager.put_output_parameters(
            self.task_name,
            output_param,
            self.task_type,
            qid=qid,
        )
        task_manager.put_calib_data(
            qid=qid,
            task_type=self.task_type,
            parameter_name="rabi_amplitude",
            data=Data(value=result.rabi_params[label].amplitude),
        )
        task_manager.put_calib_data(
            qid=qid,
            task_type=self.task_type,
            parameter_name="rabi_frequency",
            data=Data(value=result.rabi_params[label].frequency, unit="GHz"),
        )
        task_manager.save_figure(
            task_name=f"{self.task_name}",
            task_type=self.task_type,
            figure=result.data[label].fit()["fig"],
            qid=qid,
        )
        task_manager.save()

    def execute(self, exp: Experiment, task_manager: TaskManager, qid: str) -> None:
        self._preprocess(exp, task_manager, qid=qid)
        label = convert_label(qid)
        result = exp.obtain_rabi_params(
            time_range=self.input_parameters["time_range"],
            shots=self.input_parameters["shots"],
            interval=self.input_parameters["interval"],
            targets=label,
        )
        exp.calib_note.save()
        self._postprocess(exp, task_manager, result, qid=qid)
