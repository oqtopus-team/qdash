from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="MeasError")


@_attrs_define
class MeasError:
    """Measurement error of the qubit.

    Attributes:
        prob_meas1_prep0 (float):
        prob_meas0_prep1 (float):
        readout_assignment_error (float):
    """

    prob_meas1_prep0: float
    prob_meas0_prep1: float
    readout_assignment_error: float
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        prob_meas1_prep0 = self.prob_meas1_prep0

        prob_meas0_prep1 = self.prob_meas0_prep1

        readout_assignment_error = self.readout_assignment_error

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "prob_meas1_prep0": prob_meas1_prep0,
                "prob_meas0_prep1": prob_meas0_prep1,
                "readout_assignment_error": readout_assignment_error,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        prob_meas1_prep0 = d.pop("prob_meas1_prep0")

        prob_meas0_prep1 = d.pop("prob_meas0_prep1")

        readout_assignment_error = d.pop("readout_assignment_error")

        meas_error = cls(
            prob_meas1_prep0=prob_meas1_prep0,
            prob_meas0_prep1=prob_meas0_prep1,
            readout_assignment_error=readout_assignment_error,
        )

        meas_error.additional_properties = d
        return meas_error

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
