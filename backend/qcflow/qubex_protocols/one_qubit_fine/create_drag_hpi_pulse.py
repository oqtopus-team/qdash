from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    import plotly.graph_objs as go
from qcflow.manager.task import Data
from qcflow.qubex_protocols.base import (
    BaseTask,
    OutputParameter,
    PostProcessResult,
    PreProcessResult,
    RunResult,
)
from qcflow.subflow.util import convert_label
from qubex.experiment import Experiment
from qubex.experiment.experiment_constants import CALIBRATION_SHOTS, HPI_DURATION
from qubex.measurement.measurement import DEFAULT_INTERVAL


class CreateDRAGHPIPulse(BaseTask):
    """Task to create the DRAG HPI pulse."""

    task_name: str = "CreateDRAGHPIPulse"
    task_type: str = "qubit"
    output_parameters: ClassVar[dict[str, OutputParameter]] = {
        "drag_hpi_beta": OutputParameter(unit="", description="DRAG HPI pulse beta"),
        "drag_hpi_amplitude": OutputParameter(unit="", description="DRAG HPI pulse amplitude"),
    }

    def __init__(
        self,
        hpi_length=HPI_DURATION,  # noqa: ANN001
        shots=CALIBRATION_SHOTS,  # noqa: ANN001
        interval=DEFAULT_INTERVAL,  # noqa: ANN001
    ) -> None:
        self.input_parameters = {
            "hpi_length": hpi_length,
            "shots": shots,
            "interval": interval,
            "qubit_frequency": {},
            "control_amplitude": {},
            "readout_frequency": {},
            "readout_amplitude": {},
            "rabi_frequency": {},
            "rabi_amplitude": {},
        }

    def preprocess(self, exp: Experiment, qid: str) -> PreProcessResult:
        label = convert_label(qid)
        input_param = {
            "hpi_length": self.input_parameters["hpi_length"],
            "shots": self.input_parameters["shots"],
            "interval": self.input_parameters["interval"],
            "qubit_frequency": exp.targets[label].frequency,
            "control_amplitude": exp.params.control_amplitude[label],
            "readout_frequency": exp.resonators[label].frequency,
            "readout_amplitude": exp.params.readout_amplitude[label],
            "rabi_frequency": exp.rabi_params[label].frequency,
            "rabi_amplitude": exp.rabi_params[label].amplitude,
        }
        return PreProcessResult(input_parameters=input_param)

    def postprocess(self, execution_id: str, run_result: RunResult, qid: str) -> PostProcessResult:
        label = convert_label(qid)
        result = run_result.raw_result
        op = self.output_parameters
        output_param = {
            "drag_hpi_beta": Data(
                value=result["beta"][label],
                unit=op["drag_hpi_beta"].unit,
                description=op["drag_hpi_beta"].description,
                execution_id=execution_id,
            ),
            "drag_hpi_amplitude": Data(
                value=result["amplitude"][label],
                unit=op["drag_hpi_amplitude"].unit,
                description=op["drag_hpi_amplitude"].description,
                execution_id=execution_id,
            ),
        }
        figures: list[go.Figure] = []
        return PostProcessResult(output_parameters=output_param, figures=figures)

    def run(self, exp: Experiment, qid: str) -> RunResult:
        labels = [convert_label(qid)]
        result = exp.calibrate_drag_hpi_pulse(
            targets=labels,
            n_rotations=4,
            n_turns=1,
            n_iterations=2,
            shots=self.input_parameters["shots"],
            interval=self.input_parameters["interval"],
        )
        exp.calib_note.save()
        return RunResult(raw_result=result)
