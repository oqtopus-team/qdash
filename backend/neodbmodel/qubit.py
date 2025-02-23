from bunnet import Document
from datamodel.qubit import NodeInfoModel
from datamodel.system_info import SystemInfoModel
from neodbmodel.chip import ChipDocument
from pydantic import ConfigDict, Field


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
        indexes = [("qid", "chip_id")]

    @classmethod
    def find_by_qid(cls, qid: str, chip_id: str) -> "QubitDocument":
        """Find a QubitDocument by qid."""
        return cls.find_one({"qid": qid, "chip_id": chip_id}).run()

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
        doc = cls.find_by_qid(qid, chip_id)
        # Merge new calibration data into the existing data
        doc.data = QubitDocument.merge_calib_data(doc.data, output_parameters)
        doc.system_info.update_time()
        updated_qubit = doc.save()
        chip_doc = ChipDocument.find_one({"chip_id": chip_id}).run()
        if chip_doc:
            chip_doc.update_qubit(qid, updated_qubit.model_dump())

        return updated_qubit

    @classmethod
    def update_status(cls, status: str, qid: str, chip_id: str) -> "QubitDocument":
        """Update the QubitDocument's status."""
        doc = cls.find_by_qid(qid, chip_id)
        doc.status = status
        doc.system_info.update_time()
        return doc.save()
