from typing import Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="ParameterModel")


@_attrs_define
class ParameterModel:
    """Data model for a parameter.

    Attributes
    ----------
        name (str): The name of the parameter.
        unit (str): The unit of the parameter.
        description (str): Detailed description of the parameter.

        Attributes:
            username (str): The username of the user who created the parameter
            name (str): The name of the parameter
            unit (Union[Unset, str]): The unit of the parameter Default: ''.
            description (Union[Unset, str]): Detailed description of the parameter Default: ''.
    """

    username: str
    name: str
    unit: Union[Unset, str] = ""
    description: Union[Unset, str] = ""
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        username = self.username

        name = self.name

        unit = self.unit

        description = self.description

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "username": username,
                "name": name,
            }
        )
        if unit is not UNSET:
            field_dict["unit"] = unit
        if description is not UNSET:
            field_dict["description"] = description

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: dict[str, Any]) -> T:
        d = src_dict.copy()
        username = d.pop("username")

        name = d.pop("name")

        unit = d.pop("unit", UNSET)

        description = d.pop("description", UNSET)

        parameter_model = cls(
            username=username,
            name=name,
            unit=unit,
            description=description,
        )

        parameter_model.additional_properties = d
        return parameter_model

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
