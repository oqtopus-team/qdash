from typing import Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="FidelityCondition")


@_attrs_define
class FidelityCondition:
    """Condition for fidelity filtering.

    Attributes:
        min_ (float):
        max_ (float):
        is_within_24h (Union[Unset, bool]):  Default: True.
    """

    min_: float
    max_: float
    is_within_24h: Union[Unset, bool] = True
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        min_ = self.min_

        max_ = self.max_

        is_within_24h = self.is_within_24h

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "min": min_,
                "max": max_,
            }
        )
        if is_within_24h is not UNSET:
            field_dict["is_within_24h"] = is_within_24h

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: dict[str, Any]) -> T:
        d = src_dict.copy()
        min_ = d.pop("min")

        max_ = d.pop("max")

        is_within_24h = d.pop("is_within_24h", UNSET)

        fidelity_condition = cls(
            min_=min_,
            max_=max_,
            is_within_24h=is_within_24h,
        )

        fidelity_condition.additional_properties = d
        return fidelity_condition

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
