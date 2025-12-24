from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    import plotly.graph_objs as go
from qdash.datamodel.task import ParameterModel, RunParameterModel
from qdash.workflow.calibtasks.base import (
    PostProcessResult,
    RunResult,
)
from qdash.workflow.calibtasks.qubex.base import QubexTask
from qdash.workflow.engine.backend.qubex import QubexBackend
from qubex.experiment.experiment_constants import CALIBRATION_SHOTS, DRAG_PI_DURATION
from qubex.measurement.measurement import DEFAULT_INTERVAL


class CreateDRAGPIPulse(QubexTask):
    """Task to create the DRAG pi pulse."""

    name: str = "CreateDRAGPIPulse"
    task_type: str = "qubit"
    input_parameters: ClassVar[dict[str, ParameterModel]] = {}
    run_parameters: ClassVar[dict[str, RunParameterModel]] = {
        "duration": RunParameterModel(
            unit="ns",
            value_type="int",
            value=DRAG_PI_DURATION,
            description="PI pulse length",
        ),
        "shots": RunParameterModel(
            unit="a.u.",
            value_type="int",
            value=CALIBRATION_SHOTS,
            description="Number of shots",
        ),
        "interval": RunParameterModel(
            unit="ns",
            value_type="int",
            value=DEFAULT_INTERVAL,
            description="Time interval",
        ),
    }
    output_parameters: ClassVar[dict[str, ParameterModel]] = {
        "drag_pi_beta": ParameterModel(unit="", description="DRAG PI pulse beta"),
        "drag_pi_amplitude": ParameterModel(unit="", description="DRAG PI pulse amplitude"),
    }

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        self.get_experiment(backend)
        label = self.get_qubit_label(backend, qid)
        result = run_result.raw_result
        self.output_parameters["drag_pi_beta"].value = result["beta"][label]
        self.output_parameters["drag_pi_amplitude"].value = result["amplitude"][label]["amplitude"]
        output_parameters = self.attach_execution_id(execution_id)
        figures: list[go.Figure] = [result["amplitude"][label]["fig"]]
        return PostProcessResult(output_parameters=output_parameters, figures=figures)

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        exp = self.get_experiment(backend)
        labels = [exp.get_qubit_label(int(qid))]
        result = exp.calibrate_drag_pi_pulse(
            targets=labels,
            n_rotations=4,
            n_turns=1,
            n_iterations=2,
            duration=self.run_parameters["duration"].get_value(),
            shots=self.run_parameters["shots"].get_value(),
            interval=self.run_parameters["interval"].get_value(),
        )
        self.save_calibration(backend)
        r2 = result["amplitude"][exp.get_qubit_label(int(qid))]["r2"]
        return RunResult(raw_result=result, r2={qid: r2})
