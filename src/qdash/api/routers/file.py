from __future__ import annotations

import logging
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException
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


@router.get(
    "/file/zip",
    summary="download file or directory as zip",
    operation_id="downloadZipFile",
    response_class=FileResponse,
)
def download_zip_file(path: str) -> FileResponse:
    """Download a file or directory as zip."""
    import shutil
    import tempfile

    source_path = Path(path)
    if not source_path.exists():
        raise HTTPException(status_code=404, detail=f"Path not found: {path}")

    # Create a temporary directory that will persist until explicitly removed
    temp_dir = tempfile.mkdtemp()
    temp_dir_path = Path(temp_dir)
    timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    zip_filename = f"{source_path.name}_{timestamp}.zip"

    try:
        if source_path.is_dir():
            # If it's a directory, zip its contents
            # make_archive returns the path to the created zip file
            actual_zip_path = Path(shutil.make_archive(str(temp_dir_path / source_path.name), "zip", source_path))
        else:
            # If it's a file, create a zip containing just that file
            actual_zip_path = temp_dir_path / zip_filename
            with zipfile.ZipFile(actual_zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.write(source_path, source_path.name)

        if not actual_zip_path.is_file():
            raise Exception(f"Failed to create zip file at {actual_zip_path}")

        logger.info(f"Created zip file: {actual_zip_path}")

        # Create a FileResponse with a cleanup callback
        def cleanup_temp_dir() -> None:
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
                logger.info(f"Cleaned up temp directory: {temp_dir}")
            except Exception as e:
                logger.error(f"Error cleaning up temp directory: {e}")

        background_tasks = BackgroundTasks()
        background_tasks.add_task(cleanup_temp_dir)
        return FileResponse(
            path=str(actual_zip_path),
            filename=zip_filename,
            media_type="application/zip",
            background=background_tasks,
        )

    except Exception as e:
        # Clean up temp directory in case of error
        shutil.rmtree(temp_dir, ignore_errors=True)
        logger.error(f"Error creating zip file: {e}")
        raise HTTPException(status_code=500, detail=f"Error creating zip file: {e!s}")
