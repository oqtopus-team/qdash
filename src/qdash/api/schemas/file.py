"""Schema definitions for file router."""

from pydantic import BaseModel


class FileTreeNode(BaseModel):
    """File tree node model."""

    name: str
    path: str
    type: str  # "file" or "directory"
    children: list["FileTreeNode"] | None = None


class SaveFileRequest(BaseModel):
    """Request model for saving file content."""

    path: str  # Relative path from CONFIG_BASE_PATH (e.g., "64Qv2/config/chip.yaml")
    content: str


class ValidateFileRequest(BaseModel):
    """Request model for validating file content."""

    content: str
    file_type: str  # "yaml" or "json"


class GitPushRequest(BaseModel):
    """Request model for Git push operation."""

    commit_message: str = "Update config files from UI"
