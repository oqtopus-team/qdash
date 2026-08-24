from typing import ClassVar

from qubex.experiment.experiment_constants import CALIBRATION_SHOTS
from qubex.measurement.measurement_defaults import DEFAULT_INTERVAL, DEFAULT_READOUT_DURATION

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


class X90InterleavedRandomizedBenchmarking(QubexTask):
    """Task to perform X90 interleaved randomized benchmarking."""

    name: str = "X90InterleavedRandomizedBenchmarking"
    task_type: str = "qubit"
    timeout: int = 60 * 30
    input_spec: ClassVar[dict[str, InputParameterSpec]] = {
        "qubit_frequency": InputParameterSpec.required_database(),
        "drag_hpi_amplitude": InputParameterSpec.required_database(),
        "drag_hpi_length": InputParameterSpec.required_database(),
        "drag_hpi_beta": InputParameterSpec.required_database(),
        "readout_amplitude": InputParameterSpec.required_database(),
        "readout_frequency": InputParameterSpec.required_database(),
        "readout_length": InputParameterSpec.database_or_default(
            default=DEFAULT_READOUT_DURATION,
            unit="ns",
            description="Readout pulse length",
        ),
    }
    run_spec: ClassVar[dict[str, RunParameterSpec]] = {
        "n_trials": RunParameterSpec(
            unit="a.u.",
            value_type="int",
            default=10,
            description="Number of trials",
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
        "x90_gate_fidelity": OutputParameterSpec(
            unit="a.u.",
            description="X90 gate fidelity",
        ),
        "x90_depolarizing_rate": OutputParameterSpec(
            unit="a.u.",
            description="Depolarization error of the X90 gate",
        ),
    }

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        self.get_experiment(backend)
        label = self.get_qubit_label(backend, qid)
        result = run_result.raw_result
        self.output_parameters["x90_gate_fidelity"].value = result[label]["gate_fidelity"]
        self.output_parameters["x90_gate_fidelity"].error = result[label]["gate_fidelity_err"]
        self.output_parameters["x90_depolarizing_rate"].value = result[label]["rb_fit_result"][
            "depolarizing_rate"
        ]
        output_parameters = self.attach_execution_id(execution_id)
        figures = [result[label]["fig"]]
        return PostProcessResult(output_parameters=output_parameters, figures=figures)

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        """Run the X90 interleaved randomized benchmarking task with timeout."""
        exp = self.get_experiment(backend)
        label = self.get_qubit_label(backend, qid)
        readout_amp_param = self.input_parameters["readout_amplitude"]
        if readout_amp_param is not None:
            exp.params.readout_amplitude[label] = readout_amp_param.value
        x90 = {label: exp.drag_hpi_pulse[label]}
        result = exp.interleaved_randomized_benchmarking(
            targets=label,
            interleaved_clifford="X90",
            interleaved_waveform=x90,
            x90=x90,
            n_trials=self.run_parameters["n_trials"].get_value(),
            save_image=False,
            n_shots=self.run_parameters["shots"].get_value(),
            shot_interval=self.run_parameters["interval"].get_value(),
        )
        self.save_calibration(backend)
        r2 = result[label]["rb_fit_result"]["r2"]
        return RunResult(raw_result=result, r2={qid: r2})
