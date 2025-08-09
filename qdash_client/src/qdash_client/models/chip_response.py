from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.chip_response_couplings import ChipResponseCouplings
    from ..models.chip_response_qubits import ChipResponseQubits


T = TypeVar("T", bound="ChipResponse")


@_attrs_define
class ChipResponse:
    """Chip is a Pydantic model that represents a chip.

    Attributes
    ----------
        chip_id (str): The ID of the chip.
        name (str): The name of the chip.

        Attributes:
            chip_id (str):
            size (Union[Unset, int]):  Default: 64.
            qubits (Union[Unset, ChipResponseQubits]):
            couplings (Union[Unset, ChipResponseCouplings]):
            installed_at (Union[Unset, str]):  Default: ''.
    """

    chip_id: str
    size: Union[Unset, int] = 64
    qubits: Union[Unset, "ChipResponseQubits"] = UNSET
    couplings: Union[Unset, "ChipResponseCouplings"] = UNSET
    installed_at: Union[Unset, str] = ""
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        chip_id = self.chip_id

        size = self.size

        qubits: Union[Unset, dict[str, Any]] = UNSET
        if not isinstance(self.qubits, Unset):
            qubits = self.qubits.to_dict()

        couplings: Union[Unset, dict[str, Any]] = UNSET
        if not isinstance(self.couplings, Unset):
            couplings = self.couplings.to_dict()

        installed_at = self.installed_at

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "chip_id": chip_id,
            }
        )
        if size is not UNSET:
            field_dict["size"] = size
        if qubits is not UNSET:
            field_dict["qubits"] = qubits
        if couplings is not UNSET:
            field_dict["couplings"] = couplings
        if installed_at is not UNSET:
            field_dict["installed_at"] = installed_at

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.chip_response_couplings import ChipResponseCouplings
        from ..models.chip_response_qubits import ChipResponseQubits

        d = dict(src_dict)
        chip_id = d.pop("chip_id")

        size = d.pop("size", UNSET)

        _qubits = d.pop("qubits", UNSET)
        qubits: Union[Unset, ChipResponseQubits]
        if isinstance(_qubits, Unset):
            qubits = UNSET
        else:
            qubits = ChipResponseQubits.from_dict(_qubits)

        _couplings = d.pop("couplings", UNSET)
        couplings: Union[Unset, ChipResponseCouplings]
        if isinstance(_couplings, Unset):
            couplings = UNSET
        else:
            couplings = ChipResponseCouplings.from_dict(_couplings)

        installed_at = d.pop("installed_at", UNSET)

        chip_response = cls(
            chip_id=chip_id,
            size=size,
            qubits=qubits,
            couplings=couplings,
            installed_at=installed_at,
        )

        chip_response.additional_properties = d
        return chip_response

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
