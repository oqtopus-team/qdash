import numpy as np
from qcflow.subflow.protocols.base import BaseTask
from qcflow.subflow.task_manager import TaskManager
from qcflow.subflow.util import convert_qid
from qubex.experiment import Experiment
from qubex.experiment.experiment_constants import CALIBRATION_SHOTS
from qubex.measurement.measurement import DEFAULT_INTERVAL


class RandomizedBenchmarking(BaseTask):
    task_name: str = "RandomizedBenchmarking"
    task_type: str = "qubit"
    output_parameters: dict = {"average_gate_fidelity": {}}

    def __init__(
        self,
        shots=CALIBRATION_SHOTS,
        interval=DEFAULT_INTERVAL,
        n_cliffords_range=np.arange(0, 1001, 100),
        n_trials=30,
    ):
        self.input_parameters = {
            "n_cliffords_range": n_cliffords_range,
            "n_trials": n_trials,
            "shots": shots,
            "interval": interval,
        }

    def execute(self, exp: Experiment, task_manager: TaskManager):
        for target in exp.qubit_labels:
            rb_result = exp.randomized_benchmarking(
                target=target,
                n_cliffords_range=self.input_parameters["n_cliffords_range"],
                n_trials=self.input_parameters["n_trials"],
                x90=exp.drag_hpi_pulse[target],
                save_image=True,
                shots=self.input_parameters["shots"],
                interval=self.input_parameters["interval"],
            )
            self.output_parameters["average_gate_fidelity"][target] = rb_result["avg_gate_fidelity"]
            task_manager.put_output_parameters(
                self.task_name,
                self.output_parameters,
                self.task_type,
                qid=convert_qid(target),
            )
            task_manager.put_calib_data(
                qid=convert_qid(target),
                task_type=self.task_type,
                parameter_name="average_gate_fidelity",
                value=rb_result["avg_gate_fidelity"],
            )
            exp.save_defaults()
