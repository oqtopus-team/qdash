from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.coupling_gate_duration import CouplingGateDuration


T = TypeVar("T", bound="Coupling")


@_attrs_define
class Coupling:
    """Coupling information.

    Attributes:
        control (int):
        target (int):
        fidelity (float):
        gate_duration (CouplingGateDuration): Gate duration of the coupling.
    """

    control: int
    target: int
    fidelity: float
    gate_duration: "CouplingGateDuration"
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:

        control = self.control

        target = self.target

        fidelity = self.fidelity

        gate_duration = self.gate_duration.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "control": control,
                "target": target,
                "fidelity": fidelity,
                "gate_duration": gate_duration,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.coupling_gate_duration import CouplingGateDuration

        d = dict(src_dict)
        control = d.pop("control")

        target = d.pop("target")

        fidelity = d.pop("fidelity")

        gate_duration = CouplingGateDuration.from_dict(d.pop("gate_duration"))

        coupling = cls(
            control=control,
            target=target,
            fidelity=fidelity,
            gate_duration=gate_duration,
        )

        coupling.additional_properties = d
        return coupling

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
