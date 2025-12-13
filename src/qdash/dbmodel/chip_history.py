import logging
from typing import ClassVar

import pendulum
from bunnet import Document
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, DESCENDING, IndexModel
from pymongo.errors import DuplicateKeyError
from qdash.datamodel.coupling import CouplingModel
from qdash.datamodel.qubit import QubitModel
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.chip import ChipDocument

logger = logging.getLogger(__name__)


class ChipHistoryDocument(Document):
    """Data model for chip history.

    Attributes
    ----------
        project_id (str): The owning project identifier.
        chip_id (str): The chip ID. e.g. "chip1".
        size (int): The size of the chip.
        qubits (dict): The qubits of the chip.
        couplings (dict): The couplings of the chip.
        installed_at (str): The time when the system information was created.
        system_info (SystemInfo): The system information.
        recorded_date (str): The date when this history record was created (YYYYMMDD).

    """

    project_id: str = Field(..., description="Owning project identifier")
    chip_id: str = Field(..., description="The chip ID")
    username: str = Field(..., description="The username of the user who created the chip")
    size: int = Field(..., description="The size of the chip")
    topology_id: str | None = Field(None, description="Topology template ID")
    qubits: dict[str, QubitModel] = Field({}, description="The qubits of the chip")
    couplings: dict[str, CouplingModel] = Field({}, description="The couplings of the chip")
    installed_at: str = Field(..., description="The time when the system information was created")
    system_info: SystemInfoModel = Field(..., description="The system information")
    recorded_date: str = Field(
        default_factory=lambda: pendulum.now(tz="Asia/Tokyo").format("YYYYMMDD"),
        description="The date when this history record was created",
    )

    model_config = ConfigDict(
        from_attributes=True,
    )

    class Settings:
        """Settings for the document."""

        name = "chip_history"
        indexes: ClassVar = [
            IndexModel(
                [
                    ("project_id", ASCENDING),
                    ("chip_id", ASCENDING),
                    ("username", ASCENDING),
                    ("recorded_date", ASCENDING),
                ],
                unique=True,
            ),
            IndexModel(
                [("project_id", ASCENDING), ("chip_id", ASCENDING), ("recorded_date", DESCENDING)]
            ),
        ]

    @classmethod
    def get_yesterday_history(
        cls, chip_id: str, username: str, project_id: str
    ) -> "ChipHistoryDocument | None":
        """Get yesterday's history record for a chip.

        Parameters
        ----------
        chip_id : str
            The chip ID
        username : str
            The username of the user who created the chip
        project_id : str | None
            The project identifier

        Returns
        -------
        ChipHistoryDocument | None
            Yesterday's history record if it exists, None otherwise

        """
        yesterday = pendulum.now(tz="Asia/Tokyo").subtract(days=1).format("YYYYMMDD")
        return cls.find_one(
            {
                "project_id": project_id,
                "chip_id": chip_id,
                "username": username,
                "recorded_date": yesterday,
            }
        ).run()

    @classmethod
    def create_history(cls, chip_doc: ChipDocument) -> "ChipHistoryDocument":
        """Create a history record from a ChipDocument using atomic upsert.

        This method performs an atomic upsert operation to handle concurrent writes.
        If a record already exists for today, it updates the existing record.
        Otherwise, it creates a new record.

        Args:
            chip_doc: The ChipDocument to create history from

        Returns:
            ChipHistoryDocument: The created or updated history record

        Raises:
            Exception: If database operation fails
        """
        today = pendulum.now(tz="Asia/Tokyo").format("YYYYMMDD")

        try:
            # Try to insert a new document
            history_doc = cls(
                project_id=chip_doc.project_id,
                chip_id=chip_doc.chip_id,
                username=chip_doc.username,
                size=chip_doc.size,
                topology_id=chip_doc.topology_id,
                qubits=chip_doc.qubits,
                couplings=chip_doc.couplings,
                installed_at=chip_doc.installed_at,
                system_info=chip_doc.system_info,
                recorded_date=today,
            )
            return history_doc.insert()

        except DuplicateKeyError:
            # If duplicate key error occurs, find and update the existing document
            logger.info(
                f"History record already exists for chip {chip_doc.chip_id}, updating existing record"
            )
            existing_doc = cls.find_one(
                {
                    "project_id": chip_doc.project_id,
                    "chip_id": chip_doc.chip_id,
                    "username": chip_doc.username,
                    "recorded_date": today,
                }
            ).run()

            if existing_doc:
                # Update the existing document
                existing_doc.size = chip_doc.size
                existing_doc.topology_id = chip_doc.topology_id
                existing_doc.qubits = chip_doc.qubits
                existing_doc.couplings = chip_doc.couplings
                existing_doc.installed_at = chip_doc.installed_at
                existing_doc.system_info = chip_doc.system_info
                return existing_doc.save()
            else:
                # This shouldn't happen, but handle it gracefully
                raise RuntimeError("Document not found after DuplicateKeyError")

        except Exception as e:
            logger.error(f"Failed to create/update chip history: {e}")
            raise
