from typing import Any

from qcflow.subflow.protocols.base import BaseTask
from qcflow.subflow.task_manager import TaskManager
from qcflow.subflow.util import convert_qid
from qubex.experiment import Experiment


class ReadoutClassification(BaseTask):
    task_name: str = "ReadoutClassification"
    task_type: str = "qubit"

    output_parameters: dict = {"average_readout_fidelity": {}}

    def __init__(self):
        pass

    def _preprocess(self, exp: Experiment, task_manager: TaskManager):
        pass

    def _postprocess(self, exp: Experiment, task_manager: TaskManager, result: Any):
        for label in exp.qubit_labels:
            output_param = {
                "average_readout_fidelity": result["average_readout_fidelity"][label],
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
                parameter_name="average_readout_fidelity",
                value=result["average_readout_fidelity"][label],
            )

    def execute(self, exp: Experiment, task_manager: TaskManager):
        result = exp.build_classifier()
        exp.save_defaults()
        self._postprocess(exp, task_manager, result)
