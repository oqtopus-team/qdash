from typing import ClassVar

from qdash.datamodel.task import ParameterModel, RunParameterModel
from qdash.workflow.calibtasks.base import (
    PostProcessResult,
    RunResult,
)
from qdash.workflow.calibtasks.qubex.base import QubexTask
from qdash.workflow.engine.backend.qubex import QubexBackend
from qubex.experiment.experiment_constants import CALIBRATION_SHOTS, PI_DURATION
from qubex.measurement.measurement import DEFAULT_INTERVAL


class CreatePIPulse(QubexTask):
    """Task to create the pi pulse."""

    name: str = "CreatePIPulse"
    task_type: str = "qubit"
    run_parameters: ClassVar[dict[str, RunParameterModel]] = {
        "duration": RunParameterModel(
            unit="ns", value_type="int", value=PI_DURATION, description="PI pulse length"
        ),
        "shots": RunParameterModel(
            unit="",
            value_type="int",
            value=CALIBRATION_SHOTS,
            description="Number of shots for calibration",
        ),
        "interval": RunParameterModel(
            unit="ns",
            value_type="int",
            value=DEFAULT_INTERVAL,
            description="Time interval for calibration",
        ),
    }
    output_parameters: ClassVar[dict[str, ParameterModel]] = {
        "pi_amplitude": ParameterModel(unit="", description="PI pulse amplitude")
    }

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        self.get_experiment(backend)
        label = self.get_qubit_label(backend, qid)
        result = run_result.raw_result
        self.output_parameters["pi_amplitude"].value = result.data[label].calib_value
        output_parameters = self.attach_execution_id(execution_id)
        figures = [result.data[label].fit()["fig"]]
        return PostProcessResult(output_parameters=output_parameters, figures=figures)

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        exp = self.get_experiment(backend)
        labels = [exp.get_qubit_label(int(qid))]
        result = exp.calibrate_pi_pulse(
            targets=labels,
            n_rotations=1,
            duration=self.run_parameters["duration"].get_value(),
            shots=self.run_parameters["shots"].get_value(),
            interval=self.run_parameters["interval"].get_value(),
        )
        self.save_calibration(backend)
        r2 = result.data[exp.get_qubit_label(int(qid))].r2
        return RunResult(raw_result=result, r2={qid: r2})
