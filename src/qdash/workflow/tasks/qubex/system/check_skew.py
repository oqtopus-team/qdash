from pathlib import Path
from typing import Any, ClassVar

import yaml
from qdash.datamodel.task import InputParameterModel, OutputParameterModel
from qdash.workflow.engine.session.qubex import QubexSession
from qdash.workflow.tasks.base import (
    PostProcessResult,
    RunResult,
)
from qdash.workflow.tasks.qubex.base import QubexTask
from qubecalib.instrument.quel.quel1.tool.skew import Skew, SkewSetting


class CheckSkew(QubexTask):
    """Task to check skew the boxies."""

    name: str = "CheckSkew"
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

    def postprocess(
        self, session: QubexSession, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        result = run_result.raw_result
        figures: list = [result["fig"]]
        return PostProcessResult(output_parameters=self.attach_execution_id(execution_id), figures=figures)

    def load(self, filename: str) -> Any:
        with (Path.cwd() / Path(filename)).open() as file:
            return yaml.safe_load(file)

    def run(self, session: QubexSession, qid: str) -> RunResult:  # noqa: ARG002
        chip_id = session.config.get("chip_id", "64Qv1")
        skew_config = self.load(f"/app/config/qubex/{chip_id}/config/skew.yaml")
        for k, v in skew_config["box_setting"].items():
            print(f"Box {k} setting: {v}")
        from qubex import Experiment

        exp = Experiment(
            chip_id=chip_id,
            muxes=self.input_parameters["muxes"].get_value(),
            config_dir=f"/app/config/qubex/{chip_id}/config",
            params_dir=f"/app/config/qubex/{chip_id}/params",
        )
        qc = exp.tool.get_qubecalib()
        qc.sysdb.load_box_yaml(f"/app/config/qubex/{chip_id}/config/box.yaml")
        setting = SkewSetting.from_yaml(f"/app/config/qubex/{chip_id}/config/skew.yaml")
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
