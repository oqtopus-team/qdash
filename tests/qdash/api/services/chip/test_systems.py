"""Listing a chip's Systems and adding one on another backend."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest

from qdash.api.schemas.chip import AddChipSystemRequest
from qdash.api.services.chip.system_files import ChipValues, validate_system_offline
from qdash.api.services.chip.systems import ChipSystemsError, ChipSystemsService
from qdash.common.config.qubex_layout import QubexLayout
from tests.qdash.api.services.chip._trees import (
    FakeRepository,
    load_yaml,
    quel3_rows,
    write_shared_tree,
)

if TYPE_CHECKING:
    from pathlib import Path

PROJECT = "test_project"


def _values(project_id: str, chip_id: str) -> ChipValues:
    return ChipValues(
        n_qubits=16,
        qubits={"Q09": {"qubit_frequency": {"value": 4.61, "unit": "GHz"}}},
    )


def _service(
    tmp_path: Path, repo: FakeRepository | None = None, **kwargs: Any
) -> ChipSystemsService:
    return ChipSystemsService(
        layout_factory=lambda: QubexLayout.detect(tmp_path),
        repository_factory=lambda layout, actor: repo or FakeRepository(),
        chip_values=_values,
        master_note=kwargs.pop(
            "master_note", lambda p, c: {"rabi_params": {"Q09": {"amplitude": 1}}}
        ),
        **kwargs,
    )


def test_list_systems_reports_backends_muxes_boxes_and_files(tmp_path: Path) -> None:
    write_shared_tree(tmp_path)

    response = _service(tmp_path).list_systems(chip_id="src16")

    assert response.layout == "shared" and response.provisionable
    assert [s.system_id for s in response.systems] == ["src16", "src16-quel3"]
    quel1, quel3 = response.systems
    assert (quel1.backend, quel1.mux_ids, quel1.box_ids, quel1.is_default) == (
        "quel1",
        [0, 1],
        ["BOXA"],
        True,
    )
    assert (quel3.backend, quel3.mux_ids, quel3.box_ids, quel3.is_default) == (
        "quel3",
        [2, 3],
        ["q3"],
        False,
    )
    assert quel1.has_params and quel1.has_calib_note
    assert quel1.driver == "qubex"
    assert quel1.settings["quel1"] == {"clock_master": "10.0.0.1"}


def test_list_systems_explains_an_unreadable_tree(tmp_path: Path) -> None:
    write_shared_tree(tmp_path)

    response = _service(tmp_path).list_systems(chip_id="unknown")

    assert response.systems == []
    assert response.message is not None and "unknown" in response.message


def test_add_system_moves_muxes_and_projects_values_and_the_master_note(tmp_path: Path) -> None:
    write_shared_tree(tmp_path, chip_id="c16", two_systems=False)
    repo = FakeRepository()
    service = _service(tmp_path, repo)

    response = service.add_system(
        project_id=PROJECT,
        username="alice",
        chip_id="c16",
        request=AddChipSystemRequest(
            backend="quel3",
            mux_ids=[2, 3],
            settings={"transport": "grpc", "endpoint": "10.0.0.9"},
            wiring=quel3_rows(2, 3),
        ),
    )

    assert response.system.system_id == "c16-quel3"
    assert response.system.mux_ids == [2, 3] and response.system.box_ids == ["q3"]
    assert response.system.is_default is False
    assert response.publish.status == "published"
    systems = load_yaml(tmp_path / "config" / "system.yaml")
    assert systems["c16-quel3"] == {
        "chip_id": "c16",
        "backend": "quel3",
        "quel3": {"transport": "grpc", "endpoint": "10.0.0.9"},
    }
    assert systems["c16"]["quel1"] == {"clock_master": "10.0.0.1"}
    wiring = load_yaml(tmp_path / "config" / "wiring.yaml")
    assert [row["mux"] for row in wiring["c16"]] == [0, 1]
    assert [row["mux"] for row in wiring["c16-quel3"]] == [2, 3]
    assert wiring["c16-quel3"][0]["read_out"] == "q3:1"

    layout = QubexLayout.detect(tmp_path)
    for system_id in ("c16", "c16-quel3"):
        validate_system_offline(layout, system_id)
    params = layout.params_dir("c16-quel3")
    assert load_yaml(params / "capture_delay.yaml") == {
        "meta": {"description": "Capture Delay", "unit": "ns", "default": 700},
        "data": {2: 700, 3: 700},
    }
    assert load_yaml(params / "qubit_frequency.yaml")["data"]["Q09"] == 4.61
    assert not (params / "control_vatt.yaml").exists()
    assert json.loads(layout.calib_note_path("c16-quel3").read_text()) == {
        "rabi_params": {"Q09": {"amplitude": 1}}
    }
    # The existing System's directory is not touched.
    assert sorted(p.name for p in layout.params_dir("c16").iterdir()) == ["capture_delay.yaml"]
    assert repo.upserts[0][0].keys() == {"system.yaml", "wiring.yaml"}
    assert all(
        "/params/c16-quel3/" in p or "/calibration/c16-quel3/" in p for p in repo.published[0][0]
    )


def test_add_system_keeps_rows_when_no_wiring_is_given(tmp_path: Path) -> None:
    write_shared_tree(tmp_path, chip_id="c16", two_systems=False)
    service = _service(tmp_path, validate=lambda layout, entries, systems: None)

    response = service.add_system(
        project_id=PROJECT,
        username="alice",
        chip_id="c16",
        request=AddChipSystemRequest(backend="quel3", mux_ids=[3]),
    )

    assert response.system.box_ids == ["BOXA"]
    wiring = load_yaml(tmp_path / "config" / "wiring.yaml")
    assert [row["mux"] for row in wiring["c16"]] == [0, 1, 2]
    assert wiring["c16-quel3"][0]["ctrl"] == ["BOXA-5", "BOXA-6", "BOXA-7", "BOXA-8"]


def test_add_system_refuses_rows_the_new_backend_cannot_drive(tmp_path: Path) -> None:
    """QuEL-1 wiring rows moved under a QuEL-3 System fail qubex's offline load."""
    write_shared_tree(tmp_path, chip_id="c16", two_systems=False)
    before = (tmp_path / "config" / "wiring.yaml").read_bytes()

    with pytest.raises(ValueError, match="c16-quel3"):
        _service(tmp_path).add_system(
            project_id=PROJECT,
            username="alice",
            chip_id="c16",
            request=AddChipSystemRequest(backend="quel3", mux_ids=[3]),
        )

    assert (tmp_path / "config" / "wiring.yaml").read_bytes() == before
    assert not (tmp_path / "params" / "c16-quel3").exists()


