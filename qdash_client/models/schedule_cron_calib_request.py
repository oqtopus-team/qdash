from collections.abc import Mapping
from typing import Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="ScheduleCronCalibRequest")


@_attrs_define
class ScheduleCronCalibRequest:
    """ScheduleCronCalibRequest is a subclass of BaseModel.

    Attributes:
        scheduler_name (str):
        menu_name (str):
        cron (str):
        active (Union[Unset, bool]):  Default: True.
    """

    scheduler_name: str
    menu_name: str
    cron: str
    active: Union[Unset, bool] = True
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        scheduler_name = self.scheduler_name

        menu_name = self.menu_name

        cron = self.cron

        active = self.active

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "scheduler_name": scheduler_name,
                "menu_name": menu_name,
                "cron": cron,
            }
        )
        if active is not UNSET:
            field_dict["active"] = active

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        scheduler_name = d.pop("scheduler_name")

        menu_name = d.pop("menu_name")

        cron = d.pop("cron")

        active = d.pop("active", UNSET)

        schedule_cron_calib_request = cls(
            scheduler_name=scheduler_name,
            menu_name=menu_name,
            cron=cron,
            active=active,
        )

        schedule_cron_calib_request.additional_properties = d
        return schedule_cron_calib_request

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
