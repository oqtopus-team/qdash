"""Seed missing emulator calibration values from the native template."""

from typing import Any, ClassVar

from qdash.common.qibocal_platform import PlatformTemplate, template_values
from qdash.datamodel.task import OutputParameterSpec
from qdash.repository.qubit import MongoQubitCalibrationRepository
from qdash.workflow.calibtasks.base import PostProcessResult, RunResult
from qdash.workflow.calibtasks.qibocal.base import QibocalTask
from qdash.workflow.engine.backend.qibocal import QibocalBackend, hash_tree


class QibocalBringUp(QibocalTask):
    name: str = "QibocalBringUp"
    task_type: str = "qubit"
    output_spec: ClassVar[dict[str, OutputParameterSpec]] = {
        "qibocal_qubit_frequency": OutputParameterSpec(
            unit="GHz", description="Initial native drive frequency"
        ),
        "qibocal_pi_duration": OutputParameterSpec(
            unit="ns", description="Initial native RX pulse duration"
        ),
        "qibocal_pi_amplitude": OutputParameterSpec(
            unit="a.u.", description="Initial native RX pulse amplitude"
        ),
    }

    def run(self, backend: QibocalBackend, qid: str) -> RunResult:
        binding = backend.binding()
        template = PlatformTemplate(backend.settings.platforms_dir, backend.settings.platform)
        current = MongoQubitCalibrationRepository().get_calibration_data(
            project_id=backend.config["project_id"],
            chip_id=backend.config["chip_id"],
            qid=qid,
        )
        values = template_values(template.parameters(), int(qid))
        self.output_provenance = {
            "source": "qibolab-emulator",
            "synthetic": True,
            "protocol": "template_seed",
            "simulation_binding": binding.model_dump(mode="json"),
            "platform_sha256": hash_tree(template.directory),
            "chip_id": backend.config["chip_id"],
            "project_id": backend.config["project_id"],
        }
        return RunResult(
            raw_result={name: value for name, value in values.items() if name not in current}
        )

    def postprocess(
        self, backend: QibocalBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        selected: dict[str, Any] = {}
        for name, value in run_result.raw_result.items():
            self.output_parameters[name].value = value
            self.output_parameters[name].execution_id = execution_id
            selected[name] = self.output_parameters[name]
        return PostProcessResult(output_parameters=selected)
