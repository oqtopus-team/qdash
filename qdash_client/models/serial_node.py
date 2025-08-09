from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.batch_node import BatchNode
    from ..models.parallel_node import ParallelNode


T = TypeVar("T", bound="SerialNode")


@_attrs_define
class SerialNode:
    """Serial node model.

    Attributes:
        serial (list[Union['BatchNode', 'ParallelNode', 'SerialNode', str]]):
    """

    serial: list[Union["BatchNode", "ParallelNode", "SerialNode", str]]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.batch_node import BatchNode
        from ..models.parallel_node import ParallelNode

        serial = []
        for serial_item_data in self.serial:
            serial_item: Union[dict[str, Any], str]
            if isinstance(serial_item_data, SerialNode):
                serial_item = serial_item_data.to_dict()
            elif isinstance(serial_item_data, ParallelNode):
                serial_item = serial_item_data.to_dict()
            elif isinstance(serial_item_data, BatchNode):
                serial_item = serial_item_data.to_dict()
            else:
                serial_item = serial_item_data
            serial.append(serial_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "serial": serial,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.batch_node import BatchNode
        from ..models.parallel_node import ParallelNode

        d = dict(src_dict)
        serial = []
        _serial = d.pop("serial")
        for serial_item_data in _serial:

            def _parse_serial_item(data: object) -> Union["BatchNode", "ParallelNode", "SerialNode", str]:
                try:
                    if not isinstance(data, dict):
                        raise TypeError()
                    serial_item_type_0 = SerialNode.from_dict(data)

                    return serial_item_type_0
                except:  # noqa: E722
                    pass
                try:
                    if not isinstance(data, dict):
                        raise TypeError()
                    serial_item_type_1 = ParallelNode.from_dict(data)

                    return serial_item_type_1
                except:  # noqa: E722
                    pass
                try:
                    if not isinstance(data, dict):
                        raise TypeError()
                    serial_item_type_2 = BatchNode.from_dict(data)

                    return serial_item_type_2
                except:  # noqa: E722
                    pass
                return cast(Union["BatchNode", "ParallelNode", "SerialNode", str], data)

            serial_item = _parse_serial_item(serial_item_data)

            serial.append(serial_item)

        serial_node = cls(
            serial=serial,
        )

        serial_node.additional_properties = d
        return serial_node

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
