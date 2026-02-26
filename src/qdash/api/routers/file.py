"""File router for QDash API."""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from qdash.api.dependencies import get_file_service  # noqa: TCH002
from qdash.api.lib.auth import get_current_active_user  # noqa: TCH002
from qdash.api.schemas.auth import User  # noqa: TCH002
from qdash.api.schemas.file import (
    FileTreeNode,
    GitPushRequest,
    SaveFileRequest,
    ValidateFileRequest,
)
from qdash.api.services.file_service import FileService  # noqa: TCH002

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/files/raw-data",
    summary="Download file",
    operation_id="downloadFile",
    response_class=FileResponse,
)
def download_file(
    path: str,
    service: Annotated[FileService, Depends(get_file_service)],
) -> FileResponse:
    """Download a raw data file from the server.

    Parameters
    ----------
    path : str
        Absolute file path to the file to download

    Returns
    -------
    FileResponse
        The file as a downloadable response

    """
    return service.download_file(path)


@router.get(
    "/files/zip",
    summary="Download file or directory as zip",
    operation_id="downloadZipFile",
    response_class=FileResponse,
)
def download_zip_file(
    path: str,
    service: Annotated[FileService, Depends(get_file_service)],
) -> FileResponse:
    """Download a file or directory as a ZIP archive.

    Parameters
    ----------
    path : str
        Absolute path to the file or directory to archive

    Returns
    -------
    FileResponse
        ZIP archive as a downloadable response

    """
    return service.download_zip_file(path)


@router.get(
    "/files/tree",
    summary="Get file tree for entire config directory",
    operation_id="getFileTree",
    response_model=list[FileTreeNode],
)
def get_file_tree(
    service: Annotated[FileService, Depends(get_file_service)],
) -> list[FileTreeNode]:
    """Get file tree structure for entire config directory.

    Returns
    -------
        File tree structure

    """
    return service.get_file_tree()


@router.get(
    "/files/content",
    summary="Get file content for editing",
    operation_id="getFileContent",
)
def get_file_content(
    path: str,
    service: Annotated[FileService, Depends(get_file_service)],
) -> dict[str, Any]:
    """Get file content for editing.

    Args:
    ----
        path: Relative path from CONFIG_BASE_PATH

    Returns:
    -------
        File content and metadata

    """
    return service.get_file_content(path)


@router.put(
    "/files/content",
    summary="Save file content",
    operation_id="saveFileContent",
)
def save_file_content(
    request: SaveFileRequest,
    _current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[FileService, Depends(get_file_service)],
) -> dict[str, str]:
    """Save file content.

    Args:
    ----
        request: Save file request with path and content

    Returns:
    -------
        Success message

    """
    return service.save_file_content(request.path, request.content)


@router.post(
    "/files/validate",
    summary="Validate file content (YAML/JSON)",
    operation_id="validateFileContent",
)
def validate_file_content(
    request: ValidateFileRequest,
    service: Annotated[FileService, Depends(get_file_service)],
) -> dict[str, Any]:
    """Validate YAML or JSON content.

    Args:
    ----
        request: Validation request with content and file_type

    Returns:
    -------
        Validation result

    """
    return service.validate_file_content(request.content, request.file_type)


@router.get(
    "/files/git/status",
    summary="Get Git status of config directory",
    operation_id="getGitStatus",
)
def get_git_status(
    service: Annotated[FileService, Depends(get_file_service)],
) -> dict[str, Any]:
    """Get Git status of config directory.

    Returns
    -------
        Git status information

    """
    return service.get_git_status()


@router.post(
    "/files/git/pull",
    summary="Pull latest config from Git repository",
    operation_id="gitPullConfig",
)
def git_pull_config(
    _current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[FileService, Depends(get_file_service)],
) -> dict[str, Any]:
    """Pull latest config from Git repository.

    Returns
    -------
        Pull operation result

    """
    return service.git_pull_config()


@router.post(
    "/files/git/push",
    summary="Push config changes to Git repository",
    operation_id="gitPushConfig",
)
def git_push_config(
    request: GitPushRequest,
    _current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[FileService, Depends(get_file_service)],
) -> dict[str, Any]:
    """Push config changes to Git repository.

    Args:
    ----
        request: Push request with commit message

    Returns:
    -------
        Push operation result

    """
    return service.git_push_config(request.commit_message)
