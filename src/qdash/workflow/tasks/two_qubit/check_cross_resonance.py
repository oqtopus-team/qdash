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


class CheckCrossResonance(BaseTask):
    """Task to check the cross resonance pulse."""

    name: str = "CheckCrossResonance"
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
        figures: list = []
        raw_data: list = []
        return PostProcessResult(
            output_parameters=output_parameters, figures=figures, raw_data=raw_data
        )

    def run(self, exp: Experiment, qid: str) -> RunResult:
        control, target = qid_to_cr_pair(qid)
        exp.obtain_cr_params(control, target)
        result = exp.calib_note.get_cr_param(qid_to_cr_label(qid))
        exp.calib_note.save()
        return RunResult(raw_result=result)
