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

    def execute(self, exp: Experiment, task_manager: TaskManager):
        readout_result = exp.build_classifier()
        exp.save_defaults()
        self.output_parameters["average_readout_fidelity"] = readout_result[
            "average_readout_fidelity"
        ]
        for qubit in exp.qubit_labels:
            task_manager.put_output_parameters(
                self.task_name,
                self.output_parameters,
                self.task_type,
                qubit=convert_qid(qubit),
            )
            task_manager.put_calib_data(
                qid=convert_qid(qubit),
                task_type=self.task_type,
                parameter_name="average_readout_fidelity",
                value=readout_result["average_readout_fidelity"][qubit],
            )
