"""Type definitions for the task execution layer.

This module defines the protocols, models, and exceptions used across
the task execution components (executor, backend_saver, mux_distributor,
result_pipeline).

Centralising these definitions avoids circular imports between modules
that need to reference TaskProtocol or TaskExecutionResult.
"""

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from qdash.datamodel.task import CalibDataModel, OutputParameterModel
from qdash.workflow.calibtasks.results import PostProcessResult, PreProcessResult, RunResult


@runtime_checkable
class TaskProtocol(Protocol):
    """Protocol for task objects."""

    name: str
    r2_threshold: float
    backend: str
    input_parameters: dict[str, Any]
    input_parameters_from_snapshot: bool
    run_parameters: dict[str, Any]

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

    def prepare_run(self, backend: Any, qid: str) -> None:
        """Apply resolved inputs immediately before task execution."""
        ...

    def run(self, backend: Any, qid: str) -> RunResult | None:
        """Run the task."""
        ...

    def batch_run(self, backend: Any, qids: list[str]) -> RunResult | None:
        """Run the task for a batch of qubits."""
        ...

    def extract_raw_data(self, run_result: RunResult) -> list[Any]:
        """Extract serializable artifacts before postprocessing."""
        ...

    def extract_batch_raw_data(
        self, backend: Any, run_result: RunResult, qids: list[str]
    ) -> dict[str, list[Any]]:
        """Extract serializable artifacts grouped by qid from a batch result."""
        ...

    def postprocess(
        self, backend: Any, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        """Run postprocessing."""
        ...

    def attach_task_id(self, task_id: str) -> dict[str, OutputParameterModel]:
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
    stack_trace: str = ""
    output_parameters: dict[str, Any] = Field(default_factory=dict)
    r2: dict[str, float | None] | None = None
    calib_data_delta: CalibDataModel = Field(
        default_factory=lambda: CalibDataModel(qubit={}, coupling={})
    )

    model_config = {"arbitrary_types_allowed": True}
