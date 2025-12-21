"""Schema definitions for calibration router."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class CalibrationNoteResponse(BaseModel):
    """CalibrationNote is a subclass of BaseModel."""

    username: str
    execution_id: str
    task_id: str
    note: dict[str, Any]
    timestamp: datetime | None = None
