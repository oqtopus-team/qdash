"""File routers: raw downloads plus the config and knowledge git workspaces.

The two workspaces expose the same operations under ``/config/files`` and
``/knowledge/files``; each is a :class:`FileService` over its own directory
and GitHub repository.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Annotated, Any

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from qdash.api.dependencies import get_file_service, get_knowledge_file_service
from qdash.api.lib.auth import get_current_active_user
from qdash.api.schemas.auth import User
from qdash.api.schemas.file import (
    FileTreeNode,
    GitPushRequest,
    SaveFileRequest,
    ValidateFileRequest,
)
from qdash.api.services.file_service import FileService

if TYPE_CHECKING:
    from collections.abc import Callable

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


def _workspace_router(
    *,
    prefix: str,
    label: str,
    operation_prefix: str,
    get_service: Callable[[], FileService],
) -> APIRouter:
    """Build the browse/edit/git routes of one workspace."""
    # Dependencies go in defaults, not ``Annotated`` aliases: annotations are
    # strings here and FastAPI cannot resolve a closure-local alias.
    workspace = APIRouter()
    service_dep = Depends(get_service)
    user_dep = Depends(get_current_active_user)
    title = label.capitalize()

    @workspace.get(
        f"{prefix}/tree",
        summary=f"Get file tree of the {label} directory",
        operation_id=f"get{operation_prefix}FileTree",
        response_model=list[FileTreeNode],
    )
    def get_file_tree(service: FileService = service_dep) -> list[FileTreeNode]:
        return service.get_file_tree()

    @workspace.get(
        f"{prefix}/content",
        summary=f"Get {label} file content for editing",
        operation_id=f"get{operation_prefix}FileContent",
    )
    def get_file_content(path: str, service: FileService = service_dep) -> dict[str, Any]:
        return service.get_file_content(path)

    @workspace.put(
        f"{prefix}/content",
        summary=f"Save {label} file content",
        operation_id=f"save{operation_prefix}FileContent",
    )
    def save_file_content(
        request: SaveFileRequest, _current_user: User = user_dep, service: FileService = service_dep
    ) -> dict[str, str]:
        return service.save_file_content(request.path, request.content)

    @workspace.post(
        f"{prefix}/validate",
        summary="Validate file content (YAML/JSON)",
        operation_id=f"validate{operation_prefix}FileContent",
    )
    def validate_file_content(
        request: ValidateFileRequest, service: FileService = service_dep
    ) -> dict[str, Any]:
        return service.validate_file_content(request.content, request.file_type)

    @workspace.get(
        f"{prefix}/git/status",
        summary=f"Get Git status of the {label} directory",
        operation_id=f"get{operation_prefix}GitStatus",
    )
    def get_git_status(service: FileService = service_dep) -> dict[str, Any]:
        return service.get_git_status()

    @workspace.post(
        f"{prefix}/git/pull",
        summary=f"Pull the latest {label} from its Git repository",
        operation_id=f"gitPull{title}",
    )
    def git_pull(
        _current_user: User = user_dep, service: FileService = service_dep
    ) -> dict[str, Any]:
        return service.git_pull_config()

    @workspace.post(
        f"{prefix}/git/push",
        summary=f"Open a pull request with the {label} changes",
        operation_id=f"gitPush{title}",
    )
    def git_push(
        request: GitPushRequest, _current_user: User = user_dep, service: FileService = service_dep
    ) -> dict[str, Any]:
        return service.git_push_config(request.commit_message)

    return workspace


# Qubex config: operation ids unchanged from when it was the only workspace.
router.include_router(
    _workspace_router(
        prefix="/config/files", label="config", operation_prefix="", get_service=get_file_service
    )
)

knowledge_router = _workspace_router(
    prefix="/knowledge/files",
    label="knowledge",
    operation_prefix="Knowledge",
    get_service=get_knowledge_file_service,
)
