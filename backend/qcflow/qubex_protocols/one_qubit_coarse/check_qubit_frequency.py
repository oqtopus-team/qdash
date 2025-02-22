from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    import plotly.graph_objs as go
import numpy as np
from qcflow.qubex_protocols.base import (
    BaseTask,
    OutputParameter,
    PostProcessResult,
    PreProcessResult,
    RunResult,
)
from qcflow.subflow.task_manager import Data
from qcflow.subflow.util import convert_label
from qubex.experiment import Experiment
from qubex.measurement.measurement import DEFAULT_INTERVAL, DEFAULT_SHOTS


class CheckQubitFrequency(BaseTask):
    """Task to check the qubit frequency."""

    task_name: str = "CheckQubitFrequency"
    task_type: str = "qubit"
    output_parameters: ClassVar[dict[str, OutputParameter]] = {
        "qubit_frequency": OutputParameter(unit="GHz", description="Qubit frequency"),
    }

    def __init__(
        self,
        detuning_range=None,  # noqa: ANN001
        time_range=None,  # noqa: ANN001
        shots=DEFAULT_SHOTS,  # noqa: ANN001
        interval=DEFAULT_INTERVAL,  # noqa: ANN001
    ) -> None:
        if detuning_range is None:
            detuning_range = np.linspace(-0.01, 0.01, 21)
        if time_range is None:
            time_range = range(0, 101, 4)
        self.input_parameters: dict = {
            "detuning_range": detuning_range,
            "time_range": time_range,
            "shots": shots,
            "interval": interval,
            "qubit_frequency": 0.0,
            "control_amplitude": 0.0,
        }

    def preprocess(self, exp: Experiment, qid: str) -> PreProcessResult:
        label = convert_label(qid)
        input_param = {
            "detuning_range": self.input_parameters["detuning_range"],
            "time_range": self.input_parameters["time_range"],
            "shots": self.input_parameters["shots"],
            "interval": self.input_parameters["interval"],
            "qubit_frequency": exp.targets[label].frequency,
            "control_amplitude": exp.params.control_amplitude[label],
        }
        return PreProcessResult(input_parameters=input_param)

    def postprocess(self, execution_id: str, run_result: RunResult, qid: str) -> PostProcessResult:
        label = convert_label(qid)
        result = run_result.raw_result
        op = self.output_parameters
        output_param = {
            "qubit_frequency": Data(
                value=result[label],
                unit=op["qubit_frequency"].unit,
                description=op["qubit_frequency"].description,
                execution_id=execution_id,
            ),
        }
        figures: list[go.Figure] = []
        return PostProcessResult(output_parameters=output_param, figures=figures)

    def run(self, exp: Experiment, qid: str) -> RunResult:
        labels = [convert_label(qid)]
        result = exp.calibrate_control_frequency(
            labels,
            detuning_range=self.input_parameters["detuning_range"],
            time_range=self.input_parameters["time_range"],
            shots=self.input_parameters["shots"],
            interval=self.input_parameters["interval"],
        )
        exp.calib_note.save()
        return RunResult(raw_result=result)
