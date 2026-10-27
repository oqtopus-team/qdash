from typing import ClassVar

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
from qdash.workflow.engine.backend.qubex import QubexBackend
from qdash.workflow.engine.backend.qubex_paths import (
    resolve_session_system_id,
    session_experiment_paths,
)


class ConfigureAll(QubexTask):
    """Task to configure all boxes for the selected MUXes."""

    name: str = "ConfigureAll"
    task_type: str = "system"
    input_spec: ClassVar[dict[str, InputParameterSpec]] = {}
    run_spec: ClassVar[dict[str, RunParameterSpec]] = {
        "mux_ids": RunParameterSpec(
            unit="a.u.",
            value_type="list",
            default=[],
            description="List of MUX IDs to configure",
        ),
    }
    output_spec: ClassVar[dict[str, OutputParameterSpec]] = {}

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

        system_id = resolve_session_system_id({**backend.config, "muxes": mux_ids, "qids": []})
        paths = session_experiment_paths(backend.config, system_id)

        print(f"[ConfigureAll] Loading system_manager for system={system_id} mux_ids={mux_ids}")
        exp = Experiment(
            system_id=system_id,
            muxes=mux_ids,
            config_dir=paths["config_dir"],
            params_dir=paths["params_dir"],
        )
        exp.system_manager.load(
            chip_id=exp.chip_id,
            config_dir=exp.config_path,
            params_dir=exp.params_path,
        )
        print(f"[ConfigureAll] Pushing system_manager (box_ids={exp.box_ids})")
        exp.system_manager.push(box_ids=exp.box_ids, confirm=False, parallel=False)
        print("[ConfigureAll] Done")
        return RunResult(raw_result={"mux_ids": mux_ids, "box_ids": exp.box_ids})
