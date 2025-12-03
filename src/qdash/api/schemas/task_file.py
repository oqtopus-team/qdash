"""Schema definitions for task file router."""

from enum import Enum

from pydantic import BaseModel


class FileNodeType(str, Enum):
    """File node type enum."""

    FILE = "file"
    DIRECTORY = "directory"


class TaskFileTreeNode(BaseModel):
    """Task file tree node model."""

    name: str
    path: str
    type: FileNodeType
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


class TaskInfo(BaseModel):
    """Task information extracted from Python file."""

    name: str
    class_name: str
    task_type: str | None = None
    description: str | None = None
    file_path: str


class ListTaskInfoResponse(BaseModel):
    """Response model for listing task info."""

    tasks: list[TaskInfo]
