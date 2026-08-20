from typing import Any, ClassVar

from qubex.experiment.experiment_constants import CALIBRATION_SHOTS
from qubex.measurement.measurement_defaults import DEFAULT_INTERVAL

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
from qdash.workflow.calibtasks.qubex.validation import finite_value_error, first_validation_error
from qdash.workflow.engine.backend.qubex import QubexBackend


class CreateZX90(QubexTask):
    """Task to create ZX90 gate."""

    name: str = "CreateZX90"
    task_type: str = "coupling"
    timeout: int = 60 * 25  # 25 minutes
    run_spec: ClassVar[dict[str, RunParameterSpec]] = {
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

    # Input parameters from control and target qubits
    input_spec: ClassVar[dict[str, InputParameterSpec]] = {
        # Control qubit parameters
        "control_qubit_frequency": InputParameterSpec.database_or_default(
            default=0,
            parameter_name="qubit_frequency",
            qid_role="control",
            unit="GHz",
        ),
        "control_drag_hpi_amplitude": InputParameterSpec.required_database(
            parameter_name="drag_hpi_amplitude",
            qid_role="control",
            unit="a.u.",
        ),
        "control_drag_hpi_length": InputParameterSpec.required_database(
            parameter_name="drag_hpi_length",
            qid_role="control",
            unit="ns",
        ),
        "control_drag_hpi_beta": InputParameterSpec.required_database(
            parameter_name="drag_hpi_beta",
            qid_role="control",
            unit="a.u.",
        ),
        "control_readout_frequency": InputParameterSpec.database_or_default(
            default=0,
            parameter_name="readout_frequency",
            qid_role="control",
            unit="GHz",
        ),
        "control_readout_amplitude": InputParameterSpec.database_or_default(
            default=0,
            parameter_name="readout_amplitude",
            qid_role="control",
            unit="a.u.",
        ),
        "control_readout_length": InputParameterSpec.database_or_default(
            default=0,
            parameter_name="readout_length",
            qid_role="control",
            unit="ns",
        ),
        # Target qubit parameters
        "target_qubit_frequency": InputParameterSpec.database_or_default(
            default=0,
            parameter_name="qubit_frequency",
            qid_role="target",
            unit="GHz",
        ),
        "target_readout_frequency": InputParameterSpec.database_or_default(
            default=0,
            parameter_name="readout_frequency",
            qid_role="target",
            unit="GHz",
        ),
        "target_readout_amplitude": InputParameterSpec.database_or_default(
            default=0,
            parameter_name="readout_amplitude",
            qid_role="target",
            unit="a.u.",
        ),
        "target_readout_length": InputParameterSpec.database_or_default(
            default=0,
            parameter_name="readout_length",
            qid_role="target",
            unit="ns",
        ),
        # CR parameters (from CheckCrossResonance)
        "cr_amplitude": InputParameterSpec.required_database(
            parameter_name="cr_amplitude",
            qid_role="control",
            unit="a.u.",
        ),
        "cr_phase": InputParameterSpec.required_database(
            parameter_name="cr_phase",
            qid_role="control",
            unit="a.u.",
        ),
        "cancel_amplitude": InputParameterSpec.required_database(
            parameter_name="cancel_amplitude",
            qid_role="target",
            unit="a.u.",
        ),
        "cancel_phase": InputParameterSpec.required_database(
            parameter_name="cancel_phase",
            qid_role="target",
            unit="a.u.",
        ),
        "cancel_beta": InputParameterSpec.required_database(
            parameter_name="cancel_beta",
            qid_role="target",
            unit="a.u.",
        ),
        "rotary_amplitude": InputParameterSpec.required_database(
            parameter_name="rotary_amplitude",
            qid_role="control",
            unit="a.u.",
        ),
        "zx_rotation_rate": InputParameterSpec.required_database(
            parameter_name="zx_rotation_rate",
            qid_role="coupling",
            unit="a.u.",
        ),
        "cr_ramptime": InputParameterSpec.required_database(
            parameter_name="cr_ramptime",
            qid_role="coupling",
            unit="ns",
        ),
    }

    # Output parameters with qid_role specifying where each is stored
    output_spec: ClassVar[dict[str, OutputParameterSpec]] = {
        "cr_amplitude": OutputParameterSpec(
            qid_role="control", unit="a.u.", description="Amplitude of the CR pulse."
        ),
        "cr_phase": OutputParameterSpec(
            qid_role="control", unit="a.u.", description="Phase of the CR pulse."
        ),
        "cancel_amplitude": OutputParameterSpec(
            qid_role="target", unit="a.u.", description="Amplitude of the cancel pulse."
        ),
        "cancel_phase": OutputParameterSpec(
            qid_role="target", unit="a.u.", description="Phase of the cancel pulse."
        ),
        "cancel_beta": OutputParameterSpec(
            qid_role="target", unit="a.u.", description="Beta of the cancel pulse."
        ),
        "rotary_amplitude": OutputParameterSpec(
            qid_role="control", unit="a.u.", description="Amplitude of the rotary pulse."
        ),
        "zx_rotation_rate": OutputParameterSpec(
            qid_role="coupling", unit="a.u.", description="ZX rotation rate."
        ),
        "zx90_gate_time": OutputParameterSpec(
            qid_role="coupling", unit="ns", description="Duration of the ZX90 pulse."
        ),
        "cr_ramptime": OutputParameterSpec(
            qid_role="coupling", unit="ns", description="CR pulse ramp time."
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
        self.output_parameters["zx90_gate_time"].value = result["zx90_gate_time"]
        self.output_parameters["cr_ramptime"].value = result["cr_ramptime"]
        output_parameters = self.attach_execution_id(execution_id)
        figures: list[Any] = [result["n1"], result["n3"], result["fig"]]
        raw_data: list[Any] = []
        validation_error = first_validation_error(
            finite_value_error(
                self.output_parameters["cr_amplitude"].value, f"CreateZX90 cr_amplitude for {qid}"
            ),
            finite_value_error(
                self.output_parameters["cr_phase"].value, f"CreateZX90 cr_phase for {qid}"
            ),
            finite_value_error(
                self.output_parameters["cancel_amplitude"].value,
                f"CreateZX90 cancel_amplitude for {qid}",
            ),
            finite_value_error(
                self.output_parameters["cancel_phase"].value, f"CreateZX90 cancel_phase for {qid}"
            ),
            finite_value_error(
                self.output_parameters["cancel_beta"].value, f"CreateZX90 cancel_beta for {qid}"
            ),
            finite_value_error(
                self.output_parameters["rotary_amplitude"].value,
                f"CreateZX90 rotary_amplitude for {qid}",
            ),
            finite_value_error(
                self.output_parameters["zx_rotation_rate"].value,
                f"CreateZX90 zx_rotation_rate for {qid}",
            ),
            finite_value_error(
                self.output_parameters["zx90_gate_time"].value,
                f"CreateZX90 zx90_gate_time for {qid}",
                minimum=0.0,
            ),
            finite_value_error(
                self.output_parameters["cr_ramptime"].value,
                f"CreateZX90 cr_ramptime for {qid}",
            ),
        )
        return PostProcessResult(
            output_parameters=output_parameters,
            figures=figures,
            raw_data=raw_data,
            validation_error=validation_error,
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
            n_shots=self.run_parameters["shots"].get_value(),
            shot_interval=self.run_parameters["interval"].get_value(),
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
            "cr_ramptime": fit_result["ramptime"],
            "n1": raw_result["n1"]["fig"],
            "n3": raw_result["n3"]["fig"],
            "fig": raw_result["fig"],
        }

        zx90 = exp.zx90(control_qubit=control, target_qubit=target)
        result["zx90_gate_time"] = zx90.duration

        self.save_calibration(backend)
        return RunResult(raw_result=result)
