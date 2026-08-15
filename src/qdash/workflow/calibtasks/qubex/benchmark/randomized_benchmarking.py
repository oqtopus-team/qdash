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


class RandomizedBenchmarking(QubexTask):
    """Task to perform randomized benchmarking."""

    name: str = "RandomizedBenchmarking"
    task_type: str = "qubit"
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
        "average_gate_fidelity": OutputParameterSpec(
            unit="a.u.",
            description="Average gate fidelity",
        ),
        "depolarizing_rate": OutputParameterSpec(
            unit="a.u.",
            description="Depolarization rate of the qubit",
        ),
    }

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        self.get_experiment(backend)
        label = self.get_qubit_label(backend, qid)
        result = run_result.raw_result
        self.output_parameters["average_gate_fidelity"].value = result[label]["avg_gate_fidelity"]
        self.output_parameters["average_gate_fidelity"].error = result[label][
            "avg_gate_fidelity_err"
        ]
        self.output_parameters["depolarizing_rate"].value = result[label]["depolarizing_rate"]
        output_parameters = self.attach_execution_id(execution_id)
        figures = [result[label]["fig"]]
        return PostProcessResult(output_parameters=output_parameters, figures=figures)

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        exp = self.get_experiment(backend)
        label = self.get_qubit_label(backend, qid)
        readout_amp_param = self.input_parameters["readout_amplitude"]
        if readout_amp_param is not None:
            exp.params.readout_amplitude[label] = readout_amp_param.value
        result = exp.randomized_benchmarking(
            targets=label,
            n_trials=self.run_parameters["n_trials"].get_value(),
            save_image=False,
            n_shots=self.run_parameters["shots"].get_value(),
            shot_interval=self.run_parameters["interval"].get_value(),
        )
        self.save_calibration(backend)
        r2 = result[label]["r2"]
        return RunResult(raw_result=result, r2={qid: r2})
