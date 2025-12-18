from typing import ClassVar

import numpy as np
from qdash.datamodel.task import InputParameterModel, OutputParameterModel
from qdash.workflow.caltasks.base import (
    PostProcessResult,
    RunResult,
)
from qdash.workflow.caltasks.qubex.base import QubexTask
from qdash.workflow.engine.backend.qubex import QubexBackend
from qubex.measurement.measurement import DEFAULT_INTERVAL, DEFAULT_SHOTS
from qdash.workflow.engine.calibration.task.types import TaskTypes


class CheckT1(QubexTask):
    """Task to check the T1 time."""

    name: str = "CheckT1"
    task_type = TaskTypes.QUBIT
    input_parameters: ClassVar[dict[str, InputParameterModel]] = {
        "time_range": InputParameterModel(
            unit="ns",
            value_type="np.logspace",
            value=(np.log10(100), np.log10(500 * 1000), 51),
            description="Time range for T1 time",
        ),
        "shots": InputParameterModel(
            unit="",
            value_type="int",
            value=DEFAULT_SHOTS,
            description="Number of shots for T1 time",
        ),
        "interval": InputParameterModel(
            unit="ns",
            value_type="int",
            value=DEFAULT_INTERVAL,
            description="Time interval for T1 time",
        ),
    }
    output_parameters: ClassVar[dict[str, OutputParameterModel]] = {
        "t1": OutputParameterModel(unit="μs", description="T1 time"),
    }

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        self.get_experiment(backend)
        label = self.get_qubit_label(backend, qid)
        result = run_result.raw_result
        self.output_parameters["t1"].value = result.data[label].t1 * 0.001  # convert to μs
        self.output_parameters["t1"].error = result.data[label].t1_err * 0.001  # convert to μs
        output_parameters = self.attach_execution_id(execution_id)
        figures = [result.data[label].fit()["fig"]]
        return PostProcessResult(output_parameters=output_parameters, figures=figures)

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        exp = self.get_experiment(backend)
        labels = [exp.get_qubit_label(int(qid))]

        # Apply frequency override if qubit_frequency was explicitly provided
        with self._apply_frequency_override(backend, qid):
            result = exp.t1_experiment(
                time_range=self.input_parameters["time_range"].get_value(),
                shots=self.input_parameters["shots"].get_value(),
                interval=self.input_parameters["interval"].get_value(),
                targets=labels,
            )

        self.save_calibration(backend)
        r2 = result.data[exp.get_qubit_label(int(qid))].r2
        return RunResult(raw_result=result, r2={qid: r2})
