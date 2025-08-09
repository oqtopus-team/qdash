from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.task_response_input_parameters import TaskResponseInputParameters
    from ..models.task_response_output_parameters import TaskResponseOutputParameters


T = TypeVar("T", bound="TaskResponse")


@_attrs_define
class TaskResponse:
    """Response model for a task.

    Attributes:
        name (str):
        description (str):
        task_type (str):
        input_parameters (TaskResponseInputParameters):
        output_parameters (TaskResponseOutputParameters):
        backend (Union[None, Unset, str]):
    """

    name: str
    description: str
    task_type: str
    input_parameters: "TaskResponseInputParameters"
    output_parameters: "TaskResponseOutputParameters"
    backend: Union[None, Unset, str] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        name = self.name

        description = self.description

        task_type = self.task_type

        input_parameters = self.input_parameters.to_dict()

        output_parameters = self.output_parameters.to_dict()

        backend: Union[None, Unset, str]
        if isinstance(self.backend, Unset):
            backend = UNSET
        else:
            backend = self.backend

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "name": name,
                "description": description,
                "task_type": task_type,
                "input_parameters": input_parameters,
                "output_parameters": output_parameters,
            }
        )
        if backend is not UNSET:
            field_dict["backend"] = backend

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.task_response_input_parameters import TaskResponseInputParameters
        from ..models.task_response_output_parameters import TaskResponseOutputParameters

        d = dict(src_dict)
        name = d.pop("name")

        description = d.pop("description")

        task_type = d.pop("task_type")

        input_parameters = TaskResponseInputParameters.from_dict(d.pop("input_parameters"))

        output_parameters = TaskResponseOutputParameters.from_dict(d.pop("output_parameters"))

        def _parse_backend(data: object) -> Union[None, Unset, str]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(Union[None, Unset, str], data)

        backend = _parse_backend(d.pop("backend", UNSET))

        task_response = cls(
            name=name,
            description=description,
            task_type=task_type,
            input_parameters=input_parameters,
            output_parameters=output_parameters,
            backend=backend,
        )

        task_response.additional_properties = d
        return task_response

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
