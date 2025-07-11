from typing import Any

from bunnet import Document
from pydantic import ConfigDict, Field
from qdash.datamodel.menu import ScheduleNode
from qdash.datamodel.system_info import SystemInfoModel


class MenuDocument(Document):
    """Data model for a qubit.

    Attributes
    ----------
        qid (str): The qubit ID. e.g. "0".
        chip_id (str): The chip ID. e.g. "chip1".
        data (dict): The data of the qubit. e.g. {"qubit_frequency": 5.0}.
        calibrated_at (str): The time when the qubit was calibrated. e.g. "2021-01-01T00:00:00Z".
        system_info (SystemInfo): The system information. e.g. {"created_at": "2021-01-01T00:00:00Z", "updated_at": "2021-01-01T00:00:00Z"}.

    """

    name: str
    username: str
    backend: str | None = Field(default="", description="The backend used for the menu.")
    description: str
    chip_id: str | None = Field(default=None)
    schedule: ScheduleNode = Field(
        description="The schedule of the menu. It can be a serial, parallel or batch node.",
    )
    notify_bool: bool = False
    tasks: list[str] | None = Field(default=None, exclude=True)
    tags: list[str] | None = Field(default=None)
    task_details: dict[str, Any] | None = Field(default=None)
    system_info: SystemInfoModel = Field(
        default_factory=SystemInfoModel, description="The system information"
    )

    model_config = ConfigDict(
        from_attributes=True,
    )

    class Settings:
        """Settings for the document."""

        name = "menu"


# TODO(orangekame3): Impelement input parameters for the task.
