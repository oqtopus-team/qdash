from typing import ClassVar

import numpy as np
from qcflow.manager.task_manager import Data
from qcflow.qubex_protocols.base import (
    BaseTask,
    OutputParameter,
    PostProcessResult,
    PreProcessResult,
    RunResult,
)
from qcflow.subflow.util import convert_label
from qubex.experiment import Experiment
from qubex.experiment.experiment_constants import CALIBRATION_SHOTS
from qubex.measurement.measurement import DEFAULT_INTERVAL


class RandomizedBenchmarking(BaseTask):
    """Task to perform randomized benchmarking."""

    task_name: str = "RandomizedBenchmarking"
    task_type: str = "qubit"
    output_parameters: ClassVar[dict[str, OutputParameter]] = {
        "average_gate_fidelity": OutputParameter(
            unit="",
            description="Average gate fidelity",
        ),
    }

    def __init__(
        self,
        shots=CALIBRATION_SHOTS,  # noqa: ANN001
        interval=DEFAULT_INTERVAL,  # noqa: ANN001
        n_cliffords_range=None,  # noqa: ANN001
        n_trials=30,  # noqa: ANN001
    ) -> None:
        if n_cliffords_range is None:
            n_cliffords_range = np.arange(0, 1001, 100)

        self.input_parameters = {
            "n_cliffords_range": n_cliffords_range,
            "n_trials": n_trials,
            "shots": shots,
            "interval": interval,
        }

    def preprocess(self, exp: Experiment, qid: str) -> PreProcessResult:  # noqa: ARG002
        input_param = {
            "n_cliffords_range": self.input_parameters["n_cliffords_range"],
            "n_trials": self.input_parameters["n_trials"],
            "shots": self.input_parameters["shots"],
            "interval": self.input_parameters["interval"],
        }
        return PreProcessResult(input_parameters=input_param)

    def postprocess(self, execution_id: str, run_result: RunResult, qid: str) -> PostProcessResult:  # noqa: ARG002
        result = run_result.raw_result
        op = self.output_parameters
        output_param = {
            "average_gate_fidelity": Data(
                value=result["avg_gate_fidelity"],
                unit=op["average_gate_fidelity"].unit,
                description=op["average_gate_fidelity"].description,
                execution_id=execution_id,
            ),
        }
        figures = [result["fig"]]
        return PostProcessResult(output_parameters=output_param, figures=figures)

    def run(self, exp: Experiment, qid: str) -> RunResult:
        label = convert_label(qid)
        result = exp.randomized_benchmarking(
            target=label,
            n_cliffords_range=self.input_parameters["n_cliffords_range"],
            n_trials=self.input_parameters["n_trials"],
            x90=exp.drag_hpi_pulse[label],
            save_image=False,
            shots=self.input_parameters["shots"],
            interval=self.input_parameters["interval"],
        )
        exp.calib_note.save()
        return RunResult(raw_result=result)
