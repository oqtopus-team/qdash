from typing import ClassVar, get_args

from qubex.typing import ConfigurationMode

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


class Configure(QubexTask):
    """Task to configure the box."""

    name: str = "Configure"
    task_type: str = "qubit"
    input_spec: ClassVar[dict[str, InputParameterSpec]] = {}
    run_spec: ClassVar[dict[str, RunParameterSpec]] = {
        "configuration_mode": RunParameterSpec(
            value_type="str",
            default="ge-cr-cr",
            description="Control layout: ge-cr-cr, ge-ef-cr, or ge-ef-fh.",
        ),
    }
    output_spec: ClassVar[dict[str, OutputParameterSpec]] = {}

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        return PostProcessResult(output_parameters={})

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        exp = self.get_experiment(backend)

        # Older execution snapshots may not contain the newly added parameter.
        parameter = self.run_parameters.get("configuration_mode")
        mode = (
            parameter.value
            if parameter is not None
            else self.run_spec["configuration_mode"].default
        )
        if not isinstance(mode, str) or mode not in get_args(ConfigurationMode):
            raise ValueError(f"Unsupported configuration_mode: {mode!r}")

        label = self.get_qubit_label(backend, qid)
        print(f"[{self.name}] Loading system_manager for {label} (qid={qid}, mode={mode})")
        resonator_label = exp.get_resonator_label(int(qid))
        port = exp.targets[resonator_label].channel.port
        labels = [
            t.label
            for t in exp.experiment_system.read_out_targets
            if port.id == t.channel.port.id and t.label != resonator_label
        ]

        load_kwargs: dict[str, object] = {
            "chip_id": exp.chip_id,
            "config_dir": exp.config_path,
            "params_dir": exp.params_path,
            "targets_to_exclude": labels,
            "configuration_mode": mode,
        }
        exp.system_manager.load(**load_kwargs)
        print(f"[{self.name}] Pushing system_manager for {label} (box_ids={exp.box_ids})")
        exp.system_manager.push(box_ids=exp.box_ids, confirm=False, parallel=False)
        print(f"[{self.name}] Done for {label}")
        self.save_calibration(backend)
        return RunResult(raw_result=None)


class ConfigureEF(Configure):
    """Configure GE and EF drive channels before EF calibration in the same session."""

    name: str = "ConfigureEF"
    task_type: str = "qubit"
    run_spec: ClassVar[dict[str, RunParameterSpec]] = {
        "configuration_mode": RunParameterSpec(
            value_type="str",
            default="ge-ef-cr",
            description="EF control layout: ge-ef-cr or ge-ef-fh.",
        ),
    }

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        mode = self.run_parameters["configuration_mode"].value
        if mode not in ("ge-ef-cr", "ge-ef-fh"):
            raise ValueError("ConfigureEF requires configuration_mode ge-ef-cr or ge-ef-fh")
        return super().run(backend, qid)
