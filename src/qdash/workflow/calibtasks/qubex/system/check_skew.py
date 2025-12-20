from pathlib import Path
from typing import Any, ClassVar

import yaml
from qdash.datamodel.task import InputParameterModel, OutputParameterModel, TaskTypes
from qdash.workflow.calibtasks.base import (
    PostProcessResult,
    RunResult,
)
from qdash.workflow.calibtasks.qubex.base import QubexTask
from qdash.workflow.engine.backend.qubex import QubexBackend
from qdash.workflow.engine.backend.qubex_paths import get_qubex_paths
from qubecalib.instrument.quel.quel1.tool.skew import Skew


class CheckSkew(QubexTask):
    """Task to check skew the boxies."""

    name: str = "CheckSkew"
    task_type = TaskTypes.SYSTEM
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
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        result = run_result.raw_result
        figures: list[Any] = [result["fig"]]
        return PostProcessResult(
            output_parameters=self.attach_execution_id(execution_id), figures=figures
        )

    def load(self, filename: str) -> Any:
        with (Path.cwd() / Path(filename)).open() as file:
            return yaml.safe_load(file)

    def run(self, backend: QubexBackend, qid: str) -> RunResult:  # noqa: ARG002
        chip_id = backend.config.get("chip_id", None)
        qubex_paths = get_qubex_paths()
        skew_file_path = str(qubex_paths.skew_yaml(chip_id))
        box_file_path = str(qubex_paths.box_yaml(chip_id))
        skew_config = self.load(skew_file_path)
        for k, v in skew_config["box_setting"].items():
            print(f"Box {k} setting: {v}")
        from qubex import Experiment

        with open(skew_file_path) as file:
            config = yaml.safe_load(file)
            ref_port = config["reference_port"].split("-")[0]

        exp = Experiment(
            chip_id=chip_id,
            muxes=self.input_parameters["muxes"].get_value(),
            config_dir=str(qubex_paths.config_dir(chip_id)),
            params_dir=str(qubex_paths.params_dir(chip_id)),
        )
        clock_master_address = (
            exp.system_manager.experiment_system.control_system.clock_master_address
        )
        box_ids = exp.box_ids
        all_box_ids = list(set(list(box_ids) + [ref_port]))
        skew = Skew.from_yaml(
            str(skew_file_path),
            box_yaml=str(box_file_path),
            clockmaster_ip=clock_master_address,
            boxes=all_box_ids,
        )
        skew.system.resync()
        skew.measure()
        skew.estimate()
        for v, k in skew._estimated.items():
            print(f"Estimated skew for {v[0]}: {k.idx:.3f} ns")
        fig = skew.plot()
        result = {
            "fig": fig,
        }
        return RunResult(raw_result=result)
