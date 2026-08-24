"""Schema definitions for task file router."""

from pydantic import BaseModel, Field


class TaskFileBackend(BaseModel):
    """Task file backend model."""

    name: str
    path: str


class ListTaskFileBackendsResponse(BaseModel):
    """Response model for listing task file backends."""

    backends: list[TaskFileBackend]


class TaskFileSettings(BaseModel):
    """Task file settings model."""

    default_backend: str | None = None
    default_view_mode: str | None = None  # "tasks" or "files"
    sort_order: str | None = None  # "category", "type_then_name", "name_only", "file_path"


class TaskInfo(BaseModel):
    """Task information extracted from Python file."""

    name: str
    class_name: str
    task_type: str | None = None
    description: str | None = None
    file_path: str
    category: str | None = None  # From backend.yaml categories
    enabled: bool = True  # Whether task is in enabled_tasks list
    input_parameters: dict[str, dict[str, object]] = Field(default_factory=dict)
    run_parameters: dict[str, dict[str, object]] = Field(default_factory=dict)


class ListTaskInfoResponse(BaseModel):
    """Response model for listing task info."""

    tasks: list[TaskInfo]


class BackendDefinitionResponse(BaseModel):
    """Backend definition from configuration."""

    description: str = ""
    tasks: list[str] = []


class BackendConfigResponse(BaseModel):
    """Response model for backend configuration."""

    default_backend: str = "qubex"
    backends: dict[str, BackendDefinitionResponse] = {}
    categories: dict[str, list[str]] = {}
