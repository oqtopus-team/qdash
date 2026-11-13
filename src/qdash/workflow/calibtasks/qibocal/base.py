"""Base class of tasks that run on the qibocal backend."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from qdash.repository.qubit import MongoQubitCalibrationRepository
from qdash.workflow.calibtasks.base import BaseTask, PreProcessResult, RunResult
from qdash.workflow.calibtasks.input_resolver import populate_parameters

if TYPE_CHECKING:
    from qdash.workflow.engine.backend.qibocal import QibocalBackend

EMULATOR_MEASUREMENT_ONLY_REASON = (
    "Synthetic result from the Qibolab emulator; emulator outputs never update "
    "accepted calibration state"
)


class QibocalTask(BaseTask):
    """Task that runs a Qibocal protocol through the isolated runner.

    Execution requires an immutable matching simulation binding. BackendSaver checks
    that binding again before database-only adoption.
    """

    backend: str = "qibocal"
    measurement_only_reason: ClassVar[str | None] = None
    # The runner enforces its own timeout from config/app/qibocal.yaml.
    timeout: int = 60 * 30

    def __init__(self, params: dict[str, Any] | None = None) -> None:
        super().__init__(params)
        # Set in postprocess and stored with every output in task-result history.
        self.output_provenance: dict[str, Any] = {}

    def batch_run(self, backend: QibocalBackend, qids: list[str]) -> RunResult:
        raise NotImplementedError(f"{self.name} runs one qubit at a time")

    def preprocess(self, backend: QibocalBackend, qid: str) -> PreProcessResult:
        binding = backend.binding()
        self.output_provenance = {
            "source": "qibolab-emulator",
            "synthetic": True,
            "simulation_binding": binding.model_dump(mode="json"),
            "chip_id": backend.config["chip_id"],
            "project_id": backend.config.get("project_id"),
            "phase": "input_resolution",
        }
        if self.input_parameters and not self.input_parameters_from_snapshot:
            data = MongoQubitCalibrationRepository().get_calibration_data(
                project_id=backend.config["project_id"],
                chip_id=backend.config["chip_id"],
                qid=qid,
            )
            populate_parameters(
                self.input_parameters, self.__class__.input_spec, {"": [data], "self": [data]}
            )
        return PreProcessResult(input_parameters=self.input_parameters)
