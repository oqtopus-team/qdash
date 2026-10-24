"""Tests for the flow template and helper file catalog."""

from pathlib import Path

import pytest
from fastapi import HTTPException

from qdash.api.services.flow_service.templates import TemplateCatalog
from qdash.common.config.path_resolver import resolve_workflow_path

REPO_ROOT = Path(__file__).resolve().parents[5]
TEMPLATES_DIR = REPO_ROOT / "src/qdash/workflow/templates"


def test_resolve_workflow_path_uses_container_path_when_available(tmp_path: Path) -> None:
    """resolve_workflow_path returns the container path when it exists."""
    container_path = tmp_path / "templates"
    container_path.mkdir()

    assert resolve_workflow_path(container_path, "templates") == container_path


def test_resolve_workflow_path_falls_back_to_repo_local_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """resolve_workflow_path falls back to the repo-local templates directory."""
    monkeypatch.chdir(REPO_ROOT)

    resolved = resolve_workflow_path(Path("/missing/templates"), "templates")

    assert resolved == TEMPLATES_DIR


@pytest.mark.asyncio
async def test_list_templates_uses_resolved_templates_metadata() -> None:
    """list_templates returns templates loaded from the resolved templates metadata file."""
    templates = TemplateCatalog(templates_dir=TEMPLATES_DIR).list_templates()

    assert any(template.id == "full_calibration" for template in templates)


@pytest.mark.asyncio
@pytest.mark.parametrize("template_id", ["coarse_one", "fine_one"])
async def test_partial_one_qubit_template_is_listed_and_loads_its_flow_code(
    template_id: str,
) -> None:
    """Each partial one-qubit template is listed and exposes its flow source."""
    catalog = TemplateCatalog(templates_dir=TEMPLATES_DIR)

    templates = catalog.list_templates()
    assert any(template.id == template_id for template in templates)

    template = catalog.get_template(template_id)
    assert template.function_name == template_id
    assert template.code == (TEMPLATES_DIR / f"{template_id}.py").read_text(encoding="utf-8")


def test_list_templates_is_empty_without_a_metadata_file(tmp_path: Path) -> None:
    """A missing metadata file yields no templates instead of an error."""
    assert TemplateCatalog(templates_dir=tmp_path).list_templates() == []


def test_get_template_rejects_an_unknown_id(tmp_path: Path) -> None:
    """An unknown template id is reported as not found."""
    (tmp_path / "templates.json").write_text("[]", encoding="utf-8")

    with pytest.raises(HTTPException) as exc_info:
        TemplateCatalog(templates_dir=tmp_path).get_template("missing")

    assert exc_info.value.status_code == 404


def test_get_template_rejects_a_missing_metadata_file(tmp_path: Path) -> None:
    """A missing metadata file is reported as not found."""
    with pytest.raises(HTTPException) as exc_info:
        TemplateCatalog(templates_dir=tmp_path).get_template("full_calibration")

    assert exc_info.value.status_code == 404


def test_list_helper_files_lists_python_modules_with_the_init_first(tmp_path: Path) -> None:
    """Only public Python modules are listed, with __init__.py leading."""
    (tmp_path / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "helper.py").write_text("", encoding="utf-8")
    (tmp_path / "_private.py").write_text("", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("", encoding="utf-8")

    assert TemplateCatalog(helpers_dir=tmp_path).list_helper_files() == [
        "__init__.py",
        "helper.py",
    ]


def test_list_helper_files_is_empty_without_a_directory(tmp_path: Path) -> None:
    """A missing helper directory yields no files instead of an error."""
    assert TemplateCatalog(helpers_dir=tmp_path / "missing").list_helper_files() == []


def test_get_helper_file_returns_the_source(tmp_path: Path) -> None:
    """A helper module is returned verbatim."""
    (tmp_path / "helper.py").write_text("VALUE = 1\n", encoding="utf-8")

    assert TemplateCatalog(helpers_dir=tmp_path).get_helper_file("helper.py") == "VALUE = 1\n"


@pytest.mark.parametrize("filename", ["../secret.py", "nested/helper.py", "nested\\helper.py"])
def test_get_helper_file_rejects_traversal(tmp_path: Path, filename: str) -> None:
    """A helper path may not leave the helper directory."""
    with pytest.raises(HTTPException) as exc_info:
        TemplateCatalog(helpers_dir=tmp_path).get_helper_file(filename)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Invalid filename"


def test_get_helper_file_rejects_non_python_files(tmp_path: Path) -> None:
    """Only Python sources can be read."""
    with pytest.raises(HTTPException) as exc_info:
        TemplateCatalog(helpers_dir=tmp_path).get_helper_file("notes.txt")

    assert exc_info.value.status_code == 400


def test_get_helper_file_rejects_a_missing_module(tmp_path: Path) -> None:
    """An absent helper module is reported as not found."""
    with pytest.raises(HTTPException) as exc_info:
        TemplateCatalog(helpers_dir=tmp_path).get_helper_file("missing.py")

    assert exc_info.value.status_code == 404
