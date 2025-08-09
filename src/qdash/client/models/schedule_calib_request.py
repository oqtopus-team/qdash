from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="ScheduleCalibRequest")


@_attrs_define
class ScheduleCalibRequest:
    """ScheduleCalibRequest is a subclass of BaseModel.

    Attributes:
        menu_name (str):
        scheduled (str):
    """

    menu_name: str
    scheduled: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        menu_name = self.menu_name

        scheduled = self.scheduled

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "menu_name": menu_name,
                "scheduled": scheduled,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: dict[str, Any]) -> T:
        d = src_dict.copy()
        menu_name = d.pop("menu_name")

        scheduled = d.pop("scheduled")

        schedule_calib_request = cls(
            menu_name=menu_name,
            scheduled=scheduled,
        )

        schedule_calib_request.additional_properties = d
        return schedule_calib_request

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
