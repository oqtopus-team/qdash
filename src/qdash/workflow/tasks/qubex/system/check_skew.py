from pathlib import Path
from typing import Any, ClassVar

import yaml
from qdash.datamodel.task import InputParameterModel, OutputParameterModel
from qdash.workflow.core.session.qubex import QubexSession
from qdash.workflow.tasks.base import (
    BaseTask,
    PostProcessResult,
    PreProcessResult,
    RunResult,
)
from qubecalib.instrument.quel.quel1.tool.skew import Skew, SkewSetting


class CheckSkew(BaseTask):
    """Task to check skew the boxies."""

    name: str = "CheckSkew"
    backend: str = "qubex"
    task_type: str = "system"
    input_parameters: ClassVar[dict[str, InputParameterModel]] = {
        "muxes": InputParameterModel(
            unit="a.u.",
            value_type="list",
            value=[0, 1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15],
            description="List of muxes to check skew",
        ),
    }
    output_parameters: ClassVar[dict[str, OutputParameterModel]] = {}

    def preprocess(self, session: QubexSession, qid: str) -> PreProcessResult:
        return PreProcessResult(input_parameters=self.input_parameters)

    def postprocess(self, execution_id: str, run_result: RunResult, qid: str) -> PostProcessResult:
        result = run_result.raw_result
        figures: list = [result.get("fig")]
        return PostProcessResult(
            output_parameters=self.attach_execution_id(execution_id), figures=figures
        )

    def load(self, filename: str) -> Any:
        with (Path.cwd() / Path(filename)).open() as file:
            return yaml.safe_load(file)

    def run(self, session: QubexSession, qid: str) -> RunResult:  # noqa: ARG002
        skew_config = self.load("/app/config/qubex/64Q/config/skew.yaml")
        for k, v in skew_config["box_setting"].items():
            print(f"Box {k} setting: {v}")
        from qubex import Experiment

        exp = Experiment(
            chip_id="64Q",
            muxes=self.input_parameters["muxes"].get_value(),
            config_dir="/app/config/qubex/64Q/config",
            params_dir="/app/config/qubex/64Q/params",
        )
        qc = exp.tool.get_qubecalib()
        qc.sysdb.load_box_yaml("/app/config/box.yaml")
        setting = SkewSetting.from_yaml("/app/config/qubex/64Q/config/skew.yaml")
        boxes = [*list(exp.boxes), setting.monitor_box_name]
        system = qc.sysdb.create_quel1system(*boxes)
        system.initialize()
        system.resync(*boxes)
        skew = Skew.create(setting=setting, system=system, sysdb=qc.sysdb)
        skew.measure()
        skew.estimate()
        for v, k in skew._estimated.items():
            print(f"Estimated skew for {v[0]}: {k.idx:.3f} ns")
        fig = skew.plot()
        result = {
            "fig": fig,
        }
        return RunResult(raw_result=result)

    def batch_run(self, session: QubexSession, qid: str) -> RunResult:
        """Batch run is not implemented."""
        raise NotImplementedError(
            f"Batch run is not implemented for {self.name} task. Use run method instead."
        )
