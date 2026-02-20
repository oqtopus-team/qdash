from typing import Any, ClassVar

from qdash.datamodel.task import ParameterModel, RunParameterModel
from qdash.workflow.calibtasks.base import (
    PostProcessResult,
    RunResult,
)
from qdash.workflow.calibtasks.qubex.base import QubexTask
from qdash.workflow.engine.backend.qubex import QubexBackend
from qubex.experiment.experiment_constants import CALIBRATION_SHOTS
from qubex.measurement.measurement import DEFAULT_INTERVAL


class CheckBellState(QubexTask):
    """Task to check the bell state."""

    name: str = "CheckBellState"
    task_type: str = "coupling"
    timeout: int = 60 * 25  # 25 minutes
    run_parameters: ClassVar[dict[str, RunParameterModel]] = {
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

    output_parameters: ClassVar[dict[str, ParameterModel]] = {}

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        result = run_result.raw_result
        output_parameters = self.attach_execution_id(execution_id)
        figures: list[Any] = [result["figure"]]
        raw_data: list[Any] = []
        return PostProcessResult(
            output_parameters=output_parameters, figures=figures, raw_data=raw_data
        )

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        exp = self.get_experiment(backend)
        control, target = (
            exp.get_qubit_label(int(q)) for q in qid.split("-")
        )  # e.g., "0-1" → "Q00","Q01"
        result = exp.measure_bell_state(
            control,
            target,
            shots=self.run_parameters["shots"].get_value(),
            interval=self.run_parameters["interval"].get_value(),
        )
        self.save_calibration(backend)
        return RunResult(raw_result=result)
