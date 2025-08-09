from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.task_input_parameters_type_0 import TaskInputParametersType0
    from ..models.task_note_type_0 import TaskNoteType0
    from ..models.task_output_parameters_type_0 import TaskOutputParametersType0


T = TypeVar("T", bound="Task")


@_attrs_define
class Task:
    """Task is a Pydantic model that represents a task.

    Attributes:
        task_id (Union[None, Unset, str]):
        qid (Union[None, Unset, str]):
        name (Union[Unset, str]):  Default: ''.
        upstream_id (Union[None, Unset, str]):
        status (Union[Unset, str]):  Default: 'pending'.
        message (Union[None, Unset, str]):
        input_parameters (Union['TaskInputParametersType0', None, Unset]):
        output_parameters (Union['TaskOutputParametersType0', None, Unset]):
        output_parameter_names (Union[None, Unset, list[str]]):
        note (Union['TaskNoteType0', None, Unset]):
        figure_path (Union[None, Unset, list[str]]):
        json_figure_path (Union[None, Unset, list[str]]):
        raw_data_path (Union[None, Unset, list[str]]):
        start_at (Union[None, Unset, str]):
        end_at (Union[None, Unset, str]):
        elapsed_time (Union[None, Unset, str]):
        task_type (Union[None, Unset, str]):
        default_view (Union[Unset, bool]):  Default: True.
        over_threshold (Union[Unset, bool]):  Default: False.
    """

    task_id: Union[None, Unset, str] = UNSET
    qid: Union[None, Unset, str] = UNSET
    name: Union[Unset, str] = ""
    upstream_id: Union[None, Unset, str] = UNSET
    status: Union[Unset, str] = "pending"
    message: Union[None, Unset, str] = UNSET
    input_parameters: Union["TaskInputParametersType0", None, Unset] = UNSET
    output_parameters: Union["TaskOutputParametersType0", None, Unset] = UNSET
    output_parameter_names: Union[None, Unset, list[str]] = UNSET
    note: Union["TaskNoteType0", None, Unset] = UNSET
    figure_path: Union[None, Unset, list[str]] = UNSET
    json_figure_path: Union[None, Unset, list[str]] = UNSET
    raw_data_path: Union[None, Unset, list[str]] = UNSET
    start_at: Union[None, Unset, str] = UNSET
    end_at: Union[None, Unset, str] = UNSET
    elapsed_time: Union[None, Unset, str] = UNSET
    task_type: Union[None, Unset, str] = UNSET
    default_view: Union[Unset, bool] = True
    over_threshold: Union[Unset, bool] = False
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.task_input_parameters_type_0 import TaskInputParametersType0
        from ..models.task_note_type_0 import TaskNoteType0
        from ..models.task_output_parameters_type_0 import TaskOutputParametersType0

        task_id: Union[None, Unset, str]
        if isinstance(self.task_id, Unset):
            task_id = UNSET
        else:
            task_id = self.task_id

        qid: Union[None, Unset, str]
        if isinstance(self.qid, Unset):
            qid = UNSET
        else:
            qid = self.qid

        name = self.name

        upstream_id: Union[None, Unset, str]
        if isinstance(self.upstream_id, Unset):
            upstream_id = UNSET
        else:
            upstream_id = self.upstream_id

        status = self.status

        message: Union[None, Unset, str]
        if isinstance(self.message, Unset):
            message = UNSET
        else:
            message = self.message

        input_parameters: Union[None, Unset, dict[str, Any]]
        if isinstance(self.input_parameters, Unset):
            input_parameters = UNSET
        elif isinstance(self.input_parameters, TaskInputParametersType0):
            input_parameters = self.input_parameters.to_dict()
        else:
            input_parameters = self.input_parameters

        output_parameters: Union[None, Unset, dict[str, Any]]
        if isinstance(self.output_parameters, Unset):
            output_parameters = UNSET
        elif isinstance(self.output_parameters, TaskOutputParametersType0):
            output_parameters = self.output_parameters.to_dict()
        else:
            output_parameters = self.output_parameters

        output_parameter_names: Union[None, Unset, list[str]]
        if isinstance(self.output_parameter_names, Unset):
            output_parameter_names = UNSET
        elif isinstance(self.output_parameter_names, list):
            output_parameter_names = self.output_parameter_names

        else:
            output_parameter_names = self.output_parameter_names

        note: Union[None, Unset, dict[str, Any]]
        if isinstance(self.note, Unset):
            note = UNSET
        elif isinstance(self.note, TaskNoteType0):
            note = self.note.to_dict()
        else:
            note = self.note

        figure_path: Union[None, Unset, list[str]]
        if isinstance(self.figure_path, Unset):
            figure_path = UNSET
        elif isinstance(self.figure_path, list):
            figure_path = self.figure_path

        else:
            figure_path = self.figure_path

        json_figure_path: Union[None, Unset, list[str]]
        if isinstance(self.json_figure_path, Unset):
            json_figure_path = UNSET
        elif isinstance(self.json_figure_path, list):
            json_figure_path = self.json_figure_path

        else:
            json_figure_path = self.json_figure_path

        raw_data_path: Union[None, Unset, list[str]]
        if isinstance(self.raw_data_path, Unset):
            raw_data_path = UNSET
        elif isinstance(self.raw_data_path, list):
            raw_data_path = self.raw_data_path

        else:
            raw_data_path = self.raw_data_path

        start_at: Union[None, Unset, str]
        if isinstance(self.start_at, Unset):
            start_at = UNSET
        else:
            start_at = self.start_at

        end_at: Union[None, Unset, str]
        if isinstance(self.end_at, Unset):
            end_at = UNSET
        else:
            end_at = self.end_at

        elapsed_time: Union[None, Unset, str]
        if isinstance(self.elapsed_time, Unset):
            elapsed_time = UNSET
        else:
            elapsed_time = self.elapsed_time

        task_type: Union[None, Unset, str]
        if isinstance(self.task_type, Unset):
            task_type = UNSET
        else:
            task_type = self.task_type

        default_view = self.default_view

        over_threshold = self.over_threshold

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if task_id is not UNSET:
            field_dict["task_id"] = task_id
        if qid is not UNSET:
            field_dict["qid"] = qid
        if name is not UNSET:
            field_dict["name"] = name
        if upstream_id is not UNSET:
            field_dict["upstream_id"] = upstream_id
        if status is not UNSET:
            field_dict["status"] = status
        if message is not UNSET:
            field_dict["message"] = message
        if input_parameters is not UNSET:
            field_dict["input_parameters"] = input_parameters
        if output_parameters is not UNSET:
            field_dict["output_parameters"] = output_parameters
        if output_parameter_names is not UNSET:
            field_dict["output_parameter_names"] = output_parameter_names
        if note is not UNSET:
            field_dict["note"] = note
        if figure_path is not UNSET:
            field_dict["figure_path"] = figure_path
        if json_figure_path is not UNSET:
            field_dict["json_figure_path"] = json_figure_path
        if raw_data_path is not UNSET:
            field_dict["raw_data_path"] = raw_data_path
        if start_at is not UNSET:
            field_dict["start_at"] = start_at
        if end_at is not UNSET:
            field_dict["end_at"] = end_at
        if elapsed_time is not UNSET:
            field_dict["elapsed_time"] = elapsed_time
        if task_type is not UNSET:
            field_dict["task_type"] = task_type
        if default_view is not UNSET:
            field_dict["default_view"] = default_view
        if over_threshold is not UNSET:
            field_dict["over_threshold"] = over_threshold

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.task_input_parameters_type_0 import TaskInputParametersType0
        from ..models.task_note_type_0 import TaskNoteType0
        from ..models.task_output_parameters_type_0 import TaskOutputParametersType0

        d = dict(src_dict)

        def _parse_task_id(data: object) -> Union[None, Unset, str]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(Union[None, Unset, str], data)

        task_id = _parse_task_id(d.pop("task_id", UNSET))

        def _parse_qid(data: object) -> Union[None, Unset, str]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(Union[None, Unset, str], data)

        qid = _parse_qid(d.pop("qid", UNSET))

        name = d.pop("name", UNSET)

        def _parse_upstream_id(data: object) -> Union[None, Unset, str]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(Union[None, Unset, str], data)

        upstream_id = _parse_upstream_id(d.pop("upstream_id", UNSET))

        status = d.pop("status", UNSET)

        def _parse_message(data: object) -> Union[None, Unset, str]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(Union[None, Unset, str], data)

        message = _parse_message(d.pop("message", UNSET))

        def _parse_input_parameters(data: object) -> Union["TaskInputParametersType0", None, Unset]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                input_parameters_type_0 = TaskInputParametersType0.from_dict(data)

                return input_parameters_type_0
            except:  # noqa: E722
                pass
            return cast(Union["TaskInputParametersType0", None, Unset], data)

        input_parameters = _parse_input_parameters(d.pop("input_parameters", UNSET))

        def _parse_output_parameters(data: object) -> Union["TaskOutputParametersType0", None, Unset]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                output_parameters_type_0 = TaskOutputParametersType0.from_dict(data)

                return output_parameters_type_0
            except:  # noqa: E722
                pass
            return cast(Union["TaskOutputParametersType0", None, Unset], data)

        output_parameters = _parse_output_parameters(d.pop("output_parameters", UNSET))

        def _parse_output_parameter_names(data: object) -> Union[None, Unset, list[str]]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                output_parameter_names_type_0 = cast(list[str], data)

                return output_parameter_names_type_0
            except:  # noqa: E722
                pass
            return cast(Union[None, Unset, list[str]], data)

        output_parameter_names = _parse_output_parameter_names(d.pop("output_parameter_names", UNSET))

        def _parse_note(data: object) -> Union["TaskNoteType0", None, Unset]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                note_type_0 = TaskNoteType0.from_dict(data)

                return note_type_0
            except:  # noqa: E722
                pass
            return cast(Union["TaskNoteType0", None, Unset], data)

        note = _parse_note(d.pop("note", UNSET))

        def _parse_figure_path(data: object) -> Union[None, Unset, list[str]]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                figure_path_type_0 = cast(list[str], data)

                return figure_path_type_0
            except:  # noqa: E722
                pass
            return cast(Union[None, Unset, list[str]], data)

        figure_path = _parse_figure_path(d.pop("figure_path", UNSET))

        def _parse_json_figure_path(data: object) -> Union[None, Unset, list[str]]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                json_figure_path_type_0 = cast(list[str], data)

                return json_figure_path_type_0
            except:  # noqa: E722
                pass
            return cast(Union[None, Unset, list[str]], data)

        json_figure_path = _parse_json_figure_path(d.pop("json_figure_path", UNSET))

        def _parse_raw_data_path(data: object) -> Union[None, Unset, list[str]]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                raw_data_path_type_0 = cast(list[str], data)

                return raw_data_path_type_0
            except:  # noqa: E722
                pass
            return cast(Union[None, Unset, list[str]], data)

        raw_data_path = _parse_raw_data_path(d.pop("raw_data_path", UNSET))

        def _parse_start_at(data: object) -> Union[None, Unset, str]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(Union[None, Unset, str], data)

        start_at = _parse_start_at(d.pop("start_at", UNSET))

        def _parse_end_at(data: object) -> Union[None, Unset, str]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(Union[None, Unset, str], data)

        end_at = _parse_end_at(d.pop("end_at", UNSET))

        def _parse_elapsed_time(data: object) -> Union[None, Unset, str]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(Union[None, Unset, str], data)

        elapsed_time = _parse_elapsed_time(d.pop("elapsed_time", UNSET))

        def _parse_task_type(data: object) -> Union[None, Unset, str]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(Union[None, Unset, str], data)

        task_type = _parse_task_type(d.pop("task_type", UNSET))

        default_view = d.pop("default_view", UNSET)

        over_threshold = d.pop("over_threshold", UNSET)

        task = cls(
            task_id=task_id,
            qid=qid,
            name=name,
            upstream_id=upstream_id,
            status=status,
            message=message,
            input_parameters=input_parameters,
            output_parameters=output_parameters,
            output_parameter_names=output_parameter_names,
            note=note,
            figure_path=figure_path,
            json_figure_path=json_figure_path,
            raw_data_path=raw_data_path,
            start_at=start_at,
            end_at=end_at,
            elapsed_time=elapsed_time,
            task_type=task_type,
            default_view=default_view,
            over_threshold=over_threshold,
        )

        task.additional_properties = d
        return task

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
