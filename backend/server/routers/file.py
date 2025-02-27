from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.logger import logger
from fastapi.responses import FileResponse

router = APIRouter()
gunicorn_logger = logging.getLogger("gunicorn.error")
logger.handlers = gunicorn_logger.handlers
if __name__ != "main":
    logger.setLevel(gunicorn_logger.level)
else:
    logger.setLevel(logging.DEBUG)


@router.get(
    "/file/raw_data",
    summary="download file",
    operation_id="downloadFile",
    response_class=FileResponse,
)
def download_file(path: str) -> FileResponse:
    """Download a file."""
    if not Path(path).exists():
        raise HTTPException(status_code=404, detail=f"File not found: {path}")

    return FileResponse(path=path)
