from typing import Any, ClassVar

from qcflow.subflow.protocols.base import BaseTask, OutputParameter
from qcflow.subflow.task_manager import Data, TaskManager
from qcflow.subflow.util import convert_label, convert_qid
from qubex.experiment import Experiment
from qubex.experiment.experiment_constants import CALIBRATION_SHOTS, PI_DURATION
from qubex.measurement.measurement import DEFAULT_INTERVAL


class CreatePIPulse(BaseTask):
    """Task to create the pi pulse."""

    task_name: str = "CreatePIPulse"
    task_type: str = "qubit"
    output_parameters: ClassVar[dict[str, OutputParameter]] = {
        "pi_amplitude": OutputParameter(unit="", description="PI pulse amplitude")
    }

    def __init__(
        self,
        pi_length=PI_DURATION,
        shots=CALIBRATION_SHOTS,
        interval=DEFAULT_INTERVAL,
    ) -> None:
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

    def _preprocess(self, exp: Experiment, task_manager: TaskManager, qid: str) -> None:
        label = convert_label(qid)
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
            qid=qid,
        )
        task_manager.save()

    def _postprocess(
        self, exp: Experiment, task_manager: TaskManager, result: Any, qid: str
    ) -> None:
        label = convert_label(qid)
        op = self.output_parameters
        output_param = {
            "pi_amplitude": Data(
                value=result.data[label].calib_value,
                unit=op["pi_amplitude"].unit,
                description=op["pi_amplitude"].description,
                execution_id=task_manager.execution_id,
            ),
        }
        task_manager.put_output_parameters(
            self.task_name,
            output_param,
            self.task_type,
            qid=qid,
        )
        task_manager.save_figure(
            task_name=self.task_name,
            task_type=self.task_type,
            figure=result.data[label].fit()["fig"],
            qid=qid,
        )
        task_manager.save()

    def execute(self, exp: Experiment, task_manager: TaskManager, qid: str) -> None:
        self._preprocess(exp, task_manager, qid=qid)
        labels = [convert_label(qid)]
        result = exp.calibrate_pi_pulse(
            targets=labels,
            n_rotations=1,
        )
        exp.calib_note.save()
        self._postprocess(exp, task_manager, result, qid=qid)
