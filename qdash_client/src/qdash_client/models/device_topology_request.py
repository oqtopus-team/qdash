from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.condition import Condition


T = TypeVar("T", bound="DeviceTopologyRequest")


@_attrs_define
class DeviceTopologyRequest:
    """Request model for device topology.

    Attributes:
        name (Union[Unset, str]):  Default: 'anemone'.
        device_id (Union[Unset, str]):  Default: 'anemone'.
        qubits (Union[Unset, list[str]]):
        exclude_couplings (Union[Unset, list[str]]):
        condition (Union[Unset, Condition]): Condition for filtering device topology.
    """

    name: Union[Unset, str] = "anemone"
    device_id: Union[Unset, str] = "anemone"
    qubits: Union[Unset, list[str]] = UNSET
    exclude_couplings: Union[Unset, list[str]] = UNSET
    condition: Union[Unset, "Condition"] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        name = self.name

        device_id = self.device_id

        qubits: Union[Unset, list[str]] = UNSET
        if not isinstance(self.qubits, Unset):
            qubits = self.qubits

        exclude_couplings: Union[Unset, list[str]] = UNSET
        if not isinstance(self.exclude_couplings, Unset):
            exclude_couplings = self.exclude_couplings

        condition: Union[Unset, dict[str, Any]] = UNSET
        if not isinstance(self.condition, Unset):
            condition = self.condition.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if name is not UNSET:
            field_dict["name"] = name
        if device_id is not UNSET:
            field_dict["device_id"] = device_id
        if qubits is not UNSET:
            field_dict["qubits"] = qubits
        if exclude_couplings is not UNSET:
            field_dict["exclude_couplings"] = exclude_couplings
        if condition is not UNSET:
            field_dict["condition"] = condition

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.condition import Condition

        d = dict(src_dict)
        name = d.pop("name", UNSET)

        device_id = d.pop("device_id", UNSET)

        qubits = cast(list[str], d.pop("qubits", UNSET))

        exclude_couplings = cast(list[str], d.pop("exclude_couplings", UNSET))

        _condition = d.pop("condition", UNSET)
        condition: Union[Unset, Condition]
        if isinstance(_condition, Unset):
            condition = UNSET
        else:
            condition = Condition.from_dict(_condition)

        device_topology_request = cls(
            name=name,
            device_id=device_id,
            qubits=qubits,
            exclude_couplings=exclude_couplings,
            condition=condition,
        )

        device_topology_request.additional_properties = d
        return device_topology_request

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
