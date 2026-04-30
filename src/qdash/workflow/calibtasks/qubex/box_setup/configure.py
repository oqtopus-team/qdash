from typing import ClassVar

from qdash.datamodel.task import ParameterModel, RunParameterModel
from qdash.workflow.calibtasks.base import (
    PostProcessResult,
    RunResult,
)
from qdash.workflow.calibtasks.qubex.base import QubexTask
from qdash.workflow.engine.backend.qubex import QubexBackend


class Configure(QubexTask):
    """Task to configure the box."""

    name: str = "Configure"
    task_type: str = "qubit"
    input_parameters: ClassVar[dict[str, ParameterModel | None]] = {}
    run_parameters: ClassVar[dict[str, RunParameterModel]] = {}
    output_parameters: ClassVar[dict[str, ParameterModel]] = {}

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        return PostProcessResult(output_parameters={})

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        exp = self.get_experiment(backend)
        label = self.get_qubit_label(backend, qid)
        print(f"[Configure] Loading system_manager for {label} (qid={qid})")
        resonator_label = exp.get_resonator_label(int(qid))
        port = exp.targets[resonator_label].channel.port
        labels = [
            t.label
            for t in exp.experiment_system.read_out_targets
            if port.id == t.channel.port.id and t.label != resonator_label
        ]

        print(labels)
        exp.system_manager.load(
            chip_id=exp.chip_id,
            config_dir=exp.config_path,
            params_dir=exp.params_path,
            targets_to_exclude=labels,
        )
        print(f"[Configure] Pushing system_manager for {label} (box_ids={exp.box_ids})")
        exp.system_manager.push(box_ids=exp.box_ids, confirm=False)
        print(f"[Configure] Done for {label}")
        self.save_calibration(backend)
        return RunResult(raw_result=None)
