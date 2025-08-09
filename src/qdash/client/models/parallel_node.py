from typing import TYPE_CHECKING, Any, TypeVar, Union, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.batch_node import BatchNode
    from ..models.serial_node import SerialNode


T = TypeVar("T", bound="ParallelNode")


@_attrs_define
class ParallelNode:
    """Parallel node model.

    Attributes:
        parallel (list[Union['BatchNode', 'ParallelNode', 'SerialNode', str]]):
    """

    parallel: list[Union["BatchNode", "ParallelNode", "SerialNode", str]]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.batch_node import BatchNode
        from ..models.serial_node import SerialNode

        parallel = []
        for parallel_item_data in self.parallel:
            parallel_item: Union[dict[str, Any], str]
            if isinstance(parallel_item_data, SerialNode):
                parallel_item = parallel_item_data.to_dict()
            elif isinstance(parallel_item_data, ParallelNode):
                parallel_item = parallel_item_data.to_dict()
            elif isinstance(parallel_item_data, BatchNode):
                parallel_item = parallel_item_data.to_dict()
            else:
                parallel_item = parallel_item_data
            parallel.append(parallel_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "parallel": parallel,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: dict[str, Any]) -> T:
        from ..models.batch_node import BatchNode
        from ..models.serial_node import SerialNode

        d = src_dict.copy()
        parallel = []
        _parallel = d.pop("parallel")
        for parallel_item_data in _parallel:

            def _parse_parallel_item(data: object) -> Union["BatchNode", "ParallelNode", "SerialNode", str]:
                try:
                    if not isinstance(data, dict):
                        raise TypeError()
                    parallel_item_type_0 = SerialNode.from_dict(data)

                    return parallel_item_type_0
                except:  # noqa: E722
                    pass
                try:
                    if not isinstance(data, dict):
                        raise TypeError()
                    parallel_item_type_1 = ParallelNode.from_dict(data)

                    return parallel_item_type_1
                except:  # noqa: E722
                    pass
                try:
                    if not isinstance(data, dict):
                        raise TypeError()
                    parallel_item_type_2 = BatchNode.from_dict(data)

                    return parallel_item_type_2
                except:  # noqa: E722
                    pass
                return cast(Union["BatchNode", "ParallelNode", "SerialNode", str], data)

            parallel_item = _parse_parallel_item(parallel_item_data)

            parallel.append(parallel_item)

        parallel_node = cls(
            parallel=parallel,
        )

        parallel_node.additional_properties = d
        return parallel_node

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
