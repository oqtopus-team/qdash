from collections.abc import Mapping
from typing import Any, TypeVar, TYPE_CHECKING

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from typing import cast
from typing import Union

if TYPE_CHECKING:
    from ..models.batch_node import BatchNode
    from ..models.parallel_node import ParallelNode
    from ..models.serial_node import SerialNode
    from ..models.menu_model_task_details_type_0 import MenuModelTaskDetailsType0


T = TypeVar("T", bound="MenuModel")


@_attrs_define
class MenuModel:
    """Menu model.

    Attributes
    ----------
        name (str): The name of the menu.
        username (str): The username of the user who created
        description (str): Detailed description of the menu.
        cal_plan (list[list[int]]): The calibration plan.
        notify_bool (bool): The notification boolean.
        tasks (list[str]): The tasks.
        tags (list[str]): The tags.

        Attributes:
            name (str):
            chip_id (str):
            username (str):
            description (str):
            schedule (Union['BatchNode', 'ParallelNode', 'SerialNode']):
            backend (Union[Unset, str]):  Default: ''.
            notify_bool (Union[Unset, bool]):  Default: False.
            tasks (Union[None, Unset, list[str]]):
            task_details (Union['MenuModelTaskDetailsType0', None, Unset]):
            tags (Union[None, Unset, list[str]]):
    """

    name: str
    chip_id: str
    username: str
    description: str
    schedule: Union["BatchNode", "ParallelNode", "SerialNode"]
    backend: Union[Unset, str] = ""
    notify_bool: Union[Unset, bool] = False
    tasks: Union[None, Unset, list[str]] = UNSET
    task_details: Union["MenuModelTaskDetailsType0", None, Unset] = UNSET
    tags: Union[None, Unset, list[str]] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.parallel_node import ParallelNode
        from ..models.serial_node import SerialNode
        from ..models.menu_model_task_details_type_0 import MenuModelTaskDetailsType0

        name = self.name

        chip_id = self.chip_id

        username = self.username

        description = self.description

        schedule: dict[str, Any]
        if isinstance(self.schedule, SerialNode):
            schedule = self.schedule.to_dict()
        elif isinstance(self.schedule, ParallelNode):
            schedule = self.schedule.to_dict()
        else:
            schedule = self.schedule.to_dict()

        backend = self.backend

        notify_bool = self.notify_bool

        tasks: Union[None, Unset, list[str]]
        if isinstance(self.tasks, Unset):
            tasks = UNSET
        elif isinstance(self.tasks, list):
            tasks = self.tasks

        else:
            tasks = self.tasks

        task_details: Union[None, Unset, dict[str, Any]]
        if isinstance(self.task_details, Unset):
            task_details = UNSET
        elif isinstance(self.task_details, MenuModelTaskDetailsType0):
            task_details = self.task_details.to_dict()
        else:
            task_details = self.task_details

        tags: Union[None, Unset, list[str]]
        if isinstance(self.tags, Unset):
            tags = UNSET
        elif isinstance(self.tags, list):
            tags = self.tags

        else:
            tags = self.tags

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "name": name,
                "chip_id": chip_id,
                "username": username,
                "description": description,
                "schedule": schedule,
            }
        )
        if backend is not UNSET:
            field_dict["backend"] = backend
        if notify_bool is not UNSET:
            field_dict["notify_bool"] = notify_bool
        if tasks is not UNSET:
            field_dict["tasks"] = tasks
        if task_details is not UNSET:
            field_dict["task_details"] = task_details
        if tags is not UNSET:
            field_dict["tags"] = tags

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.batch_node import BatchNode
        from ..models.parallel_node import ParallelNode
        from ..models.serial_node import SerialNode
        from ..models.menu_model_task_details_type_0 import MenuModelTaskDetailsType0

        d = dict(src_dict)
        name = d.pop("name")

        chip_id = d.pop("chip_id")

        username = d.pop("username")

        description = d.pop("description")

        def _parse_schedule(data: object) -> Union["BatchNode", "ParallelNode", "SerialNode"]:
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                schedule_type_0 = SerialNode.from_dict(data)

                return schedule_type_0
            except:  # noqa: E722
                pass
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                schedule_type_1 = ParallelNode.from_dict(data)

                return schedule_type_1
            except:  # noqa: E722
                pass
            if not isinstance(data, dict):
                raise TypeError()
            schedule_type_2 = BatchNode.from_dict(data)

            return schedule_type_2

        schedule = _parse_schedule(d.pop("schedule"))

        backend = d.pop("backend", UNSET)

        notify_bool = d.pop("notify_bool", UNSET)

        def _parse_tasks(data: object) -> Union[None, Unset, list[str]]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                tasks_type_0 = cast(list[str], data)

                return tasks_type_0
            except:  # noqa: E722
                pass
            return cast(Union[None, Unset, list[str]], data)

        tasks = _parse_tasks(d.pop("tasks", UNSET))

        def _parse_task_details(data: object) -> Union["MenuModelTaskDetailsType0", None, Unset]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                task_details_type_0 = MenuModelTaskDetailsType0.from_dict(data)

                return task_details_type_0
            except:  # noqa: E722
                pass
            return cast(Union["MenuModelTaskDetailsType0", None, Unset], data)

        task_details = _parse_task_details(d.pop("task_details", UNSET))

        def _parse_tags(data: object) -> Union[None, Unset, list[str]]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                tags_type_0 = cast(list[str], data)

                return tags_type_0
            except:  # noqa: E722
                pass
            return cast(Union[None, Unset, list[str]], data)

        tags = _parse_tags(d.pop("tags", UNSET))

        menu_model = cls(
            name=name,
            chip_id=chip_id,
            username=username,
            description=description,
            schedule=schedule,
            backend=backend,
            notify_bool=notify_bool,
            tasks=tasks,
            task_details=task_details,
            tags=tags,
        )

        menu_model.additional_properties = d
        return menu_model

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
