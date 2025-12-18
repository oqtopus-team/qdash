from typing import ClassVar

from qdash.datamodel.task import InputParameterModel, OutputParameterModel
from qdash.workflow.caltasks.base import (
    PostProcessResult,
    RunResult,
)
from qdash.workflow.caltasks.qubex.base import QubexTask
from qdash.workflow.engine.backend.qubex import QubexBackend
from qubex.experiment.experiment_constants import CALIBRATION_SHOTS, HPI_DURATION
from qubex.measurement.measurement import DEFAULT_INTERVAL
from qdash.workflow.engine.calibration.task.types import TaskTypes


class CreateHPIPulse(QubexTask):
    """Task to create the HPI pulse."""

    name: str = "CreateHPIPulse"
    task_type = TaskTypes.QUBIT
    input_parameters: ClassVar[dict[str, InputParameterModel]] = {
        "duration": InputParameterModel(
            unit="ns", value_type="int", value=HPI_DURATION, description="HPI pulse length"
        ),
        "shots": InputParameterModel(
            unit="",
            value_type="int",
            value=CALIBRATION_SHOTS,
            description="Number of shots for calibration",
        ),
        "interval": InputParameterModel(
            unit="ns",
            value_type="int",
            value=DEFAULT_INTERVAL,
            description="Time interval for calibration",
        ),
    }
    output_parameters: ClassVar[dict[str, OutputParameterModel]] = {
        "hpi_amplitude": OutputParameterModel(unit="", description="HPI pulse amplitude")
    }

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        self.get_experiment(backend)
        label = self.get_qubit_label(backend, qid)
        result = run_result.raw_result
        self.output_parameters["hpi_amplitude"].value = result.data[label].calib_value
        output_parameters = self.attach_execution_id(execution_id)
        figures = [result.data[label].fit()["fig"]]
        return PostProcessResult(output_parameters=output_parameters, figures=figures)

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        exp = self.get_experiment(backend)
        labels = [exp.get_qubit_label(int(qid))]
        result = exp.calibrate_hpi_pulse(
            targets=labels,
            n_rotations=1,
            duration=self.input_parameters["duration"].get_value(),
            shots=self.input_parameters["shots"].get_value(),
            interval=self.input_parameters["interval"].get_value(),
        )
        self.save_calibration(backend)
        r2 = result.data[exp.get_qubit_label(int(qid))].r2
        return RunResult(raw_result=result, r2={qid: r2})
