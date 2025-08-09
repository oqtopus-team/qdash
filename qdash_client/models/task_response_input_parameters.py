from collections.abc import Mapping
from typing import Any, TypeVar, TYPE_CHECKING

from attrs import define as _attrs_define
from attrs import field as _attrs_field



if TYPE_CHECKING:
    from ..models.input_parameter_model import InputParameterModel


T = TypeVar("T", bound="TaskResponseInputParameters")


@_attrs_define
class TaskResponseInputParameters:
    """ """

    additional_properties: dict[str, "InputParameterModel"] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:

        field_dict: dict[str, Any] = {}
        for prop_name, prop in self.additional_properties.items():
            field_dict[prop_name] = prop.to_dict()

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.input_parameter_model import InputParameterModel

        d = dict(src_dict)
        task_response_input_parameters = cls()

        additional_properties = {}
        for prop_name, prop_dict in d.items():
            additional_property = InputParameterModel.from_dict(prop_dict)

            additional_properties[prop_name] = additional_property

        task_response_input_parameters.additional_properties = additional_properties
        return task_response_input_parameters

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> "InputParameterModel":
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: "InputParameterModel") -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
