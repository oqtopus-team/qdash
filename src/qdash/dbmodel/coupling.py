from typing import Any, ClassVar

from bunnet import Document
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, IndexModel
from qdash.datamodel.coupling import CouplingModel, EdgeInfoModel
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.coupling_history import CouplingHistoryDocument


class CouplingDocument(Document):
    """Coupling document.

    Attributes
    ----------
        project_id (str): The owning project identifier (required).
        qid (str): The coupling ID. e.g. "0-1".
        chip_id (str): The chip ID. e.g. "chip1".
        data (dict): The data of the coupling. e.g. {"coupling_strength": 0.1}.
        calibrated_at (str): The time when the coupling was calibrated. e.g. "2021-01-01T00:00:00Z".
        edge_info (EdgeInfoModel): The edge information. e.g. {"fill": "red", "position": {"x": 0.0, "y": 0.0}}.
        system_info (SystemInfo): The system information. e.g. {"created_at": "2021-01-01T00:00:00Z", "updated_at": "2021-01-01T00:00:00Z"}.

    """

    project_id: str = Field(..., description="Owning project identifier")
    username: str = Field(..., description="The username of the user who created the coupling")
    qid: str = Field(..., description="The coupling ID")
    status: str = Field("pending", description="The status of the coupling")
    chip_id: str = Field(..., description="The chip ID")
    data: dict[str, Any] = Field(..., description="The data of the coupling")
    best_data: dict[str, Any] = Field(
        default_factory=dict,
        description="The best calibration results, focusing on fidelity metrics",
    )
    edge_info: EdgeInfoModel | None = Field(
        default=None, description="The edge information (deprecated)"
    )

    system_info: SystemInfoModel = Field(..., description="The system information")

    model_config = ConfigDict(
        from_attributes=True,
    )

    class Settings:
        """Settings for the document."""

        name = "coupling"
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
                existing[key] = CouplingDocument.merge_calib_data(existing[key], value)
            else:
                existing[key] = value
        return existing

    @staticmethod
    def update_best_data(current_best: dict[str, Any], new_data: dict[str, Any]) -> dict[str, Any]:
        """Update best_data with new calibration results if they are better.

        Only updates fidelity-related metrics when the new values are higher
        (better fidelity = higher value).
        """
        fidelity_metrics = [
            "zx90_gate_fidelity",
            "bell_state_fidelity",
        ]

        for metric in fidelity_metrics:
            if metric in new_data:
                new_param = new_data[metric]
                new_value = new_param.value if hasattr(new_param, "value") else 0.0
                # Initialize if metric doesn't exist in best_data or new value is better
                current_value = (
                    current_best[metric].get("value", 0.0) if metric in current_best else 0.0
                )
                if metric not in current_best or new_value > current_value:
                    # Convert OutputParameterModel to dict for storage
                    current_best[metric] = {
                        "value": new_param.value,
                        "value_type": new_param.value_type,
                        "error": new_param.error,
                        "unit": new_param.unit,
                        "description": new_param.description,
                        "calibrated_at": new_param.calibrated_at,
                        "execution_id": new_param.execution_id,
                        "task_id": new_param.task_id,
                    }

        return current_best

    @classmethod
    def update_calib_data(
        cls,
        username: str,
        qid: str,
        chip_id: str,
        output_parameters: dict[str, Any],
        project_id: str,
    ) -> "CouplingDocument":
        """Update the CouplingDocument's calibration data with new values."""
        coupling_doc = cls.find_one({"username": username, "qid": qid, "chip_id": chip_id}).run()
        if coupling_doc is None:
            raise ValueError(f"Coupling {qid} not found in chip {chip_id}")
        coupling_doc.data = CouplingDocument.merge_calib_data(coupling_doc.data, output_parameters)
        # Update best_data if new results are better
        coupling_doc.best_data = CouplingDocument.update_best_data(
            coupling_doc.best_data, output_parameters
        )
        coupling_doc.system_info.update_time()
        coupling_doc.save()
        chip_doc = ChipDocument.find_one({"username": username, "chip_id": chip_id}).run()
        if chip_doc is None:
            raise ValueError(f"Chip {chip_id} not found")
        coupling_model = CouplingModel(
            project_id=project_id,
            qid=qid,
            chip_id=chip_id,
            data=coupling_doc.data,
            best_data=coupling_doc.best_data,
            edge_info=coupling_doc.edge_info,
            username=username,
        )
        chip_doc.update_coupling(qid, coupling_model)
        # Update the coupling in the history document
        CouplingHistoryDocument.create_history(coupling_model)
        return coupling_doc

    @classmethod
    def update_status(cls, qid: str, chip_id: str, status: str) -> "CouplingDocument":
        """Update the CouplingDocument's status."""
        coupling_doc = cls.find_one({"qid": qid, "chip_id": chip_id}).run()
        if coupling_doc is None:
            raise ValueError(f"Coupling {qid} not found in chip {chip_id}")
        coupling_doc.status = status
        coupling_doc.save()
        return coupling_doc
