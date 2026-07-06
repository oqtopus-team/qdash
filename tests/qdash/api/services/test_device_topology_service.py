from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Literal, cast

import pytest
from pydantic import ValidationError

from qdash.api.schemas.device_topology import Condition, DeviceTopologyRequest
from qdash.api.services.device_topology_service import DeviceTopologyService

if TYPE_CHECKING:
    from qdash.repository.protocols import CalibrationNoteRepository, ChipRepository


def _service() -> DeviceTopologyService:
    return DeviceTopologyService(
        chip_repository=cast("ChipRepository", SimpleNamespace()),
        calibration_note_repository=cast("CalibrationNoteRepository", SimpleNamespace()),
    )


def _topology() -> SimpleNamespace:
    return SimpleNamespace(num_qubits=2, couplings=[[0, 1]])


@pytest.mark.parametrize(
    ("cr_direction", "expected_pairs"),
    [
        (None, [(0, 1), (1, 0)]),
        ("mix", [(0, 1), (1, 0)]),
        ("forward", [(0, 1)]),
        ("inverse", [(1, 0)]),
    ],
)
def test_build_couplings_filters_by_cr_direction(
    cr_direction: Literal["forward", "inverse", "mix"] | None,
    expected_pairs: list[tuple[int, int]],
) -> None:
    request = DeviceTopologyRequest(qubits=["0", "1"])
    request.condition.cr_direction = cr_direction
    cr_params: dict[str, dict[str, Any]] = {
        "Q00-Q01": {"duration": 20},
        "Q01-Q00": {"duration": 30},
    }

    couplings = _service()._build_couplings(
        request=request,
        cr_params=cr_params,
        coupling_models={},
        topology=_topology(),
        id_mapping={"0": 0, "1": 1},
    )

    assert [(c.control, c.target) for c in couplings] == expected_pairs


def _condition_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "coupling_fidelity": {"min": 0.8, "max": 1.0, "is_within_24h": True},
        "qubit_fidelity": {"min": 0.9, "max": 1.0, "is_within_24h": True},
        "readout_fidelity": {"min": 0.7, "max": 1.0, "is_within_24h": True},
        "only_maximum_connected": True,
    }
    payload.update(overrides)
    return payload


def test_condition_accepts_camel_case_cr_direction() -> None:
    condition = Condition.model_validate(_condition_payload(crDirection="forward"))

    assert condition.cr_direction == "forward"


def test_condition_rejects_unknown_direction_key() -> None:
    with pytest.raises(ValidationError):
        Condition.model_validate(_condition_payload(crDirectionTypo="forward"))


def test_condition_rejects_misspelled_forward_value() -> None:
    with pytest.raises(ValidationError):
        Condition.model_validate(_condition_payload(cr_direction="foward"))


def test_device_topology_request_rejects_top_level_cr_direction() -> None:
    with pytest.raises(ValidationError):
        DeviceTopologyRequest.model_validate({"cr_direction": "forward"})


def test_device_topology_request_accepts_condition_cr_direction() -> None:
    request = DeviceTopologyRequest.model_validate(
        {"condition": _condition_payload(cr_direction="forward")}
    )

    assert request.condition.cr_direction == "forward"
