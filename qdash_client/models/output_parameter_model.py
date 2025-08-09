from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from typing import cast, Union


T = TypeVar("T", bound="OutputParameterModel")


@_attrs_define
class OutputParameterModel:
    """Data model.

    Attributes
    ----------
        qubit (dict[str, dict[str, float | int]]): The calibration data for qubits.
        coupling (dict[str, dict[str, float | int]]): The calibration data for couplings.

        Attributes:
            value (Union[Unset, float, int]):  Default: 0.0.
            value_type (Union[Unset, str]):  Default: 'float'.
            error (Union[Unset, float]):  Default: 0.0.
            unit (Union[Unset, str]):  Default: ''.
            description (Union[Unset, str]):  Default: ''.
            calibrated_at (Union[Unset, str]): The time when the system information was created
            execution_id (Union[Unset, str]):  Default: ''.
    """

    value: Union[Unset, float, int] = 0.0
    value_type: Union[Unset, str] = "float"
    error: Union[Unset, float] = 0.0
    unit: Union[Unset, str] = ""
    description: Union[Unset, str] = ""
    calibrated_at: Union[Unset, str] = UNSET
    execution_id: Union[Unset, str] = ""
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        value: Union[Unset, float, int]
        if isinstance(self.value, Unset):
            value = UNSET
        else:
            value = self.value

        value_type = self.value_type

        error = self.error

        unit = self.unit

        description = self.description

        calibrated_at = self.calibrated_at

        execution_id = self.execution_id

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if value is not UNSET:
            field_dict["value"] = value
        if value_type is not UNSET:
            field_dict["value_type"] = value_type
        if error is not UNSET:
            field_dict["error"] = error
        if unit is not UNSET:
            field_dict["unit"] = unit
        if description is not UNSET:
            field_dict["description"] = description
        if calibrated_at is not UNSET:
            field_dict["calibrated_at"] = calibrated_at
        if execution_id is not UNSET:
            field_dict["execution_id"] = execution_id

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)

        def _parse_value(data: object) -> Union[Unset, float, int]:
            if isinstance(data, Unset):
                return data
            return cast(Union[Unset, float, int], data)

        value = _parse_value(d.pop("value", UNSET))

        value_type = d.pop("value_type", UNSET)

        error = d.pop("error", UNSET)

        unit = d.pop("unit", UNSET)

        description = d.pop("description", UNSET)

        calibrated_at = d.pop("calibrated_at", UNSET)

        execution_id = d.pop("execution_id", UNSET)

        output_parameter_model = cls(
            value=value,
            value_type=value_type,
            error=error,
            unit=unit,
            description=description,
            calibrated_at=calibrated_at,
            execution_id=execution_id,
        )

        output_parameter_model.additional_properties = d
        return output_parameter_model

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
