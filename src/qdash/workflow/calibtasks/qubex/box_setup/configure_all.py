from typing import ClassVar

from qdash.datamodel.task import ParameterModel, RunParameterModel
from qdash.workflow.calibtasks.base import (
    PostProcessResult,
    RunResult,
)
from qdash.workflow.calibtasks.qubex.base import QubexTask
from qdash.workflow.engine.backend.qubex import QubexBackend
from qdash.workflow.engine.backend.qubex_paths import get_qubex_paths


class ConfigureAll(QubexTask):
    """Task to configure all boxes for the selected MUXes."""

    name: str = "ConfigureAll"
    task_type: str = "system"
    input_parameters: ClassVar[dict[str, ParameterModel | None]] = {}
    run_parameters: ClassVar[dict[str, RunParameterModel]] = {
        "mux_ids": RunParameterModel(
            unit="a.u.",
            value_type="list",
            value=[],
            description="List of MUX IDs to configure",
        ),
    }
    output_parameters: ClassVar[dict[str, ParameterModel]] = {}

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        return PostProcessResult(output_parameters={})

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        from qubex import Experiment

        chip_id = backend.config.get("chip_id")
        if chip_id is None:
            msg = "chip_id must be provided to run ConfigureAll"
            raise ValueError(msg)

        mux_ids = self.run_parameters["mux_ids"].get_value()
        if mux_ids is None:
            mux_ids = []
        mux_ids = list(mux_ids)

        qubex_paths = get_qubex_paths()
        config_dir = backend.config.get("config_dir", str(qubex_paths.config_dir(chip_id)))
        params_dir = backend.config.get("params_dir", str(qubex_paths.params_dir(chip_id)))

        print(f"[ConfigureAll] Loading system_manager for mux_ids={mux_ids}")
        exp = Experiment(
            chip_id=chip_id,
            muxes=mux_ids,
            config_dir=config_dir,
            params_dir=params_dir,
        )
        exp.system_manager.load(
            chip_id=exp.chip_id,
            config_dir=exp.config_path,
            params_dir=exp.params_path,
        )
        print(f"[ConfigureAll] Pushing system_manager (box_ids={exp.box_ids})")
        exp.system_manager.push(box_ids=exp.box_ids, confirm=False)
        print("[ConfigureAll] Done")
        return RunResult(raw_result={"mux_ids": mux_ids, "box_ids": exp.box_ids})
