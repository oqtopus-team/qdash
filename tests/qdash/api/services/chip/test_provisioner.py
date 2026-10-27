"""Chip provisioning writes a loadable Qubex configuration next to the database records."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest
import yaml

from qdash.api.schemas.chip import CreateChipRequest
from qdash.api.services.chip.provisioner import ChipProvisioningError, ChipProvisioningService
from qdash.api.services.chip.system_files import ChipValues, validate_system_offline
from qdash.common.config.qubex_layout import LayoutKind, QubexLayout
from qdash.common.config.system_catalog import SystemCatalog
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.qubit import QubitDocument
from qdash.dbmodel.user import UserDocument
from tests.qdash.api.services.chip._trees import FakeRepository, load_yaml, write_shared_tree

if TYPE_CHECKING:
    from pathlib import Path

PROJECT = "test_project"
USER = "test_user"


@pytest.fixture
def user(init_db: Any) -> UserDocument:
    doc = UserDocument(
        username=USER,
        hashed_password="x",
        access_token="t",
        default_project_id=PROJECT,
        system_info=SystemInfoModel(),
    )
    doc.insert()
    return doc


def _source_values(project_id: str, chip_id: str) -> ChipValues:
    assert (project_id, chip_id) == (PROJECT, "src16")
    return ChipValues(
        n_qubits=16,
        qubits={
            "Q01": {
                "qubit_frequency": {"value": 4.55, "unit": "GHz"},
                "t1": {"value": 20.0, "unit": "ns"},  # unit differs from the template: skipped
                "control_amplitude": {"value": 0.03, "unit": "a.u."},
            }
        },
    )


def _service(tmp_path: Path, repo: FakeRepository, **kwargs: Any) -> ChipProvisioningService:
    return ChipProvisioningService(
        layout_factory=lambda: QubexLayout.detect(tmp_path),
        repository_factory=lambda layout, actor: repo,
        chip_values=kwargs.pop("chip_values", _source_values),
        cooldown_assign=kwargs.pop("cooldown_assign", None),
        previous_chip=kwargs.pop("previous_chip", lambda project_id, cooldown_id: None),
        **kwargs,
    )


def test_inherits_both_systems_and_every_file_loads_with_qubex(tmp_path: Path, user: Any) -> None:
    write_shared_tree(tmp_path)
    repo = FakeRepository()
    service = _service(tmp_path, repo)

    response = service.create_chip(
        project_id=PROJECT,
        username=USER,
        request=CreateChipRequest(
            chip_id="new16",
            size=16,
            topology_id="square-lattice-mux-16",
            inherit_wiring_from="src16",
        ),
    )

    assert response.chip_id == "new16"
    assert response.provisioning is not None
    result = response.provisioning
    assert result.provisioned and result.layout == "shared"
    assert result.system_ids == ["new16", "new16-quel3"]
    assert result.inherited_from == "src16"
    assert result.publish.status == "published" and result.publish.commit == "abc123"

    chips = load_yaml(tmp_path / "config" / "chip.yaml")
    assert chips["new16"]["n_qubits"] == 16
    assert chips["new16"]["topology"]["mux_size"] == 4
    assert "src16" in chips  # the inherited chip is untouched
    systems = load_yaml(tmp_path / "config" / "system.yaml")
    assert systems["new16"] == {
        "chip_id": "new16",
        "backend": "quel1",
        "quel1": {"clock_master": "10.0.0.1"},
    }
    assert systems["new16-quel3"]["backend"] == "quel3"
    wiring = load_yaml(tmp_path / "config" / "wiring.yaml")
    assert [row["mux"] for row in wiring["new16"]] == [0, 1]
    assert [row["mux"] for row in wiring["new16-quel3"]] == [2, 3]
    assert (tmp_path / "config" / "box.yaml").read_text().startswith("# boxes")

    layout = QubexLayout.detect(tmp_path)
    for system_id in ("new16", "new16-quel3"):
        validate_system_offline(layout, system_id)
        assert json.loads(layout.calib_note_path(system_id).read_text()) == {}
    quel1 = load_yaml(layout.params_dir("new16") / "capture_delay.yaml")
    quel3 = load_yaml(layout.params_dir("new16-quel3") / "capture_delay.yaml")
    assert (quel1["meta"]["unit"], quel1["data"]) == ("ndelay", {0: 8, 1: 8})
    assert (quel3["meta"]["unit"], quel3["data"]) == ("ns", {2: 700, 3: 700})
    assert not (layout.params_dir("new16-quel3") / "control_vatt.yaml").exists()
    assert (layout.params_dir("new16") / "control_vatt.yaml").exists()

    # Physics values come from the source chip where the unit matches; both Systems get them.
    for system_id in ("new16", "new16-quel3"):
        freq = load_yaml(layout.params_dir(system_id) / "qubit_frequency.yaml")["data"]
        assert freq["Q01"] == 4.55 and freq["Q00"] == 4.2
        t1 = load_yaml(layout.params_dir(system_id) / "t1.yaml")["data"]
        assert "Q01" not in t1

    catalog = SystemCatalog(layout, "new16")
    assert catalog.system_ids() == ["new16", "new16-quel3"]
    assert catalog.resolve(["1", "9"]) == {"new16": ["1"], "new16-quel3": ["9"]}

    assert ChipDocument.find_one({"project_id": PROJECT, "chip_id": "new16"}).run() is not None
    assert QubitDocument.find({"project_id": PROJECT, "chip_id": "new16"}).count() == 16
    assert repo.upserts[0][0].keys() == {"chip.yaml", "system.yaml", "wiring.yaml"}
    owned = repo.published[0][0]
    assert all("/params/" in path or "/calibration/" in path for path in owned)
    assert all("/config/" not in path for path in owned)


def test_without_a_source_chip_a_single_empty_system_is_created(tmp_path: Path, user: Any) -> None:
    write_shared_tree(tmp_path)
    service = _service(tmp_path, FakeRepository(), chip_values=lambda p, c: ChipValues(n_qubits=16))

    response = service.create_chip(
        project_id=PROJECT,
        username=USER,
        request=CreateChipRequest(
            chip_id="fresh", size=16, topology_id="square-lattice-mux-16", backend="quel3"
        ),
    )

    result = response.provisioning
    assert result is not None and result.system_ids == ["fresh"]
    assert result.inherited_from is None
    assert any("No chip to inherit" in warning for warning in result.warnings)
    assert not any("qubex-config.json" in warning for warning in result.warnings)
    systems = load_yaml(tmp_path / "config" / "system.yaml")
    assert systems["fresh"] == {"chip_id": "fresh", "backend": "quel3", "quel3": {}}
    assert load_yaml(tmp_path / "config" / "wiring.yaml")["fresh"] == []
    layout = QubexLayout.detect(tmp_path)
    assert load_yaml(layout.params_dir("fresh") / "capture_delay.yaml")["meta"]["unit"] == "ns"


def test_previous_chip_on_the_cryostat_is_the_default_source(tmp_path: Path, user: Any) -> None:
    write_shared_tree(tmp_path)
    assigned: list[tuple[str, str, str]] = []
    service = _service(
        tmp_path,
        FakeRepository(),
        previous_chip=lambda project_id, cooldown_id: (
            "src16" if cooldown_id == "2026-002" else None
        ),
        cooldown_assign=lambda *args: assigned.append(args),
    )

    response = service.create_chip(
        project_id=PROJECT,
        username=USER,
        request=CreateChipRequest(
            chip_id="next16", size=16, topology_id="square-lattice-mux-16", cooldown_id="2026-002"
        ),
    )

    assert response.provisioning is not None
    assert response.provisioning.inherited_from == "src16"
    assert response.current_cooldown_id == "2026-002"
    assert assigned == [(PROJECT, "2026-002", "next16")]


def test_publish_failure_keeps_files_and_records(tmp_path: Path, user: Any) -> None:
    write_shared_tree(tmp_path)
    service = _service(tmp_path, FakeRepository(fail=True))

    response = service.create_chip(
        project_id=PROJECT,
        username=USER,
        request=CreateChipRequest(
            chip_id="new16",
            size=16,
            topology_id="square-lattice-mux-16",
            inherit_wiring_from="src16",
        ),
    )

    assert response.provisioning is not None
    assert response.provisioning.publish.status == "failed"
    assert "remote rejected" in (response.provisioning.publish.message or "")
    assert "new16" in load_yaml(tmp_path / "config" / "chip.yaml")
    assert (tmp_path / "params" / "new16" / "qubit_frequency.yaml").exists()
    assert ChipDocument.find_one({"project_id": PROJECT, "chip_id": "new16"}).run() is not None


def test_database_failure_rolls_the_files_back(tmp_path: Path, user: Any) -> None:
    write_shared_tree(tmp_path)
    before = {path: path.read_bytes() for path in (tmp_path / "config").glob("*.yaml")}
    service = _service(tmp_path, FakeRepository())
    ChipDocument(
        project_id=PROJECT, username=USER, chip_id="new16", size=16, system_info=SystemInfoModel()
    ).insert()

    with pytest.raises(ValueError, match="already exists"):
        service.create_chip(
            project_id=PROJECT,
            username=USER,
            request=CreateChipRequest(
                chip_id="new16",
                size=16,
                topology_id="square-lattice-mux-16",
                inherit_wiring_from="src16",
            ),
        )

    assert {path: path.read_bytes() for path in (tmp_path / "config").glob("*.yaml")} == before
    assert not (tmp_path / "params" / "new16").exists()
    assert not (tmp_path / "calibration" / "new16").exists()


def test_invalid_generated_configuration_writes_nothing(tmp_path: Path, user: Any) -> None:
    write_shared_tree(tmp_path)
    (tmp_path / "config" / "box.yaml").write_text(
        "BOXA:\n  name: a\n  type: quel1se-riken8\n  address: x\n  adapter: y\n"
    )
    service = _service(tmp_path, FakeRepository())

    with pytest.raises(ValueError, match="q3"):
        service.create_chip(
            project_id=PROJECT,
            username=USER,
            request=CreateChipRequest(
                chip_id="new16",
                size=16,
                topology_id="square-lattice-mux-16",
                inherit_wiring_from="src16",
            ),
        )

    assert "new16" not in load_yaml(tmp_path / "config" / "chip.yaml")
    assert not (tmp_path / "params" / "new16").exists()
    assert ChipDocument.find_one({"project_id": PROJECT, "chip_id": "new16"}).run() is None


def test_legacy_layout_refuses_provisioning_and_creates_records_by_default(
    tmp_path: Path, user: Any
) -> None:
    (tmp_path / "64Qv3" / "config").mkdir(parents=True)
    service = _service(tmp_path, FakeRepository())
    assert QubexLayout.detect(tmp_path).kind is LayoutKind.LEGACY

    with pytest.raises(ChipProvisioningError, match="shared layout"):
        service.create_chip(
            project_id=PROJECT,
            username=USER,
            request=CreateChipRequest(chip_id="legacy16", size=16, provision_config=True),
        )

    response = service.create_chip(
        project_id=PROJECT,
        username=USER,
        request=CreateChipRequest(chip_id="legacy16", size=16),
    )
    assert response.provisioning is None
    assert ChipDocument.find_one({"project_id": PROJECT, "chip_id": "legacy16"}).run() is not None


def test_request_shape_is_validated_before_anything_is_written(tmp_path: Path, user: Any) -> None:
    write_shared_tree(tmp_path)
    service = _service(tmp_path, FakeRepository())

    with pytest.raises(ChipProvisioningError, match="inherit its wiring from itself"):
        service.create_chip(
            project_id=PROJECT,
            username=USER,
            request=CreateChipRequest(chip_id="src16", size=16, inherit_wiring_from="src16"),
        )
    with pytest.raises(ValueError, match="does not match"):
        service.create_chip(
            project_id=PROJECT,
            username=USER,
            request=CreateChipRequest(
                chip_id="new16", size=64, topology_id="square-lattice-mux-16"
            ),
        )
    with pytest.raises(ValueError):
        CreateChipRequest(chip_id="../evil", size=16)
    assert not (tmp_path / "params" / "new16").exists()
    assert yaml.safe_load((tmp_path / "config" / "chip.yaml").read_text()).keys() == {"src16"}


def test_repository_without_a_manifest_gets_a_warning(tmp_path: Path, user: Any) -> None:
    write_shared_tree(tmp_path, manifest=False)
    service = _service(tmp_path, FakeRepository(), chip_values=lambda p, c: ChipValues(n_qubits=16))

    response = service.create_chip(
        project_id=PROJECT,
        username=USER,
        request=CreateChipRequest(
            chip_id="fresh", size=16, topology_id="square-lattice-mux-16", backend="quel3"
        ),
    )

    result = response.provisioning
    assert result is not None and result.provisioned is True
    assert any('"layout_version": "2.0"' in warning for warning in result.warnings)
    assert not (tmp_path / "qubex-config.json").exists()
