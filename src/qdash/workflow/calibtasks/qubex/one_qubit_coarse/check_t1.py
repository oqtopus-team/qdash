from typing import ClassVar

import numpy as np
from qdash.datamodel.task import ParameterModel, RunParameterModel
from qdash.workflow.calibtasks.base import (
    PostProcessResult,
    RunResult,
)
from qdash.workflow.calibtasks.qubex.base import QubexTask
from qdash.workflow.engine.backend.qubex import QubexBackend
from qubex.measurement.measurement import DEFAULT_INTERVAL, DEFAULT_READOUT_DURATION, DEFAULT_SHOTS


class CheckT1(QubexTask):
    """Task to check the T1 time."""

    name: str = "CheckT1"
    task_type: str = "qubit"
    input_parameters: ClassVar[dict[str, ParameterModel | None]] = {
        "qubit_frequency": None,  # Load from DB
        "hpi_amplitude": None,  # Load from DB
        "hpi_length": None,  # Load from DB
        "readout_amplitude": None,  # Load from DB
        "readout_frequency": None,  # Load from DB
        "readout_length": ParameterModel(
            value=DEFAULT_READOUT_DURATION, unit="ns", description="Readout pulse length"
        ),
    }
    run_parameters: ClassVar[dict[str, RunParameterModel]] = {
        "time_range": RunParameterModel(
            unit="ns",
            value_type="np.logspace",
            value=(np.log10(100), np.log10(500 * 1000), 51),
            description="Time range for T1 time",
        ),
        "shots": RunParameterModel(
            unit="",
            value_type="int",
            value=DEFAULT_SHOTS,
            description="Number of shots for T1 time",
        ),
        "interval": RunParameterModel(
            unit="ns",
            value_type="int",
            value=DEFAULT_INTERVAL,
            description="Time interval for T1 time",
        ),
    }
    output_parameters: ClassVar[dict[str, ParameterModel]] = {
        "t1": ParameterModel(unit="μs", description="T1 time"),
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
                time_range=self.run_parameters["time_range"].get_value(),
                shots=self.run_parameters["shots"].get_value(),
                interval=self.run_parameters["interval"].get_value(),
                targets=labels,
            )

        self.save_calibration(backend)
        r2 = result.data[exp.get_qubit_label(int(qid))].r2
        return RunResult(raw_result=result, r2={qid: r2})
