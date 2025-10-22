from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    import plotly.graph_objs as go
from qdash.datamodel.task import InputParameterModel, OutputParameterModel
from qdash.workflow.core.session.qubex import QubexSession
from qdash.workflow.tasks.base import (
    PostProcessResult,
    RunResult,
)
from qdash.workflow.tasks.qubex.base import QubexTask
from qubex.experiment.experiment_constants import CALIBRATION_SHOTS, DRAG_HPI_DURATION
from qubex.measurement.measurement import DEFAULT_INTERVAL


class CreateDRAGHPIPulse(QubexTask):
    """Task to create the DRAG HPI pulse."""

    name: str = "CreateDRAGHPIPulse"
    task_type: str = "qubit"
    input_parameters: ClassVar[dict[str, InputParameterModel]] = {
        "duration": InputParameterModel(
            unit="ns",
            value_type="int",
            value=DRAG_HPI_DURATION,
            description="HPI pulse length",
        ),
        "shots": InputParameterModel(
            unit="a.u.",
            value_type="int",
            value=CALIBRATION_SHOTS,
            description="Number of shots",
        ),
        "interval": InputParameterModel(
            unit="ns",
            value_type="int",
            value=DEFAULT_INTERVAL,
            description="Time interval",
        ),
    }
    output_parameters: ClassVar[dict[str, OutputParameterModel]] = {
        "drag_hpi_beta": OutputParameterModel(unit="a.u.", description="DRAG HPI pulse beta"),
        "drag_hpi_amplitude": OutputParameterModel(unit="a.u.", description="DRAG HPI pulse amplitude"),
    }

    def postprocess(
        self, session: QubexSession, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        exp = self.get_experiment(session)
        label = self.get_qubit_label(session, qid)
        result = run_result.raw_result
        self.output_parameters["drag_hpi_beta"].value = result["beta"][label]
        self.output_parameters["drag_hpi_amplitude"].value = result["amplitude"][label]["amplitude"]
        output_parameters = self.attach_execution_id(execution_id)
        figures: list[go.Figure] = [result["amplitude"][label]["fig"]]
        return PostProcessResult(output_parameters=output_parameters, figures=figures)

    def run(self, session: QubexSession, qid: str) -> RunResult:
        exp = self.get_experiment(session)
        labels = [exp.get_qubit_label(int(qid))]
        result = exp.calibrate_drag_hpi_pulse(
            targets=labels,
            n_rotations=4,
            n_turns=1,
            n_iterations=2,
            duration=self.input_parameters["duration"].get_value(),
            shots=self.input_parameters["shots"].get_value(),
            interval=self.input_parameters["interval"].get_value(),
        )
        self.save_calibration(session)
        r2 = result["amplitude"][exp.get_qubit_label(int(qid))]["r2"]
        return RunResult(raw_result=result, r2={qid: r2})
