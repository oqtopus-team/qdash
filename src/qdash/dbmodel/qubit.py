from typing import ClassVar

from bunnet import Document
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, IndexModel
from qdash.datamodel.qubit import NodeInfoModel, QubitModel
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.chip import ChipDocument


class QubitDocument(Document):
    """Data model for a qubit.

    Attributes
    ----------
        qid (str): The qubit ID. e.g. "0".
        chip_id (str): The chip ID. e.g. "chip1".
        data (dict): The data of the qubit. e.g. {"qubit_frequency": 5.0}.
        calibrated_at (str): The time when the qubit was calibrated. e.g. "2021-01-01T00:00:00Z".
        system_info (SystemInfo): The system information. e.g. {"created_at": "2021-01-01T00:00:00Z", "updated_at": "2021-01-01T00:00:00Z"}.

    """

    username: str = Field(..., description="The username of the user who created the qubit")
    qid: str = Field(..., description="The qubit ID")
    status: str = Field("pending", description="The status of the qubit")
    chip_id: str = Field(..., description="The chip ID")
    data: dict = Field(..., description="The data of the qubit")
    node_info: NodeInfoModel = Field(..., description="The node information")

    system_info: SystemInfoModel = Field(..., description="The system information")

    model_config = ConfigDict(
        from_attributes=True,
    )

    class Settings:
        """Settings for the document."""

        name = "qubit"
        indexes: ClassVar = [
            IndexModel([("chip_id", ASCENDING), ("qid", ASCENDING), ("username")], unique=True)
        ]

    @staticmethod
    def merge_calib_data(existing: dict, new: dict) -> dict:
        """Merge calibration data recursively."""
        for key, value in new.items():
            if key in existing and isinstance(existing[key], dict) and isinstance(value, dict):
                existing[key] = QubitDocument.merge_calib_data(existing[key], value)
            else:
                existing[key] = value
        return existing

    @classmethod
    def update_calib_data(cls, qid: str, chip_id: str, output_parameters: dict) -> "QubitDocument":
        """Update the QubitDocument's calibration data with new values."""
        qubit_doc = cls.find_one({"qid": qid, "chip_id": chip_id}).run()
        if qubit_doc is None:
            raise ValueError(f"Qubit {qid} not found in chip {chip_id}")
        # Merge new calibration data into the existing data
        qubit_doc.data = QubitDocument.merge_calib_data(qubit_doc.data, output_parameters)
        qubit_doc.system_info.update_time()
        qubit_doc.save()
        # Update the qubit in the chip document
        chip_doc = ChipDocument.find_one({"chip_id": chip_id}).run()
        if chip_doc is None:
            raise ValueError(f"Chip {chip_id} not found")
        qubit_model = QubitModel(
            qid=qid, chip_id=chip_id, data=qubit_doc.data, node_info=qubit_doc.node_info
        )
        chip_doc.update_qubit(qid, qubit_model)
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
