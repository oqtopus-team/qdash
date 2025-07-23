from typing import ClassVar

import numpy as np
from qdash.datamodel.task import InputParameterModel, OutputParameterModel
from qdash.workflow.core.session.qubex import QubexSession
from qdash.workflow.tasks.base import (
    BaseTask,
    PostProcessResult,
    PreProcessResult,
    RunResult,
)
from qubex.measurement.measurement import DEFAULT_INTERVAL, DEFAULT_SHOTS


class CheckT1(BaseTask):
    """Task to check the T1 time."""

    name: str = "CheckT1"
    backend: str = "qubex"
    task_type: str = "qubit"
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

    def preprocess(self, session: QubexSession, qid: str) -> PreProcessResult:  # noqa: ARG002
        return PreProcessResult(input_parameters=self.input_parameters)

    def postprocess(
        self, session: QubexSession, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        exp = session.get_session()
        label = exp.get_qubit_label(int(qid))
        result = run_result.raw_result
        self.output_parameters["t1"].value = result.data[label].t1 * 0.001  # convert to μs
        self.output_parameters["t1"].error = result.data[label].t1_err * 0.001  # convert to μs
        output_parameters = self.attach_execution_id(execution_id)
        figures = [result.data[label].fit()["fig"]]
        return PostProcessResult(output_parameters=output_parameters, figures=figures)

    def run(self, session: QubexSession, qid: str) -> RunResult:
        exp = session.get_session()
        labels = [exp.get_qubit_label(int(qid))]
        result = exp.t1_experiment(
            time_range=self.input_parameters["time_range"].get_value(),
            shots=self.input_parameters["shots"].get_value(),
            interval=self.input_parameters["interval"].get_value(),
            targets=labels,
        )
        exp.calib_note.save()
        r2 = result.data[exp.get_qubit_label(int(qid))].r2
        return RunResult(raw_result=result, r2={qid: r2})

    def batch_run(self, session: QubexSession, qid: str) -> RunResult:
        """Batch run is not implemented."""
        raise NotImplementedError(
            f"Batch run is not implemented for {self.name} task. Use run method instead."
        )
