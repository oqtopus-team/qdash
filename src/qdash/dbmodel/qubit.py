from typing import Any, ClassVar

from bunnet import Document
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, IndexModel
from qdash.datamodel.qubit import QubitModel
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.qubit_history import QubitHistoryDocument


class QubitDocument(Document):
    """Data model for a qubit.

    Attributes
    ----------
        project_id (str): The owning project identifier (required).
        qid (str): The qubit ID. e.g. "0".
        chip_id (str): The chip ID. e.g. "chip1".
        data (dict): The data of the qubit. e.g. {"qubit_frequency": 5.0}.
        calibrated_at (str): The time when the qubit was calibrated. e.g. "2021-01-01T00:00:00Z".
        system_info (SystemInfo): The system information. e.g. {"created_at": "2021-01-01T00:00:00Z", "updated_at": "2021-01-01T00:00:00Z"}.

    """

    project_id: str = Field(..., description="Owning project identifier")
    username: str = Field(..., description="The username of the user who created the qubit")
    qid: str = Field(..., description="The qubit ID")
    status: str = Field("pending", description="The status of the qubit")
    chip_id: str = Field(..., description="The chip ID")
    data: dict[str, Any] = Field(..., description="The data of the qubit")
    system_info: SystemInfoModel = Field(..., description="The system information")

    model_config = ConfigDict(
        from_attributes=True,
    )

    class Settings:
        """Settings for the document."""

        name = "qubit"
        indexes: ClassVar = [
            IndexModel(
                [
                    ("project_id", ASCENDING),
                    ("chip_id", ASCENDING),
                    ("qid", ASCENDING),
                    ("username", ASCENDING),
                ],
                unique=True,
            ),
            IndexModel([("project_id", ASCENDING), ("chip_id", ASCENDING)]),
        ]

    @staticmethod
    def merge_calib_data(existing: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
        """Merge calibration data recursively."""
        for key, value in new.items():
            if key in existing and isinstance(existing[key], dict) and isinstance(value, dict):
                existing[key] = QubitDocument.merge_calib_data(existing[key], value)
            else:
                existing[key] = value
        return existing

    @classmethod
    def update_calib_data(
        cls,
        username: str,
        qid: str,
        chip_id: str,
        output_parameters: dict[str, Any],
        project_id: str,
    ) -> "QubitDocument":
        """Update the QubitDocument's calibration data with new values."""
        qubit_doc = cls.find_one({"username": username, "qid": qid, "chip_id": chip_id}).run()
        if qubit_doc is None:
            raise ValueError(f"Qubit {qid} not found in chip {chip_id}")
        # Merge new calibration data into the existing data
        qubit_doc.data = QubitDocument.merge_calib_data(qubit_doc.data, output_parameters)
        qubit_doc.system_info.update_time()
        qubit_doc.save()
        # Create history entry for the updated qubit
        qubit_model = QubitModel(
            project_id=project_id,
            qid=qid,
            chip_id=chip_id,
            data=qubit_doc.data,
            username=username,
        )
        QubitHistoryDocument.create_history(qubit_model)
        return qubit_doc

    @classmethod
    def update_status(cls, qid: str, chip_id: str, status: str) -> "QubitDocument":
        """Update the QubitDocument's status."""
        doc = cls.find_one({"qid": qid, "chip_id": chip_id}).run()
        if doc is None:
            raise ValueError(f"Qubit {qid} not found in chip {chip_id}")
        doc.status = status
        doc.system_info.update_time()
        doc.save()
        return doc
