from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.meas_error import MeasError
    from ..models.position import Position
    from ..models.qubit_gate_duration import QubitGateDuration
    from ..models.qubit_lifetime import QubitLifetime


T = TypeVar("T", bound="Qubit")


@_attrs_define
class Qubit:
    """Qubit information.

    Attributes:
        id (int):
        physical_id (int):
        position (Position): Position of the qubit on the device.
        fidelity (float):
        meas_error (MeasError): Measurement error of the qubit.
        qubit_lifetime (QubitLifetime): Qubit lifetime of the qubit.
        gate_duration (QubitGateDuration): Gate duration of the qubit.
    """

    id: int
    physical_id: int
    position: "Position"
    fidelity: float
    meas_error: "MeasError"
    qubit_lifetime: "QubitLifetime"
    gate_duration: "QubitGateDuration"
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        physical_id = self.physical_id

        position = self.position.to_dict()

        fidelity = self.fidelity

        meas_error = self.meas_error.to_dict()

        qubit_lifetime = self.qubit_lifetime.to_dict()

        gate_duration = self.gate_duration.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "physical_id": physical_id,
                "position": position,
                "fidelity": fidelity,
                "meas_error": meas_error,
                "qubit_lifetime": qubit_lifetime,
                "gate_duration": gate_duration,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: dict[str, Any]) -> T:
        from ..models.meas_error import MeasError
        from ..models.position import Position
        from ..models.qubit_gate_duration import QubitGateDuration
        from ..models.qubit_lifetime import QubitLifetime

        d = src_dict.copy()
        id = d.pop("id")

        physical_id = d.pop("physical_id")

        position = Position.from_dict(d.pop("position"))

        fidelity = d.pop("fidelity")

        meas_error = MeasError.from_dict(d.pop("meas_error"))

        qubit_lifetime = QubitLifetime.from_dict(d.pop("qubit_lifetime"))

        gate_duration = QubitGateDuration.from_dict(d.pop("gate_duration"))

        qubit = cls(
            id=id,
            physical_id=physical_id,
            position=position,
            fidelity=fidelity,
            meas_error=meas_error,
            qubit_lifetime=qubit_lifetime,
            gate_duration=gate_duration,
        )

        qubit.additional_properties = d
        return qubit

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
