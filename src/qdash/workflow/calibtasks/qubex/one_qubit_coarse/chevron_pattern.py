import math
from typing import ClassVar

import numpy as np
from qdash.datamodel.task import ParameterModel, RunParameterModel
from qdash.workflow.calibtasks.base import (
    PostProcessResult,
    PreProcessResult,
    RunResult,
)
from qdash.workflow.calibtasks.qubex.base import QubexTask
from qdash.workflow.engine.backend.qubex import QubexBackend
from qubex.measurement.measurement import DEFAULT_READOUT_DURATION

DEFAULT_READOUT_AMPLITUDE = 0.2
DEFAULT_CONTROL_AMPLITUDE = 0.0625
CONTROL_AMPLITUDE_MIN = 1e-4
CONTROL_AMPLITUDE_MAX = 1.0


class ChevronPattern(QubexTask):
    """Task to check the chevron pattern."""

    name: str = "ChevronPattern"
    task_type: str = "qubit"
    timeout: int = 60 * 240
    input_parameters: ClassVar[dict[str, ParameterModel | None]] = {
        "qubit_frequency": None,
        "readout_frequency": None,
        "control_amplitude": ParameterModel(
            value=0.0625, unit="a.u.", description="Control pulse amplitude"
        ),
        "readout_length": ParameterModel(
            value=DEFAULT_READOUT_DURATION, unit="ns", description="Readout pulse length"
        ),
    }
    run_parameters: ClassVar[dict[str, RunParameterModel]] = {
        "readout_amplitude": RunParameterModel(
            unit="a.u.",
            value_type="float",
            value=DEFAULT_READOUT_AMPLITUDE,
            description="Readout amplitude",
        ),
    }
    output_parameters: ClassVar[dict[str, ParameterModel]] = {
        "qubit_frequency": ParameterModel(unit="GHz", description="Qubit bare frequency"),
        "readout_amplitude": ParameterModel(
            unit="a.u.", description="Readout amplitude used for chevron pattern"
        ),
    }

    def preprocess(self, backend: QubexBackend, qid: str) -> PreProcessResult:
        """Preprocess: load params from DB and validate control_amplitude."""
        result = super().preprocess(backend, qid)

        # Validate control_amplitude from DB; use default if invalid
        param = self.input_parameters.get("control_amplitude")
        value = param.value if param is not None else None
        if value is None or not isinstance(value, (int, float)) or math.isnan(value) or value <= CONTROL_AMPLITUDE_MIN or value >= CONTROL_AMPLITUDE_MAX:
            print(
                f"control_amplitude={value} is out of range "
                f"({CONTROL_AMPLITUDE_MIN}, {CONTROL_AMPLITUDE_MAX}), "
                f"using default={DEFAULT_CONTROL_AMPLITUDE}"
            )
            if param is None:
                self.input_parameters["control_amplitude"] = ParameterModel(
                    value=DEFAULT_CONTROL_AMPLITUDE,
                    unit="a.u.",
                    description="Control pulse amplitude (default)",
                )
            else:
                param.value = DEFAULT_CONTROL_AMPLITUDE

        return result

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        self.get_experiment(backend)
        label = self.get_qubit_label(backend, qid)
        result = run_result.raw_result
        self.output_parameters["qubit_frequency"].value = result["resonant_frequencies"][label]
        # Record the readout_amplitude actually used
        ra_param = self.run_parameters.get("readout_amplitude")
        if ra_param is not None:
            self.output_parameters["readout_amplitude"].value = ra_param.get_value()
        output_parameters = self.attach_execution_id(execution_id)
        figures = [result["fig"][label]]
        return PostProcessResult(output_parameters=output_parameters, figures=figures)

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        exp = self.get_experiment(backend)
        labels = [exp.get_qubit_label(int(qid))]

        readout_frequency = self.input_parameters["readout_frequency"]
        qubit_frequency = self.input_parameters["qubit_frequency"]
        control_amplitude = self.input_parameters["control_amplitude"]
        assert readout_frequency is not None
        assert qubit_frequency is not None
        assert control_amplitude is not None

        # Get readout_amplitude from run_parameters
        ra_param = self.run_parameters.get("readout_amplitude")
        readout_amp = ra_param.get_value() if ra_param is not None else DEFAULT_READOUT_AMPLITUDE

        # Fallback to default if control_amplitude value is invalid
        ctrl_amp_value = control_amplitude.value
        if ctrl_amp_value is None or not isinstance(ctrl_amp_value, (int, float)) or math.isnan(ctrl_amp_value) or ctrl_amp_value <= CONTROL_AMPLITUDE_MIN or ctrl_amp_value >= CONTROL_AMPLITUDE_MAX:
            print(
                f"[run] control_amplitude={ctrl_amp_value} is invalid for {labels[0]}, "
                f"using default={DEFAULT_CONTROL_AMPLITUDE}"
            )
            ctrl_amp_value = DEFAULT_CONTROL_AMPLITUDE

        print(
            f"[run] ChevronPattern params for {labels[0]}: "
            f"control_amplitude={ctrl_amp_value}, "
            f"qubit_frequency={qubit_frequency.value}, "
            f"readout_amplitude={readout_amp}, "
            f"readout_frequency={readout_frequency.value}"
        )

        exp.params.readout_amplitude[labels[0]] = readout_amp
        with exp.modified_frequencies({"R" + labels[0]: readout_frequency.value}):
            result = exp.chevron_pattern(
                amplitudes={labels[0]: ctrl_amp_value},
                frequencies={labels[0]: qubit_frequency.value},
                targets=labels,
                detuning_range=np.linspace(-0.05, 0.05, 51),
                time_range=np.arange(0, 201, 4),
            )

        self.save_calibration(backend)
        return RunResult(raw_result=result)
