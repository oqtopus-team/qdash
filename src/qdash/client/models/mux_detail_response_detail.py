from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.mux_detail_response_detail_additional_property import MuxDetailResponseDetailAdditionalProperty


T = TypeVar("T", bound="MuxDetailResponseDetail")


@_attrs_define
class MuxDetailResponseDetail:
    """ """

    additional_properties: dict[str, "MuxDetailResponseDetailAdditionalProperty"] = _attrs_field(
        init=False, factory=dict
    )

    def to_dict(self) -> dict[str, Any]:
        field_dict: dict[str, Any] = {}
        for prop_name, prop in self.additional_properties.items():
            field_dict[prop_name] = prop.to_dict()

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: dict[str, Any]) -> T:
        from ..models.mux_detail_response_detail_additional_property import MuxDetailResponseDetailAdditionalProperty

        d = src_dict.copy()
        mux_detail_response_detail = cls()

        additional_properties = {}
        for prop_name, prop_dict in d.items():
            additional_property = MuxDetailResponseDetailAdditionalProperty.from_dict(prop_dict)

            additional_properties[prop_name] = additional_property

        mux_detail_response_detail.additional_properties = additional_properties
        return mux_detail_response_detail

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> "MuxDetailResponseDetailAdditionalProperty":
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: "MuxDetailResponseDetailAdditionalProperty") -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
