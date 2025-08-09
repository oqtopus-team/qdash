from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.execution_response_summary_note import ExecutionResponseSummaryNote


T = TypeVar("T", bound="ExecutionResponseSummary")


@_attrs_define
class ExecutionResponseSummary:
    """ExecutionResponseSummaryV2 is a Pydantic model that represents the summary of an execution response.

    Attributes
    ----------
        name (str): The name of the execution.
        status (str): The current status of the execution.
        start_at (str): The start time of the execution.
        end_at (str): The end time of the execution.
        elapsed_time (str): The total elapsed time of the execution.

        Attributes:
            name (str):
            execution_id (str):
            status (str):
            start_at (str):
            end_at (str):
            elapsed_time (str):
            tags (list[str]):
            note (ExecutionResponseSummaryNote):
    """

    name: str
    execution_id: str
    status: str
    start_at: str
    end_at: str
    elapsed_time: str
    tags: list[str]
    note: "ExecutionResponseSummaryNote"
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        name = self.name

        execution_id = self.execution_id

        status = self.status

        start_at = self.start_at

        end_at = self.end_at

        elapsed_time = self.elapsed_time

        tags = self.tags

        note = self.note.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "name": name,
                "execution_id": execution_id,
                "status": status,
                "start_at": start_at,
                "end_at": end_at,
                "elapsed_time": elapsed_time,
                "tags": tags,
                "note": note,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.execution_response_summary_note import ExecutionResponseSummaryNote

        d = dict(src_dict)
        name = d.pop("name")

        execution_id = d.pop("execution_id")

        status = d.pop("status")

        start_at = d.pop("start_at")

        end_at = d.pop("end_at")

        elapsed_time = d.pop("elapsed_time")

        tags = cast(list[str], d.pop("tags"))

        note = ExecutionResponseSummaryNote.from_dict(d.pop("note"))

        execution_response_summary = cls(
            name=name,
            execution_id=execution_id,
            status=status,
            start_at=start_at,
            end_at=end_at,
            elapsed_time=elapsed_time,
            tags=tags,
            note=note,
        )

        execution_response_summary.additional_properties = d
        return execution_response_summary

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
