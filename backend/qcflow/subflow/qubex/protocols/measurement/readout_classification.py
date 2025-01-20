from qcflow.subflow.qubex.manager import ExecutionManager
from qcflow.subflow.qubex.protocols.base import BaseTask
from qubex.experiment import Experiment


class ReadoutClassification(BaseTask):
    task_name: str = "ReadoutClassification"
    output_parameters: dict = {"readout_fidelity": {}}

    def __init__(self):
        pass

    def execute(self, exp: Experiment, execution_manager: ExecutionManager):
        readout_result = exp.build_classifier()
        exp.save_defaults()
        self.output_parameters["readout_fidelity"] = readout_result["average_fidelity"]
        execution_manager.put_output_parameters(self.task_name, self.output_parameters)