@pytest.mark.parametrize(
    ("request_kwargs", "match"),
    [
        ({"backend": "quel3", "mux_ids": [9]}, "not wired"),
        ({"backend": "quel1", "mux_ids": [1]}, "already has a quel1 System"),
        ({"backend": "quel3", "mux_ids": [2], "wiring": quel3_rows(2, box="ghost")}, "ghost"),
        ({"backend": "quel3", "mux_ids": [2, 3], "wiring": quel3_rows(2)}, "must match"),
    ],
)
def test_add_system_refuses_bad_requests_before_writing(
    tmp_path: Path, request_kwargs: dict[str, Any], match: str
) -> None:
    write_shared_tree(tmp_path, chip_id="c16", two_systems=False)
    before = (tmp_path / "config" / "wiring.yaml").read_bytes()

    with pytest.raises(ChipSystemsError, match=match):
        _service(tmp_path).add_system(
            project_id=PROJECT,
            username="alice",
            chip_id="c16",
            request=AddChipSystemRequest(**request_kwargs),
        )

    assert (tmp_path / "config" / "wiring.yaml").read_bytes() == before
    assert not (tmp_path / "params" / "c16-quel3").exists()


def test_add_system_requires_the_shared_layout_and_an_explicit_system(tmp_path: Path) -> None:
    (tmp_path / "c16" / "config").mkdir(parents=True)
    with pytest.raises(ChipSystemsError, match="shared"):
        _service(tmp_path).add_system(
            project_id=PROJECT,
            username="alice",
            chip_id="c16",
            request=AddChipSystemRequest(backend="quel3", mux_ids=[0]),
        )

    shared = tmp_path / "shared"
    write_shared_tree(shared, chip_id="c16", two_systems=False)
    (shared / "config" / "system.yaml").unlink()
    with pytest.raises(ChipSystemsError, match=r"system\.yaml"):
        _service(shared).add_system(
            project_id=PROJECT,
            username="alice",
            chip_id="c16",
            request=AddChipSystemRequest(backend="quel3", mux_ids=[0]),
        )
