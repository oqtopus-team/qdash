"""Type definitions for the task execution layer.

This module defines the protocols, models, and exceptions used across
the task execution components (executor, backend_saver, mux_distributor,
result_pipeline).

Centralising these definitions avoids circular imports between modules
that need to reference TaskProtocol or TaskExecutionResult.
"""

from typing import Any, ClassVar, Protocol, runtime_checkable

from pydantic import BaseModel, Field
from qdash.datamodel.task import CalibDataModel, ParameterModel
from qdash.workflow.calibtasks.results import PostProcessResult, PreProcessResult, RunResult


@runtime_checkable
class TaskProtocol(Protocol):
    """Protocol for task objects."""

    name: str
    r2_threshold: float
    backend: str
    run_parameters: ClassVar[dict[str, Any]]

    def get_name(self) -> str:
        """Get task name."""
        ...

    def get_task_type(self) -> str:
        """Get task type."""
        ...

    def is_qubit_task(self) -> bool:
        """Check if qubit task."""
        ...

    def is_coupling_task(self) -> bool:
        """Check if coupling task."""
        ...

    def preprocess(self, backend: Any, qid: str) -> PreProcessResult | None:
        """Run preprocessing."""
        ...

    def run(self, backend: Any, qid: str) -> RunResult | None:
        """Run the task."""
        ...

    def postprocess(
        self, backend: Any, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        """Run postprocessing."""
        ...

    def attach_task_id(self, task_id: str) -> dict[str, ParameterModel]:
        """Attach task ID to output parameters."""
        ...


@runtime_checkable
class BackendProtocol(Protocol):
    """Protocol for backend objects."""

    name: str

    def update_note(
        self,
        username: str,
        chip_id: str,
        calib_dir: str,
        execution_id: str,
        task_manager_id: str,
        project_id: str | None = None,
        qid: str | None = None,
    ) -> None:
        """Update calibration note."""
        ...


class TaskExecutionError(Exception):
    """Exception raised when task execution fails."""


class TaskExecutionResult(BaseModel):
    """Result of task execution.

    This class encapsulates the complete result of a task execution,
    including output parameters, calibration data changes, and metadata.
    """

    task_name: str
    task_type: str
    qid: str
    success: bool = False
    message: str = ""
    output_parameters: dict[str, Any] = Field(default_factory=dict)
    r2: dict[str, float | None] | None = None
    calib_data_delta: CalibDataModel = Field(
        default_factory=lambda: CalibDataModel(qubit={}, coupling={})
    )

    model_config = {"arbitrary_types_allowed": True}
