from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.fidelity_condition import FidelityCondition


T = TypeVar("T", bound="Condition")


@_attrs_define
class Condition:
    """Condition for filtering device topology.

    Attributes:
        coupling_fidelity (FidelityCondition): Condition for fidelity filtering.
        qubit_fidelity (FidelityCondition): Condition for fidelity filtering.
        readout_fidelity (FidelityCondition): Condition for fidelity filtering.
        only_maximum_connected (Union[Unset, bool]):  Default: True.
    """

    coupling_fidelity: "FidelityCondition"
    qubit_fidelity: "FidelityCondition"
    readout_fidelity: "FidelityCondition"
    only_maximum_connected: Union[Unset, bool] = True
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        coupling_fidelity = self.coupling_fidelity.to_dict()

        qubit_fidelity = self.qubit_fidelity.to_dict()

        readout_fidelity = self.readout_fidelity.to_dict()

        only_maximum_connected = self.only_maximum_connected

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "coupling_fidelity": coupling_fidelity,
                "qubit_fidelity": qubit_fidelity,
                "readout_fidelity": readout_fidelity,
            }
        )
        if only_maximum_connected is not UNSET:
            field_dict["only_maximum_connected"] = only_maximum_connected

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.fidelity_condition import FidelityCondition

        d = dict(src_dict)
        coupling_fidelity = FidelityCondition.from_dict(d.pop("coupling_fidelity"))

        qubit_fidelity = FidelityCondition.from_dict(d.pop("qubit_fidelity"))

        readout_fidelity = FidelityCondition.from_dict(d.pop("readout_fidelity"))

        only_maximum_connected = d.pop("only_maximum_connected", UNSET)

        condition = cls(
            coupling_fidelity=coupling_fidelity,
            qubit_fidelity=qubit_fidelity,
            readout_fidelity=readout_fidelity,
            only_maximum_connected=only_maximum_connected,
        )

        condition.additional_properties = d
        return condition

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
