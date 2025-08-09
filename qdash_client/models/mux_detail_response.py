from collections.abc import Mapping
from typing import Any, TypeVar, TYPE_CHECKING

from attrs import define as _attrs_define
from attrs import field as _attrs_field



if TYPE_CHECKING:
    from ..models.mux_detail_response_detail import MuxDetailResponseDetail


T = TypeVar("T", bound="MuxDetailResponse")


@_attrs_define
class MuxDetailResponse:
    """MuxDetailResponse is a Pydantic model that represents the response for fetching the multiplexer details.

    Attributes:
        mux_id (int):
        detail (MuxDetailResponseDetail):
    """

    mux_id: int
    detail: "MuxDetailResponseDetail"
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:

        mux_id = self.mux_id

        detail = self.detail.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "mux_id": mux_id,
                "detail": detail,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.mux_detail_response_detail import MuxDetailResponseDetail

        d = dict(src_dict)
        mux_id = d.pop("mux_id")

        detail = MuxDetailResponseDetail.from_dict(d.pop("detail"))

        mux_detail_response = cls(
            mux_id=mux_id,
            detail=detail,
        )

        mux_detail_response.additional_properties = d
        return mux_detail_response

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
