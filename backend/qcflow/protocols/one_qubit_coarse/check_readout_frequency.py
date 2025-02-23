from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    import plotly.graph_objs as go
import numpy as np
from datamodel.task import DataModel
from qcflow.cal_util import qid_to_label
from qcflow.protocols.base import (
    BaseTask,
    OutputParameter,
    PostProcessResult,
    PreProcessResult,
    RunResult,
)
from qubex.experiment import Experiment
from qubex.measurement.measurement import DEFAULT_INTERVAL, DEFAULT_SHOTS


class CheckReadoutFrequency(BaseTask):
    """Task to check the readout frequency."""

    name: str = "CheckReadoutFrequency"
    task_type: str = "qubit"
    output_parameters: ClassVar[dict[str, OutputParameter]] = {
        "readout_frequency": OutputParameter(unit="GHz", description="Readout frequency"),
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
            "qubit_frequency": {},
            "control_amplitude": {},
            "readout_frequency": {},
            "readout_amplitude": {},
        }

    def preprocess(self, exp: Experiment, qid: str) -> PreProcessResult:
        label = qid_to_label(qid)
        input_param = {
            "detuning_range": self.input_parameters["detuning_range"],
            "time_range": self.input_parameters["time_range"],
            "shots": self.input_parameters["shots"],
            "interval": self.input_parameters["interval"],
            "qubit_frequency": exp.targets[label].frequency,
            "control_amplitude": exp.params.control_amplitude[label],
            "readout_frequency": exp.resonators[label].frequency,
            "readout_amplitude": exp.params.readout_amplitude[label],
        }
        return PreProcessResult(input_parameters=input_param)

    def postprocess(self, execution_id: str, run_result: RunResult, qid: str) -> PostProcessResult:
        label = qid_to_label(qid)
        result = run_result.raw_result
        op = self.output_parameters
        output_param = {
            "readout_frequency": DataModel(
                value=result[label],
                unit=op["readout_frequency"].unit,
                description=op["readout_frequency"].description,
                execution_id=execution_id,
            ),
        }
        figures: list[go.Figure] = []
        return PostProcessResult(output_parameters=output_param, figures=figures)

    def run(self, exp: Experiment, qid: str) -> RunResult:
        labels = [qid_to_label(qid)]
        result = exp.calibrate_readout_frequency(
            labels,
            detuning_range=self.input_parameters["detuning_range"],
            time_range=self.input_parameters["time_range"],
            shots=self.input_parameters["shots"],
            interval=self.input_parameters["interval"],
        )
        exp.calib_note.save()
        return RunResult(raw_result=result)
