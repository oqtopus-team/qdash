"""Cryostat (dilution refrigerator) document.

A cryostat is a long-lived piece of lab hardware. Each cool-down cycle of a
cryostat is a separate ``CooldownDocument`` that references this entity.
"""

from datetime import datetime
from typing import ClassVar

from bunnet import Document
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, IndexModel
from qdash.datamodel.note import NoteModel
from qdash.datamodel.system_info import SystemInfoModel


class CryostatDocument(Document):
    """One physical cryostat / dilution refrigerator."""

    project_id: str = Field(..., description="Owning project identifier")
    cryo_id: str = Field(..., description="Cryostat identifier (project-unique, e.g. 'K-101')")
    name: str = Field(default="", description="Human-readable display name")
    manufacturer: str = Field(default="", description="e.g. 'Oxford Instruments'")
    model: str = Field(default="", description="e.g. 'Triton 200'")
    location: str = Field(default="", description="Physical location, e.g. 'Lab B-204'")
    status: str = Field(
        default="active",
        description="active | maintenance | decommissioned",
    )
    commissioned_at: datetime | None = Field(default=None, description="When put into service")
    decommissioned_at: datetime | None = Field(default=None, description="When retired")
    note: NoteModel = Field(default_factory=NoteModel, description="Free-form note")
    system_info: SystemInfoModel = Field(
        default_factory=SystemInfoModel, description="Created/updated timestamps"
    )

    class Settings:
        """Settings for the document."""

        name = "cryostat"
        indexes: ClassVar = [
            IndexModel(
                [("project_id", ASCENDING), ("cryo_id", ASCENDING)],
                unique=True,
                name="project_cryo_unique",
            ),
        ]

    model_config = ConfigDict(from_attributes=True)
