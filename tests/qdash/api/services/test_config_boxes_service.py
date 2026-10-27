"""The shared box catalog lists and upserts box.yaml entries."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from qdash.api.schemas.config_boxes import ConfigBox
from qdash.api.services.config_boxes_service import ConfigBoxesError, ConfigBoxesService
from qdash.common.config.qubex_layout import QubexLayout
from tests.qdash.api.services.chip._trees import FakeRepository, load_yaml, write_shared_tree

if TYPE_CHECKING:
    from pathlib import Path


def _service(root: Path, repo: FakeRepository | None = None) -> ConfigBoxesService:
    return ConfigBoxesService(
        layout_factory=lambda: QubexLayout.detect(root),
        repository_factory=lambda layout, actor: repo or FakeRepository(),
    )


def test_list_boxes_reads_the_shared_catalog_and_names_the_types(tmp_path: Path) -> None:
    write_shared_tree(tmp_path)

    response = _service(tmp_path).list_boxes()

    assert response.layout == "shared" and response.editable
    assert [box.box_id for box in response.boxes] == ["BOXA", "q3"]
    assert response.boxes[0].address == "10.1.0.1"
    assert response.boxes[1].address is None
    assert {"quel3", "quel1se-riken8"} <= set(response.box_types)


def test_upsert_box_keeps_other_entries_and_comments(tmp_path: Path) -> None:
    write_shared_tree(tmp_path)
    repo = FakeRepository()

    created = _service(tmp_path, repo).upsert_box(
        username="admin",
        box=ConfigBox(box_id="q4", name="quel3 #4", type="quel3", extra={"rack": "B"}),
    )
    updated = _service(tmp_path, repo).upsert_box(
        username="admin",
        box=ConfigBox(
            box_id="BOXA", name="box a", type="quel1se-riken8", address="10.1.0.2", adapter="X"
        ),
    )

    assert created.created and created.box.extra == {"rack": "B"}
    assert not updated.created
    text = (tmp_path / "config" / "box.yaml").read_text()
    assert text.startswith("# boxes")
    catalog = load_yaml(tmp_path / "config" / "box.yaml")
    assert catalog["q4"] == {"name": "quel3 #4", "type": "quel3", "rack": "B"}
    assert catalog["BOXA"]["address"] == "10.1.0.2"
    assert catalog["q3"] == {"name": "q3", "type": "quel3"}
    assert [u[0].keys() for u in repo.upserts] == [{"box.yaml"}, {"box.yaml"}]
    assert created.publish.status == "recorded"


@pytest.mark.parametrize(
    ("box", "match"),
    [
        (ConfigBox(box_id="x", name="x", type="not-a-type"), "Unknown box type"),
        (ConfigBox(box_id="x", name="x", type="quel1-a"), "address and adapter"),
    ],
)
def test_upsert_box_validates_type_and_required_fields(
    tmp_path: Path, box: ConfigBox, match: str
) -> None:
    write_shared_tree(tmp_path)

    with pytest.raises(ConfigBoxesError, match=match):
        _service(tmp_path).upsert_box(username="admin", box=box)


def test_legacy_layout_is_read_only_and_needs_a_chip(tmp_path: Path) -> None:
    (tmp_path / "64Qv3" / "config").mkdir(parents=True)
    (tmp_path / "64Qv3" / "config" / "box.yaml").write_text("B:\n  name: b\n  type: quel3\n")
    service = _service(tmp_path)

    assert service.list_boxes().message is not None
    assert [box.box_id for box in service.list_boxes(chip_id="64Qv3").boxes] == ["B"]
    assert not service.list_boxes(chip_id="64Qv3").editable
    with pytest.raises(ConfigBoxesError, match="shared"):
        service.upsert_box(username="admin", box=ConfigBox(box_id="x", name="x", type="quel3"))
