from typing import Any, TypeVar, Union, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="InputParameterModel")


@_attrs_define
class InputParameterModel:
    """Input parameter class.

    Attributes:
        unit (Union[Unset, str]):  Default: ''.
        value_type (Union[Unset, str]):  Default: 'float'.
        value (Union[None, Unset, float, int, list[Any]]):
        description (Union[Unset, str]):  Default: ''.
    """

    unit: Union[Unset, str] = ""
    value_type: Union[Unset, str] = "float"
    value: Union[None, Unset, float, int, list[Any]] = UNSET
    description: Union[Unset, str] = ""
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        unit = self.unit

        value_type = self.value_type

        value: Union[None, Unset, float, int, list[Any]]
        if isinstance(self.value, Unset):
            value = UNSET
        elif isinstance(self.value, list):
            value = self.value

        else:
            value = self.value

        description = self.description

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if unit is not UNSET:
            field_dict["unit"] = unit
        if value_type is not UNSET:
            field_dict["value_type"] = value_type
        if value is not UNSET:
            field_dict["value"] = value
        if description is not UNSET:
            field_dict["description"] = description

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: dict[str, Any]) -> T:
        d = src_dict.copy()
        unit = d.pop("unit", UNSET)

        value_type = d.pop("value_type", UNSET)

        def _parse_value(data: object) -> Union[None, Unset, float, int, list[Any]]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                value_type_0 = cast(list[Any], data)

                return value_type_0
            except:  # noqa: E722
                pass
            return cast(Union[None, Unset, float, int, list[Any]], data)

        value = _parse_value(d.pop("value", UNSET))

        description = d.pop("description", UNSET)

        input_parameter_model = cls(
            unit=unit,
            value_type=value_type,
            value=value,
            description=description,
        )

        input_parameter_model.additional_properties = d
        return input_parameter_model

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
