from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field



T = TypeVar("T", bound="QubitLifetime")


@_attrs_define
class QubitLifetime:
    """Qubit lifetime of the qubit.

    Attributes:
        t1 (float):
        t2 (float):
    """

    t1: float
    t2: float
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        t1 = self.t1

        t2 = self.t2

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "t1": t1,
                "t2": t2,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        t1 = d.pop("t1")

        t2 = d.pop("t2")

        qubit_lifetime = cls(
            t1=t1,
            t2=t2,
        )

        qubit_lifetime.additional_properties = d
        return qubit_lifetime

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
