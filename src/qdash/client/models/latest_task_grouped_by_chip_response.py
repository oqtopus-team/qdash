from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.latest_task_grouped_by_chip_response_result import LatestTaskGroupedByChipResponseResult


T = TypeVar("T", bound="LatestTaskGroupedByChipResponse")


@_attrs_define
class LatestTaskGroupedByChipResponse:
    """ChipTaskResponse is a Pydantic model that represents the response for fetching the tasks of a chip.

    Attributes:
        task_name (str):
        result (LatestTaskGroupedByChipResponseResult):
    """

    task_name: str
    result: "LatestTaskGroupedByChipResponseResult"
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        task_name = self.task_name

        result = self.result.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "task_name": task_name,
                "result": result,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: dict[str, Any]) -> T:
        from ..models.latest_task_grouped_by_chip_response_result import LatestTaskGroupedByChipResponseResult

        d = src_dict.copy()
        task_name = d.pop("task_name")

        result = LatestTaskGroupedByChipResponseResult.from_dict(d.pop("result"))

        latest_task_grouped_by_chip_response = cls(
            task_name=task_name,
            result=result,
        )

        latest_task_grouped_by_chip_response.additional_properties = d
        return latest_task_grouped_by_chip_response

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
