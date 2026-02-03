from typing import ClassVar

from qdash.datamodel.task import ParameterModel, RunParameterModel
from qdash.workflow.calibtasks.base import (
    PostProcessResult,
    PreProcessResult,
    RunResult,
)
from qdash.workflow.calibtasks.qubex.base import QubexTask
from qdash.workflow.engine.backend.qubex import QubexBackend
from qubex.experiment.experiment_constants import CALIBRATION_SHOTS
from qubex.measurement.measurement import DEFAULT_INTERVAL, DEFAULT_READOUT_DURATION

DEFAULT_CONTROL_AMPLITUDE = 0.0125
CONTROL_AMPLITUDE_MIN = 1e-4
CONTROL_AMPLITUDE_MAX = 1.0


class CheckRabi(QubexTask):
    """Task to check the Rabi oscillation."""

    name: str = "CheckRabi"
    task_type: str = "qubit"
    input_parameters: ClassVar[dict[str, ParameterModel | None]] = {
        "qubit_frequency": None,
        "control_amplitude": None,
        "readout_amplitude": None,
        "readout_frequency": None,
        "readout_length": ParameterModel(
            value=DEFAULT_READOUT_DURATION, unit="ns", description="Readout pulse length"
        ),
    }
    run_parameters: ClassVar[dict[str, RunParameterModel]] = {
        "time_range": RunParameterModel(
            unit="ns",
            value_type="range",
            value=(0, 401, 8),
            description="Time range for Rabi oscillation",
        ),
        "shots": RunParameterModel(
            unit="a.u.",
            value_type="int",
            value=CALIBRATION_SHOTS,
            description="Number of shots for Rabi oscillation",
        ),
        "interval": RunParameterModel(
            unit="ns",
            value_type="int",
            value=DEFAULT_INTERVAL,
            description="Time interval for Rabi oscillation",
        ),
    }
    output_parameters: ClassVar[dict[str, ParameterModel]] = {
        "rabi_amplitude": ParameterModel(unit="a.u.", description="Rabi oscillation amplitude"),
        "rabi_frequency": ParameterModel(unit="MHz", description="Rabi oscillation frequency"),
        "rabi_phase": ParameterModel(unit="a.u.", description="Rabi oscillation phase"),
        "rabi_offset": ParameterModel(unit="a.u.", description="Rabi oscillation offset"),
        "rabi_angle": ParameterModel(unit="degree", description="Rabi angle (in degree)"),
        "rabi_noise": ParameterModel(unit="a.u.", description="Rabi oscillation noise"),
        "rabi_distance": ParameterModel(unit="a.u.", description="Rabi distance"),
        "rabi_reference_phase": ParameterModel(unit="a.u.", description="Rabi reference phase"),
        "control_amplitude": ParameterModel(unit="a.u.", description="Control pulse amplitude"),
    }

    def preprocess(self, backend: QubexBackend, qid: str) -> PreProcessResult:
        """Preprocess with control_amplitude validation."""
        result = super().preprocess(backend, qid)
        param = self.input_parameters.get("control_amplitude")
        value = param.value if param is not None else None
        if value is None or value <= CONTROL_AMPLITUDE_MIN or value >= CONTROL_AMPLITUDE_MAX:
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
        """Process the results of the task."""
        label = self.get_qubit_label(backend, qid)
        result = run_result.raw_result
        self.output_parameters["rabi_amplitude"].value = result.rabi_params[label].amplitude
        self.output_parameters["rabi_amplitude"].error = result.data[label].fit()["amplitude_err"]
        self.output_parameters["rabi_frequency"].value = (
            result.rabi_params[label].frequency * 1000
        )  # convert to MHz
        self.output_parameters["rabi_frequency"].error = (
            result.data[label].fit()["frequency_err"] * 1000
        )
        self.output_parameters["rabi_phase"].value = result.rabi_params[label].phase
        self.output_parameters["rabi_phase"].error = result.data[label].fit()["phase_err"]
        self.output_parameters["rabi_offset"].value = result.rabi_params[label].offset
        self.output_parameters["rabi_offset"].error = result.data[label].fit()["offset_err"]
        self.output_parameters["rabi_angle"].value = result.rabi_params[label].angle
        self.output_parameters["rabi_noise"].value = result.rabi_params[label].noise
        self.output_parameters["rabi_distance"].value = result.rabi_params[label].distance
        self.output_parameters["rabi_reference_phase"].value = result.rabi_params[
            label
        ].reference_phase
        control_amplitude_param = self.input_parameters["control_amplitude"]
        assert control_amplitude_param is not None
        default_amp = control_amplitude_param.value
        rabi_frequency = self.output_parameters["rabi_frequency"].value
        print("rabi frequency (MHz): ", self.output_parameters["rabi_frequency"].value)
        print("default amplitude (a.u.): ", control_amplitude_param.value)
        ratio = (rabi_frequency / default_amp) / 1000
        self.output_parameters["control_amplitude"].value = 0.0125 / ratio
        output_parameters = self.attach_execution_id(execution_id)
        figures = [result.data[label].fit()["fig"]]
        raw_data = [result.data[label].data]
        return PostProcessResult(
            output_parameters=output_parameters, figures=figures, raw_data=raw_data
        )

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        """Run the task."""
        exp = self.get_experiment(backend)
        label = self.get_qubit_label(backend, qid)

        # Apply frequency override if qubit_frequency was explicitly provided
        control_amplitude_param = self.input_parameters["control_amplitude"]
        qubit_frequency_param = self.input_parameters["qubit_frequency"]
        assert control_amplitude_param is not None
        assert qubit_frequency_param is not None
        # with self._apply_frequency_override(backend, qid):
        result = exp.obtain_rabi_params(
            amplitudes={label: control_amplitude_param.value},
            frequencies={label: qubit_frequency_param.value},
            time_range=self.run_parameters["time_range"].get_value(),
            shots=self.run_parameters["shots"].get_value(),
            interval=self.run_parameters["interval"].get_value(),
            targets=label,
        )

        self.save_calibration(backend)
        r2 = result.rabi_params[label].r2 if result.rabi_params else None
        return RunResult(raw_result=result, r2={qid: r2})
