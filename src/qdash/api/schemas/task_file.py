"""Schema definitions for task file router."""

from pydantic import BaseModel


class TaskFileTreeNode(BaseModel):
    """Task file tree node model."""

    name: str
    path: str
    type: str  # "file" or "directory"
    children: list["TaskFileTreeNode"] | None = None


class SaveTaskFileRequest(BaseModel):
    """Request model for saving task file content."""

    path: str  # Relative path from CALTASKS_PATH (e.g., "qubex/one_qubit_coarse/check_rabi.py")
    content: str


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
