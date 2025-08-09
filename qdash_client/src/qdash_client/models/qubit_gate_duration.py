from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="QubitGateDuration")


@_attrs_define
class QubitGateDuration:
    """Gate duration of the qubit.

    Attributes:
        rz (int):
        sx (int):
        x (int):
    """

    rz: int
    sx: int
    x: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        rz = self.rz

        sx = self.sx

        x = self.x

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "rz": rz,
                "sx": sx,
                "x": x,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        rz = d.pop("rz")

        sx = d.pop("sx")

        x = d.pop("x")

        qubit_gate_duration = cls(
            rz=rz,
            sx=sx,
            x=x,
        )

        qubit_gate_duration.additional_properties = d
        return qubit_gate_duration

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
