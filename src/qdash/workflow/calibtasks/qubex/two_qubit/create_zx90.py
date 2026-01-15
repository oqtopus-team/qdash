from typing import Any, ClassVar

from qdash.datamodel.task import ParameterModel, RunParameterModel
from qdash.workflow.calibtasks.base import (
    PostProcessResult,
    RunResult,
)
from qdash.workflow.calibtasks.qubex.base import QubexTask
from qdash.workflow.engine.backend.qubex import QubexBackend


class CreateZX90(QubexTask):
    """Task to create ZX90 gate."""

    name: str = "CreateZX90"
    task_type: str = "coupling"
    timeout: int = 60 * 25  # 25 minutes
    run_parameters: ClassVar[dict[str, RunParameterModel]] = {}

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
    }

    # Output parameters with qid_role specifying where each is stored
    output_parameters: ClassVar[dict[str, ParameterModel]] = {
        "cr_amplitude": ParameterModel(
            qid_role="control", unit="a.u.", description="Amplitude of the CR pulse."
        ),
        "cr_phase": ParameterModel(
            qid_role="control", unit="a.u.", description="Phase of the CR pulse."
        ),
        "cancel_amplitude": ParameterModel(
            qid_role="target", unit="a.u.", description="Amplitude of the cancel pulse."
        ),
        "cancel_phase": ParameterModel(
            qid_role="target", unit="a.u.", description="Phase of the cancel pulse."
        ),
        "cancel_beta": ParameterModel(
            qid_role="target", unit="a.u.", description="Beta of the cancel pulse."
        ),
        "rotary_amplitude": ParameterModel(
            qid_role="control", unit="a.u.", description="Amplitude of the rotary pulse."
        ),
        "zx_rotation_rate": ParameterModel(
            qid_role="coupling", unit="a.u.", description="ZX rotation rate."
        ),
    }

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        result = run_result.raw_result
        self.output_parameters["cr_amplitude"].value = result["cr_amplitude"]
        self.output_parameters["cr_phase"].value = result["cr_phase"]
        self.output_parameters["cancel_amplitude"].value = result["cancel_amplitude"]
        self.output_parameters["cancel_phase"].value = result["cancel_phase"]
        self.output_parameters["cancel_beta"].value = result["cancel_beta"]
        self.output_parameters["rotary_amplitude"].value = result["rotary_amplitude"]
        self.output_parameters["zx_rotation_rate"].value = result["zx_rotation_rate"]
        output_parameters = self.attach_execution_id(execution_id)
        figures: list[Any] = [result["n1"], result["n3"], result["fig"]]
        raw_data: list[Any] = []
        return PostProcessResult(
            output_parameters=output_parameters, figures=figures, raw_data=raw_data
        )

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        exp = self.get_experiment(backend)
        control, target = (
            exp.get_qubit_label(int(q)) for q in qid.split("-")
        )  # e.g., "0-1" → "Q00","Q01"
        label = "-".join(
            [exp.get_qubit_label(int(q)) for q in qid.split("-")]
        )  # e.g., "0-1" → "Q00-Q01"
        raw_result = exp.calibrate_zx90(
            control,
            target,
        )
        fit_result = exp.calib_note.get_cr_param(label)
        if fit_result is None:
            err_msg = f"CR parameters for {label} not found."
            raise ValueError(err_msg)
        result = {
            "cr_amplitude": fit_result["cr_amplitude"],
            "cr_phase": fit_result["cr_phase"],
            "cancel_amplitude": fit_result["cancel_amplitude"],
            "cancel_phase": fit_result["cancel_phase"],
            "cancel_beta": fit_result["cancel_beta"],
            "rotary_amplitude": fit_result["rotary_amplitude"],
            "zx_rotation_rate": fit_result["zx_rotation_rate"],
            "n1": raw_result["n1"]["fig"],
            "n3": raw_result["n3"]["fig"],
            "fig": raw_result["fig"],
        }

        self.save_calibration(backend)
        return RunResult(raw_result=result)
