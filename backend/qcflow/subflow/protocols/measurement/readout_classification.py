from qcflow.subflow.manager import ExecutionManager
from qcflow.subflow.protocols.base import BaseTask
from qubex.experiment import Experiment


class ReadoutClassification(BaseTask):
    task_name: str = "ReadoutClassification"
    output_parameters: dict = {"average_readout_fidelity": {}}

    def __init__(self):
        pass

    def execute(self, exp: Experiment, execution_manager: ExecutionManager):
        readout_result = exp.build_classifier()
        exp.save_defaults()
        self.output_parameters["average_readout_fidelity"] = readout_result[
            "average_readout_fidelity"
        ]
        execution_manager.put_output_parameters(self.task_name, self.output_parameters)
