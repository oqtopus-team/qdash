from collections.abc import Mapping
from typing import Any, TypeVar, TYPE_CHECKING

from attrs import define as _attrs_define
from attrs import field as _attrs_field



if TYPE_CHECKING:
    from ..models.execute_calib_request import ExecuteCalibRequest


T = TypeVar("T", bound="ScheduleCalibResponse")


@_attrs_define
class ScheduleCalibResponse:
    """ScheduleCalibResponse is a subclass of BaseModel.

    Attributes:
        menu_name (str):
        menu (ExecuteCalibRequest): ExecuteCalibRequest is a subclass of MenuModel.
        description (str):
        note (str):
        timezone (str):
        scheduled_time (str):
        flow_run_id (str):
    """

    menu_name: str
    menu: "ExecuteCalibRequest"
    description: str
    note: str
    timezone: str
    scheduled_time: str
    flow_run_id: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:

        menu_name = self.menu_name

        menu = self.menu.to_dict()

        description = self.description

        note = self.note

        timezone = self.timezone

        scheduled_time = self.scheduled_time

        flow_run_id = self.flow_run_id

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "menu_name": menu_name,
                "menu": menu,
                "description": description,
                "note": note,
                "timezone": timezone,
                "scheduled_time": scheduled_time,
                "flow_run_id": flow_run_id,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.execute_calib_request import ExecuteCalibRequest

        d = dict(src_dict)
        menu_name = d.pop("menu_name")

        menu = ExecuteCalibRequest.from_dict(d.pop("menu"))

        description = d.pop("description")

        note = d.pop("note")

        timezone = d.pop("timezone")

        scheduled_time = d.pop("scheduled_time")

        flow_run_id = d.pop("flow_run_id")

        schedule_calib_response = cls(
            menu_name=menu_name,
            menu=menu,
            description=description,
            note=note,
            timezone=timezone,
            scheduled_time=scheduled_time,
            flow_run_id=flow_run_id,
        )

        schedule_calib_response.additional_properties = d
        return schedule_calib_response

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
