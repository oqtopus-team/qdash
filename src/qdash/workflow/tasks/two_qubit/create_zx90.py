from typing import ClassVar

from qdash.datamodel.task import InputParameterModel, OutputParameterModel
from qdash.workflow.calibration.util import qid_to_cr_label, qid_to_cr_pair
from qdash.workflow.tasks.base import (
    BaseTask,
    PostProcessResult,
    PreProcessResult,
    RunResult,
)
from qubex.experiment import Experiment


class CreateZX90(BaseTask):
    """Task to create ZX90 gate."""

    name: str = "CreateZX90"
    task_type: str = "coupling"
    input_parameters: ClassVar[dict[str, InputParameterModel]] = {}
    output_parameters: ClassVar[dict[str, OutputParameterModel]] = {
        "cr_amplitude": OutputParameterModel(
            unit="a.u.", value_type="float", description="Amplitude of the CR pulse."
        ),
        "cr_phase": OutputParameterModel(
            unit="a.u.", value_type="float", description="Phase of the CR pulse."
        ),
        "cancel_amplitude": OutputParameterModel(
            unit="a.u.", value_type="float", description="Amplitude of the cancel pulse."
        ),
        "cancel_phase": OutputParameterModel(
            unit="a.u.", value_type="float", description="Phase of the cancel pulse."
        ),
    }

    def preprocess(self, exp: Experiment, qid: str) -> PreProcessResult:
        return PreProcessResult(input_parameters=self.input_parameters)

    def postprocess(self, execution_id: str, run_result: RunResult, qid: str) -> PostProcessResult:
        result = run_result.raw_result
        self.output_parameters["cr_amplitude"].value = result["cr_amplitude"]
        self.output_parameters["cr_phase"].value = result["cr_phase"]
        self.output_parameters["cancel_amplitude"].value = result["cancel_amplitude"]
        self.output_parameters["cancel_phase"].value = result["cancel_phase"]
        output_parameters = self.attach_execution_id(execution_id)
        figures: list = [result["n1"], result["n3"], result["fig"]]
        raw_data: list = []
        return PostProcessResult(
            output_parameters=output_parameters, figures=figures, raw_data=raw_data
        )

    def run(self, exp: Experiment, qid: str) -> RunResult:
        control, target = qid_to_cr_pair(qid)
        raw_result = exp.calibrate_zx90(control, target)
        fit_result = exp.calib_note.get_cr_param(qid_to_cr_label(qid))
        if fit_result is None:
            err_msg = f"CR parameters for {qid_to_cr_label(qid)} not found."
            raise ValueError(err_msg)
        result = {
            "cr_amplitude": fit_result["cr_amplitude"],
            "cr_phase": fit_result["cr_phase"],
            "cancel_amplitude": fit_result["cancel_amplitude"],
            "cancel_phase": fit_result["cancel_phase"],
            "n1": raw_result["n1"]["fig"],
            "n3": raw_result["n3"]["fig"],
            "fig": raw_result["fig"],
        }

        exp.calib_note.save()
        return RunResult(raw_result=result)

    def batch_run(self, exp: Experiment, qid: str) -> RunResult:
        """Batch run is not implemented."""
        raise NotImplementedError(
            f"Batch run is not implemented for {self.name} task. Use run method instead."
        )
