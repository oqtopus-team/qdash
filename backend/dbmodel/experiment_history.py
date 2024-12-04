from datetime import datetime
from enum import Enum
from typing import Optional

from bunnet import Document
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, IndexModel


class Status(str, Enum):
    SCHEDULED: str = "scheduled"
    RUNNING: str = "running"
    SUCCESS: str = "success"
    FAILED: str = "failed"
    UNKNOWN: str = "unknown"


class ExperimentHistoryModel(Document):
    experiment_name: str
    label: str
    timestamp: datetime = Field(default_factory=datetime.now)
    status: Optional[str] = Field("running")
    fig_path: Optional[str] = Field(None)
    input_parameter: dict
    output_parameter: dict
    execution_id: Optional[str] = Field(None)  # 20241116#0

    class Settings:
        name = "experiment_history"
        indexes = [
            IndexModel(
                [
                    ("label", ASCENDING),
                    ("timestamp", ASCENDING),
                    ("experiment_name", ASCENDING),
                ],
                unique=True,
            )
        ]

    model_config = ConfigDict(
        from_attributes=True,
    )
