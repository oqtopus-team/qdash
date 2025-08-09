from collections.abc import Mapping
from typing import Any, TypeVar, TYPE_CHECKING

from attrs import define as _attrs_define
from attrs import field as _attrs_field



if TYPE_CHECKING:
    from ..models.qubit import Qubit
    from ..models.coupling import Coupling


T = TypeVar("T", bound="Device")


@_attrs_define
class Device:
    """Device information.

    Attributes:
        name (str):
        device_id (str):
        qubits (list['Qubit']):
        couplings (list['Coupling']):
        calibrated_at (str):
    """

    name: str
    device_id: str
    qubits: list["Qubit"]
    couplings: list["Coupling"]
    calibrated_at: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:

        name = self.name

        device_id = self.device_id

        qubits = []
        for qubits_item_data in self.qubits:
            qubits_item = qubits_item_data.to_dict()
            qubits.append(qubits_item)

        couplings = []
        for couplings_item_data in self.couplings:
            couplings_item = couplings_item_data.to_dict()
            couplings.append(couplings_item)

        calibrated_at = self.calibrated_at

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "name": name,
                "device_id": device_id,
                "qubits": qubits,
                "couplings": couplings,
                "calibrated_at": calibrated_at,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.qubit import Qubit
        from ..models.coupling import Coupling

        d = dict(src_dict)
        name = d.pop("name")

        device_id = d.pop("device_id")

        qubits = []
        _qubits = d.pop("qubits")
        for qubits_item_data in _qubits:
            qubits_item = Qubit.from_dict(qubits_item_data)

            qubits.append(qubits_item)

        couplings = []
        _couplings = d.pop("couplings")
        for couplings_item_data in _couplings:
            couplings_item = Coupling.from_dict(couplings_item_data)

            couplings.append(couplings_item)

        calibrated_at = d.pop("calibrated_at")

        device = cls(
            name=name,
            device_id=device_id,
            qubits=qubits,
            couplings=couplings,
            calibrated_at=calibrated_at,
        )

        device.additional_properties = d
        return device

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
