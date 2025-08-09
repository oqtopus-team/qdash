from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.menu_model import MenuModel


T = TypeVar("T", bound="ListMenuResponse")


@_attrs_define
class ListMenuResponse:
    """ListMenuResponse is a Pydantic model that represents a menu item.

    Attributes:
        menus (list['MenuModel']):
    """

    menus: list["MenuModel"]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        menus = []
        for menus_item_data in self.menus:
            menus_item = menus_item_data.to_dict()
            menus.append(menus_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "menus": menus,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: dict[str, Any]) -> T:
        from ..models.menu_model import MenuModel

        d = src_dict.copy()
        menus = []
        _menus = d.pop("menus")
        for menus_item_data in _menus:
            menus_item = MenuModel.from_dict(menus_item_data)

            menus.append(menus_item)

        list_menu_response = cls(
            menus=menus,
        )

        list_menu_response.additional_properties = d
        return list_menu_response

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
