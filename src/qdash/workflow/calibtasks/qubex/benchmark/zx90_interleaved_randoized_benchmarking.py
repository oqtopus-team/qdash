from typing import ClassVar

from qdash.datamodel.task import ParameterModel, RunParameterModel
from qdash.workflow.calibtasks.base import (
    PostProcessResult,
    RunResult,
)
from qdash.workflow.calibtasks.qubex.base import QubexTask
from qdash.workflow.engine.backend.qubex import QubexBackend
from qubex.experiment.experiment_constants import CALIBRATION_SHOTS
from qubex.measurement.measurement import DEFAULT_INTERVAL


class ZX90InterleavedRandomizedBenchmarking(QubexTask):
    """Task to perform ZX90 interleaved randomized benchmarking."""

    name: str = "ZX90InterleavedRandomizedBenchmarking"
    task_type: str = "coupling"
    timeout: int = 60 * 30  # 30 minutes
    run_parameters: ClassVar[dict[str, RunParameterModel]] = {
        "n_trials": RunParameterModel(
            unit="a.u.",
            value_type="int",
            value=10,
            description="Number of trials",
        ),
        "shots": RunParameterModel(
            unit="a.u.",
            value_type="int",
            value=CALIBRATION_SHOTS,
            description="Number of shots",
        ),
        "interval": RunParameterModel(
            unit="ns",
            value_type="int",
            value=DEFAULT_INTERVAL,
            description="Time interval",
        ),
    }

    # Input parameters from control and target qubits
    input_parameters: ClassVar[dict[str, ParameterModel | None]] = {
        # Control qubit parameters
        "control_qubit_frequency": ParameterModel(
            parameter_name="qubit_frequency", qid_role="control", unit="GHz"
        ),
        "control_drag_hpi_amplitude": ParameterModel(
            parameter_name="drag_hpi_amplitude", qid_role="control", unit="a.u."
        ),
        "control_drag_hpi_length": ParameterModel(
            parameter_name="drag_hpi_length", qid_role="control", unit="ns"
        ),
        "control_drag_hpi_beta": ParameterModel(
            parameter_name="drag_hpi_beta", qid_role="control", unit="a.u."
        ),
        "control_readout_frequency": ParameterModel(
            parameter_name="readout_frequency", qid_role="control", unit="GHz"
        ),
        "control_readout_amplitude": ParameterModel(
            parameter_name="readout_amplitude", qid_role="control", unit="a.u."
        ),
        "control_readout_length": ParameterModel(
            parameter_name="readout_length", qid_role="control", unit="ns"
        ),
        # Target qubit parameters
        "target_qubit_frequency": ParameterModel(
            parameter_name="qubit_frequency", qid_role="target", unit="GHz"
        ),
        "target_readout_frequency": ParameterModel(
            parameter_name="readout_frequency", qid_role="target", unit="GHz"
        ),
        "target_readout_amplitude": ParameterModel(
            parameter_name="readout_amplitude", qid_role="target", unit="a.u."
        ),
        "target_readout_length": ParameterModel(
            parameter_name="readout_length", qid_role="target", unit="ns"
        ),
        # CR parameters (from previous calibration)
        "cr_amplitude": ParameterModel(
            parameter_name="cr_amplitude", qid_role="control", unit="a.u."
        ),
        "cr_phase": ParameterModel(parameter_name="cr_phase", qid_role="control", unit="a.u."),
        "cancel_amplitude": ParameterModel(
            parameter_name="cancel_amplitude", qid_role="target", unit="a.u."
        ),
        "cancel_phase": ParameterModel(
            parameter_name="cancel_phase", qid_role="target", unit="a.u."
        ),
        "cancel_beta": ParameterModel(parameter_name="cancel_beta", qid_role="target", unit="a.u."),
        "rotary_amplitude": ParameterModel(
            parameter_name="rotary_amplitude", qid_role="control", unit="a.u."
        ),
        "zx_rotation_rate": ParameterModel(
            parameter_name="zx_rotation_rate", qid_role="coupling", unit="a.u."
        ),
    }

    output_parameters: ClassVar[dict[str, ParameterModel]] = {
        "zx90_gate_fidelity": ParameterModel(
            qid_role="coupling",
            unit="a.u.",
            description="ZX90 gate fidelity",
            value_type="float",
        ),
        "zx90_depolarizing_rate": ParameterModel(
            qid_role="coupling",
            unit="a.u.",
            description="Depolarization error of the ZX90 gate",
            value_type="float",
        ),
    }

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        exp = self.get_experiment(backend)
        label = "-".join(
            [exp.get_qubit_label(int(q)) for q in qid.split("-")]
        )  # e.g., "0-1" → "Q00-Q01"
        result = run_result.raw_result
        self.output_parameters["zx90_gate_fidelity"].value = result[label]["gate_fidelity"]
        self.output_parameters["zx90_gate_fidelity"].error = result[label]["gate_fidelity_err"]
        self.output_parameters["zx90_depolarizing_rate"].value = result[label]["rb_fit_result"][
            "depolarizing_rate"
        ]
        output_parameters = self.attach_execution_id(execution_id)
        figures = [result[label]["fig"]]
        return PostProcessResult(output_parameters=output_parameters, figures=figures)

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        exp = self.get_experiment(backend)
        label = "-".join(
            [exp.get_qubit_label(int(q)) for q in qid.split("-")]
        )  # e.g., "0-1" → "Q00-Q01"
        result = exp.interleaved_randomized_benchmarking(
            targets=label,
            interleaved_clifford="ZX90",
            n_trials=self.run_parameters["n_trials"].get_value(),
            save_image=False,
            shots=self.run_parameters["shots"].get_value(),
            interval=self.run_parameters["interval"].get_value(),
        )
        self.save_calibration(backend)
        r2 = result[label]["rb_fit_result"]["r2"]
        return RunResult(raw_result=result, r2={qid: r2})
