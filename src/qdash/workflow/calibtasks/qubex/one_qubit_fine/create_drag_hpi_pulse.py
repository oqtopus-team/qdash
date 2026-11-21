from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    import plotly.graph_objs as go
from qubex.experiment.experiment_constants import CALIBRATION_SHOTS, DRAG_HPI_DURATION
from qubex.measurement.measurement_defaults import DEFAULT_INTERVAL

from qdash.datamodel.task import (
    InputParameterSpec,
    OutputParameterSpec,
    RunParameterSpec,
    TaskDocumentation,
    TaskReference,
)
from qdash.workflow.calibtasks.base import (
    PostProcessResult,
    RunResult,
)
from qdash.workflow.calibtasks.qubex.base import (
    QubexTask,
    readout_duration_run_parameter,
    required_rabi_normalization_inputs,
)
from qdash.workflow.calibtasks.qubex.validation import finite_value_error, first_validation_error
from qdash.workflow.engine.backend.qubex import QubexBackend


class CreateDRAGHPIPulse(QubexTask):
    """Task to create the DRAG HPI pulse."""

    name: str = "CreateDRAGHPIPulse"
    task_type: str = "qubit"
    documentation: ClassVar[TaskDocumentation] = TaskDocumentation(
        description=(
            "Calibrates a 16 ns DRAG half-pi pulse: two iterations of amplitude calibration and"
            " a DRAG beta sweep whose zero crossing cancels the phase error amplified by "
            "repeated X90 and -X90 pairs. It writes drag_hpi_amplitude, drag_hpi_beta, and "
            "drag_hpi_duration."
        ),
        when_to_use=(
            "Run it after CheckRabi when gates must be short or high fidelity. "
            "RandomizedBenchmarking, ReadoutClassification, and the two-qubit tasks use the "
            "DRAG half-pi pulse."
        ),
        prerequisites=(
            (
                "Rabi parameters from a CheckRabi run under the current readout_duration, with "
                "rabi_r2 at or above the R² threshold; they normalize the IQ data."
            ),
            (
                "control_frequency (or qubit_frequency), readout_frequency (or "
                "resonator_frequency), and readout_amplitude are stored for the qubit."
            ),
        ),
        references=(
            TaskReference(
                title="Simple Pulses for Elimination of Leakage in Weakly Nonlinear Qubits",
                url="https://doi.org/10.1103/PhysRevLett.103.110501",
                relevance=(
                    "DRAG derivative correction that suppresses leakage and phase error in a "
                    "weakly anharmonic qubit."
                ),
            ),
            TaskReference(
                title=(
                    "Analytic control methods for high-fidelity unitary operations in a weakly "
                    "nonlinear oscillator"
                ),
                url="https://doi.org/10.1103/PhysRevA.83.012308",
                relevance="Analysis of DRAG pulse families and their phase-error terms.",
            ),
            TaskReference(
                title="Reduced phase error through optimized control of a superconducting qubit",
                url="https://doi.org/10.1103/PhysRevA.82.042339",
                relevance=(
                    "Amplified phase error sequences of pseudo-identity pairs, similar to the "
                    "beta sweep; shown on a phase qubit."
                ),
            ),
        ),
    )
    input_spec: ClassVar[dict[str, InputParameterSpec]] = {
        # RabiParam calibrates the pulse and normalizes IQ; validate its readout context.
        **required_rabi_normalization_inputs(),
        "control_frequency": InputParameterSpec.required_database(
            fallback_parameter_names=("qubit_frequency",)
        ),
        "readout_amplitude": InputParameterSpec.required_database(),
        "readout_frequency": InputParameterSpec.required_database(
            fallback_parameter_names=("resonator_frequency",)
        ),
    }
    run_spec: ClassVar[dict[str, RunParameterSpec]] = {
        "readout_duration": readout_duration_run_parameter(),
        "drag_hpi_duration": RunParameterSpec(
            unit="ns",
            value_type="int",
            default=DRAG_HPI_DURATION,
            description="HPI pulse duration",
        ),
        "shots": RunParameterSpec(
            unit="a.u.",
            value_type="int",
            default=CALIBRATION_SHOTS,
            description="Number of shots",
        ),
        "interval": RunParameterSpec(
            unit="ns",
            value_type="int",
            default=DEFAULT_INTERVAL,
            description="Time interval",
        ),
    }
    output_spec: ClassVar[dict[str, OutputParameterSpec]] = {
        "drag_hpi_beta": OutputParameterSpec(unit="a.u.", description="DRAG HPI pulse beta"),
        "drag_hpi_amplitude": OutputParameterSpec(
            unit="a.u.", description="DRAG HPI pulse amplitude"
        ),
        "drag_hpi_duration": OutputParameterSpec(
            default=None, unit="ns", description="DRAG HPI pulse duration"
        ),
    }

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        self.get_experiment(backend)
        label = self.get_qubit_label(backend, qid)
        result = run_result.raw_result
        self.output_parameters["drag_hpi_beta"].value = result["beta"][label]
        self.output_parameters["drag_hpi_amplitude"].value = result["amplitude"][label]["amplitude"]
        self.output_parameters["drag_hpi_duration"].value = self.run_parameters[
            "drag_hpi_duration"
        ].get_value()
        output_parameters = self.attach_execution_id(execution_id)
        figures: list[go.Figure] = [result["amplitude"][label]["fig"]]
        validation_error = first_validation_error(
            finite_value_error(
                self.output_parameters["drag_hpi_beta"].value,
                f"CreateDRAGHPIPulse drag_hpi_beta for {label}",
            ),
            finite_value_error(
                self.output_parameters["drag_hpi_amplitude"].value,
                f"CreateDRAGHPIPulse drag_hpi_amplitude for {label}",
                minimum=0.0,
                maximum=1.0,
            ),
        )
        return PostProcessResult(
            output_parameters=output_parameters,
            figures=figures,
            validation_error=validation_error,
        )

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        exp = self.get_experiment(backend)
        labels = [exp.get_qubit_label(int(qid))]
        readout_amp_param = self.input_parameters["readout_amplitude"]
        if readout_amp_param is not None:
            exp.params.readout_amplitude[labels[0]] = readout_amp_param.value
        control_amp_param = self.input_parameters["control_amplitude"]
        if control_amp_param is not None:
            exp.params.control_amplitude[labels[0]] = control_amp_param.value
        self._restore_rabi_context(backend, qid)
        result = exp.calibrate_drag_hpi_pulse(
            targets=labels,
            n_rotations=4,
            n_turns=1,
            n_iterations=2,
            duration=self.run_parameters["drag_hpi_duration"].get_value(),
            n_shots=self.run_parameters["shots"].get_value(),
            shot_interval=self.run_parameters["interval"].get_value(),
        )
        self.save_calibration(backend)
        r2 = result["amplitude"][exp.get_qubit_label(int(qid))]["r2"]
        return RunResult(raw_result=result, r2={qid: r2})
