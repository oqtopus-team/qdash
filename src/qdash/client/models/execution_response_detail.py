from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.execution_response_detail_note import ExecutionResponseDetailNote
    from ..models.task import Task


T = TypeVar("T", bound="ExecutionResponseDetail")


@_attrs_define
class ExecutionResponseDetail:
    """ExecutionResponseDetailV2 is a Pydantic model that represents the detail of an execution response.

    Attributes
    ----------
        name (str): The name of the execution.
        status (str): The current status of the execution.
        start_at (str): The start time

        Attributes:
            name (str):
            status (str):
            start_at (str):
            end_at (str):
            elapsed_time (str):
            task (list['Task']):
            note (ExecutionResponseDetailNote):
    """

    name: str
    status: str
    start_at: str
    end_at: str
    elapsed_time: str
    task: list["Task"]
    note: "ExecutionResponseDetailNote"
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        name = self.name

        status = self.status

        start_at = self.start_at

        end_at = self.end_at

        elapsed_time = self.elapsed_time

        task = []
        for task_item_data in self.task:
            task_item = task_item_data.to_dict()
            task.append(task_item)

        note = self.note.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "name": name,
                "status": status,
                "start_at": start_at,
                "end_at": end_at,
                "elapsed_time": elapsed_time,
                "task": task,
                "note": note,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: dict[str, Any]) -> T:
        from ..models.execution_response_detail_note import ExecutionResponseDetailNote
        from ..models.task import Task

        d = src_dict.copy()
        name = d.pop("name")

        status = d.pop("status")

        start_at = d.pop("start_at")

        end_at = d.pop("end_at")

        elapsed_time = d.pop("elapsed_time")

        task = []
        _task = d.pop("task")
        for task_item_data in _task:
            task_item = Task.from_dict(task_item_data)

            task.append(task_item)

        note = ExecutionResponseDetailNote.from_dict(d.pop("note"))

        execution_response_detail = cls(
            name=name,
            status=status,
            start_at=start_at,
            end_at=end_at,
            elapsed_time=elapsed_time,
            task=task,
            note=note,
        )

        execution_response_detail.additional_properties = d
        return execution_response_detail

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
