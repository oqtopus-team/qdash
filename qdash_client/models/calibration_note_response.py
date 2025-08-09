from collections.abc import Mapping
from typing import Any, TypeVar, TYPE_CHECKING

from attrs import define as _attrs_define
from attrs import field as _attrs_field



if TYPE_CHECKING:
    from ..models.calibration_note_response_note import CalibrationNoteResponseNote


T = TypeVar("T", bound="CalibrationNoteResponse")


@_attrs_define
class CalibrationNoteResponse:
    """CalibrationNote is a subclass of BaseModel.

    Attributes:
        username (str):
        execution_id (str):
        task_id (str):
        note (CalibrationNoteResponseNote):
        timestamp (str):
    """

    username: str
    execution_id: str
    task_id: str
    note: "CalibrationNoteResponseNote"
    timestamp: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:

        username = self.username

        execution_id = self.execution_id

        task_id = self.task_id

        note = self.note.to_dict()

        timestamp = self.timestamp

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "username": username,
                "execution_id": execution_id,
                "task_id": task_id,
                "note": note,
                "timestamp": timestamp,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.calibration_note_response_note import CalibrationNoteResponseNote

        d = dict(src_dict)
        username = d.pop("username")

        execution_id = d.pop("execution_id")

        task_id = d.pop("task_id")

        note = CalibrationNoteResponseNote.from_dict(d.pop("note"))

        timestamp = d.pop("timestamp")

        calibration_note_response = cls(
            username=username,
            execution_id=execution_id,
            task_id=task_id,
            note=note,
            timestamp=timestamp,
        )

        calibration_note_response.additional_properties = d
        return calibration_note_response

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
