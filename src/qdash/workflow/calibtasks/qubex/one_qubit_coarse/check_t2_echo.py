from typing import ClassVar

import numpy as np
from qubex.measurement.measurement_defaults import (
    DEFAULT_INTERVAL,
    DEFAULT_READOUT_DURATION,
    DEFAULT_SHOTS,
)

from qdash.datamodel.task import (
    InputParameterSpec,
    OutputParameterSpec,
    RunParameterSpec,
)
from qdash.workflow.calibtasks.base import (
    PostProcessResult,
    RunResult,
)
from qdash.workflow.calibtasks.qubex.base import QubexTask
from qdash.workflow.engine.backend.qubex import QubexBackend


class CheckT2Echo(QubexTask):
    """Task to check the T2 echo time."""

    name: str = "CheckT2Echo"
    task_type: str = "qubit"
    input_spec: ClassVar[dict[str, InputParameterSpec]] = {
        "qubit_frequency": InputParameterSpec.required_database(),
        "hpi_amplitude": InputParameterSpec.required_database(),
        "hpi_duration": InputParameterSpec.required_database(),
        "readout_amplitude": InputParameterSpec.required_database(),
        "readout_frequency": InputParameterSpec.required_database(),
        "readout_duration": InputParameterSpec.database_or_default(
            default=DEFAULT_READOUT_DURATION,
            unit="ns",
            description="Readout pulse duration",
        ),
    }
    run_spec: ClassVar[dict[str, RunParameterSpec]] = {
        "time_range": RunParameterSpec(
            unit="ns",
            value_type="np.logspace",
            default=(np.log10(300), np.log10(100 * 1000), 51),
            description="Time range for T2 echo time",
        ),
        "shots": RunParameterSpec(
            unit="",
            value_type="int",
            default=DEFAULT_SHOTS,
            description="Number of shots for T2 echo time",
        ),
        "interval": RunParameterSpec(
            unit="ns",
            value_type="int",
            default=DEFAULT_INTERVAL,
            description="Time interval for T2 echo time",
        ),
    }
    output_spec: ClassVar[dict[str, OutputParameterSpec]] = {
        "t2_echo": OutputParameterSpec(unit="μs", description="T2 echo time"),
    }

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        self.get_experiment(backend)
        label = self.get_qubit_label(backend, qid)
        result = run_result.raw_result
        self.output_parameters["t2_echo"].value = result.data[label].t2 * 0.001  # convert to μs
        self.output_parameters["t2_echo"].error = result.data[label].t2_err * 0.001  # convert to μs
        output_parameters = self.attach_execution_id(execution_id)
        figures = [result.data[label].fit()["fig"]]
        return PostProcessResult(output_parameters=output_parameters, figures=figures)

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        exp = self.get_experiment(backend)
        labels = [exp.get_qubit_label(int(qid))]
        readout_amp_param = self.input_parameters["readout_amplitude"]
        if readout_amp_param is not None:
            exp.params.readout_amplitude[labels[0]] = readout_amp_param.value

        # Apply frequency override if qubit_frequency was explicitly provided
        with self._apply_frequency_override(backend, qid):
            result = exp.t2_experiment(
                labels,
                time_range=self.run_parameters["time_range"].get_value(),
                n_shots=self.run_parameters["shots"].get_value(),
                shot_interval=self.run_parameters["interval"].get_value(),
                save_image=False,
            )

        r2 = result.data[exp.get_qubit_label(int(qid))].r2
        self.save_calibration(backend)
        return RunResult(raw_result=result, r2={qid: r2})
