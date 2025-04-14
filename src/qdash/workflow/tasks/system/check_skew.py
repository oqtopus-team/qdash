from typing import ClassVar

from qdash.datamodel.task import InputParameterModel, OutputParameterModel
from qdash.workflow.tasks.base import (
    BaseTask,
    PostProcessResult,
    PreProcessResult,
    RunResult,
)
from qubecalib.instrument.quel.quel1.tool.skew import Skew, SkewSetting
from qubex.experiment import Experiment


class CheckSkew(BaseTask):
    """Task to check skew the boxies."""

    name: str = "CheckSkew"
    task_type: str = "system"
    input_parameters: ClassVar[dict[str, InputParameterModel]] = {
        "muxes": InputParameterModel(
            unit="a.u.",
            value_type="list",
            value=[0, 1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14],
            description="List of muxes to check skew",
        ),
    }
    output_parameters: ClassVar[dict[str, OutputParameterModel]] = {}

    def preprocess(self, exp: Experiment, qid: str) -> PreProcessResult:
        return PreProcessResult(input_parameters=self.input_parameters)

    def postprocess(self, execution_id: str, run_result: RunResult, qid: str) -> PostProcessResult:
        result = run_result.raw_result
        figures: list = [result.get("fig")]
        return PostProcessResult(
            output_parameters=self.attach_execution_id(execution_id), figures=figures
        )

    def run(self, exp: Experiment, qid: str) -> RunResult:  # noqa: ARG002
        qc = exp.tool.get_qubecalib()
        exp = Experiment(
            chip_id="64Q",
            muxes=self.input_parameters["muxes"].get_value(),
            config_dir="/app/config",
            params_dir="/app/config",
        )
        qc.sysdb.load_box_yaml("/app/config/box.yaml")
        setting = SkewSetting.from_yaml("/app/config/skew.yaml")
        boxes = [*list(exp.boxes), setting.monitor_box_name]
        system = qc.sysdb.create_quel1system(*boxes)
        system.resync(*boxes)
        skew = Skew.create(setting=setting, system=system, sysdb=qc.sysdb)

        skew.measure()
        skew.estimate()
        fig = skew.plot()
        result = {
            "fig": fig,
        }
        return RunResult(raw_result=result)

    def batch_run(self, exp: Experiment, qid: str) -> RunResult:
        """Batch run is not implemented."""
        raise NotImplementedError(
            f"Batch run is not implemented for {self.name} task. Use run method instead."
        )
