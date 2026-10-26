"""Tests for the flow template catalog."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

import pytest
from fastapi import HTTPException

from qdash.api.schemas.flow import FlowTemplate, FlowTemplateWithCode
from qdash.api.services.flow_service.templates import TemplateCatalog

if TYPE_CHECKING:
    from pathlib import Path

TEMPLATE = {
    "id": "daily",
    "name": "Daily calibration",
    "description": "A daily calibration",
    "category": "example",
    "filename": "daily.py",
    "function_name": "daily",
}


def _catalog(
    tmp_path: Path,
    *,
    templates_dir: Path | None = None,
    helpers_dir: Path | None = None,
    create_helpers: bool = True,
) -> tuple[TemplateCatalog, Path, Path]:
    templates = templates_dir or tmp_path / "templates"
    helpers = helpers_dir or tmp_path / "helpers"
    paths = (templates, helpers) if create_helpers else (templates,)
    for path in paths:
        if not path.exists():
            path.mkdir(parents=True)
    return TemplateCatalog(templates_dir=templates, helpers_dir=helpers), templates, helpers


def _write_index(templates_dir: Path, entries: list[dict[str, Any]]) -> None:
    (templates_dir / "templates.json").write_text(json.dumps(entries), encoding="utf-8")


class TestListTemplates:
    """list_templates() returns template metadata or an empty list without an index."""

    def test_missing_index_returns_empty(self, tmp_path: Path, caplog):
        catalog, _, _ = _catalog(tmp_path)

        with caplog.at_level(logging.ERROR):
            templates = catalog.list_templates()

        assert templates == []
        assert "Templates metadata file not found" in caplog.text

    def test_lists_every_indexed_template(self, tmp_path: Path):
        catalog, templates_dir, _ = _catalog(tmp_path)
        second = {**TEMPLATE, "id": "t1", "name": "T1", "filename": "t1.py", "function_name": "t1"}
        _write_index(templates_dir, [TEMPLATE, second])

        templates = catalog.list_templates()

        assert [template.id for template in templates] == ["daily", "t1"]
        assert all(isinstance(template, FlowTemplate) for template in templates)

    def test_invalid_json_raises_500(self, tmp_path: Path, caplog):
        catalog, templates_dir, _ = _catalog(tmp_path)
        (templates_dir / "templates.json").write_text("not json", encoding="utf-8")

        with caplog.at_level(logging.ERROR), pytest.raises(HTTPException) as exc_info:
            catalog.list_templates()

        assert exc_info.value.status_code == 500
        assert "Failed to list flow templates" in caplog.text

    def test_unreadable_index_raises_500(self, tmp_path: Path):
        catalog, templates_dir, _ = _catalog(tmp_path)
        (templates_dir / "templates.json").mkdir()

        with pytest.raises(HTTPException) as exc_info:
            catalog.list_templates()

        assert exc_info.value.status_code == 500

    def test_incomplete_entry_raises_500(self, tmp_path: Path):
        catalog, templates_dir, _ = _catalog(tmp_path)
        _write_index(templates_dir, [{"id": "daily", "filename": "daily.py"}])

        with pytest.raises(HTTPException) as exc_info:
            catalog.list_templates()

        assert exc_info.value.status_code == 500


class TestGetTemplate:
    """get_template() returns one template together with its flow source."""

    def test_missing_index_raises_404(self, tmp_path: Path):
        catalog, _, _ = _catalog(tmp_path)

        with pytest.raises(HTTPException) as exc_info:
            catalog.get_template("daily")

        assert exc_info.value.status_code == 404
        assert "Templates metadata file not found" in str(exc_info.value.detail)

    def test_unknown_template_raises_404(self, tmp_path: Path):
        catalog, templates_dir, _ = _catalog(tmp_path)
        _write_index(templates_dir, [TEMPLATE])

        with pytest.raises(HTTPException) as exc_info:
            catalog.get_template("t1")

        assert exc_info.value.status_code == 404
        assert "Template 't1' not found" in str(exc_info.value.detail)

    def test_missing_code_file_raises_404(self, tmp_path: Path, caplog):
        catalog, templates_dir, _ = _catalog(tmp_path)
        _write_index(templates_dir, [{**TEMPLATE, "filename": "missing.py"}])

        with caplog.at_level(logging.ERROR), pytest.raises(HTTPException) as exc_info:
            catalog.get_template("daily")

        assert exc_info.value.status_code == 404
        assert "Template file not found" in str(exc_info.value.detail)

    def test_returns_the_source(self, tmp_path: Path):
        catalog, templates_dir, _ = _catalog(tmp_path)
        _write_index(templates_dir, [TEMPLATE])
        (templates_dir / "daily.py").write_text("# flow\n", encoding="utf-8")

        template = catalog.get_template("daily")

        assert isinstance(template, FlowTemplateWithCode)
        assert template.id == "daily"
        assert template.code == "# flow\n"

    def test_incomplete_entry_raises_500(self, tmp_path: Path, caplog):
        catalog, templates_dir, _ = _catalog(tmp_path)
        _write_index(templates_dir, [{"id": "daily", "filename": "daily.py"}])
        (templates_dir / "daily.py").write_text("# flow\n", encoding="utf-8")

        with caplog.at_level(logging.ERROR), pytest.raises(HTTPException) as exc_info:
            catalog.get_template("daily")

        assert exc_info.value.status_code == 500
        assert "Failed to get flow template" in caplog.text


class TestListHelperFiles:
    """list_helper_files() returns the modules importable from a user flow."""

    def test_missing_helpers_dir_returns_empty(self, tmp_path: Path, caplog):
        catalog, _, _ = _catalog(tmp_path, helpers_dir=tmp_path / "absent", create_helpers=False)

        with caplog.at_level(logging.WARNING):
            files = catalog.list_helper_files()

        assert files == []
        assert "Flow helpers directory not found" in caplog.text

    def test_empty_helpers_dir_returns_empty(self, tmp_path: Path):
        catalog, _, _ = _catalog(tmp_path)

        assert catalog.list_helper_files() == []

    def test_lists_python_modules_with_init_first(self, tmp_path: Path):
        catalog, _, helpers_dir = _catalog(tmp_path)
        for name in ("util.py", "_internal.py", "constants.py", "notes.txt", "__init__.py"):
            (helpers_dir / name).write_text("# helper\n", encoding="utf-8")

        files = catalog.list_helper_files()

        assert files == ["__init__.py", "constants.py", "util.py"]

    def test_sorts_files_alphabetically(self, tmp_path: Path):
        catalog, _, helpers_dir = _catalog(tmp_path)
        for name in ("z.py", "a.py"):
            (helpers_dir / name).write_text("# helper\n", encoding="utf-8")

        assert catalog.list_helper_files() == ["a.py", "z.py"]

    def test_unlistable_helpers_dir_raises_500(self, tmp_path: Path, caplog):
        helpers_file = tmp_path / "helpers.py"
        helpers_file.write_text("# not a directory\n", encoding="utf-8")
        catalog, _, _ = _catalog(tmp_path, helpers_dir=helpers_file)

        with caplog.at_level(logging.ERROR), pytest.raises(HTTPException) as exc_info:
            catalog.list_helper_files()

        assert exc_info.value.status_code == 500
        assert "Failed to list flow helper files" in caplog.text

    def test_logs_the_listing(self, tmp_path: Path, caplog):
        """Listing helper files logs how many were found."""
        catalog, _, helpers_dir = _catalog(tmp_path)
        (helpers_dir / "util.py").write_text("# helper\n", encoding="utf-8")

        with caplog.at_level(logging.INFO, logger="uvicorn.app"):
            catalog.list_helper_files()

        assert "Listed 1 flow helper files" in caplog.text


class TestGetHelperFile:
    """get_helper_file() returns the source of one helper module."""

    @pytest.mark.parametrize("filename", ["../etc/passwd", "subdir/util.py", "a\\b.py"])
    def test_rejects_path_segments(self, tmp_path: Path, filename: str):
        catalog, _, _ = _catalog(tmp_path)

        with pytest.raises(HTTPException) as exc_info:
            catalog.get_helper_file(filename)

        assert exc_info.value.status_code == 400
        assert "Invalid filename" in str(exc_info.value.detail)

    def test_rejects_non_python_files(self, tmp_path: Path):
        catalog, _, _ = _catalog(tmp_path)

        with pytest.raises(HTTPException) as exc_info:
            catalog.get_helper_file("readme.md")

        assert exc_info.value.status_code == 400
        assert "Only Python files are allowed" in str(exc_info.value.detail)

    def test_missing_file_raises_404(self, tmp_path: Path):
        catalog, _, _ = _catalog(tmp_path)

        with pytest.raises(HTTPException) as exc_info:
            catalog.get_helper_file("missing.py")

        assert exc_info.value.status_code == 404
        assert "File not found" in str(exc_info.value.detail)

    def test_returns_the_source(self, tmp_path: Path, caplog):
        """Reading a helper file returns its source."""
        catalog, _, helpers_dir = _catalog(tmp_path)
        (helpers_dir / "util.py").write_text("def helper():\n    return 1\n", encoding="utf-8")

        with caplog.at_level(logging.INFO, logger="uvicorn.app"):
            content = catalog.get_helper_file("util.py")

        assert content == "def helper():\n    return 1\n"
        assert "Read flow helper file" in caplog.text

    def test_unreadable_file_raises_500(self, tmp_path: Path, caplog):
        catalog, _, helpers_dir = _catalog(tmp_path)
        (helpers_dir / "bad.py").mkdir()

        with caplog.at_level(logging.ERROR), pytest.raises(HTTPException) as exc_info:
            catalog.get_helper_file("bad.py")

        assert exc_info.value.status_code == 500
        assert "Failed to read flow helper file" in caplog.text


def test_metadata_file_points_at_the_index(tmp_path: Path):
    catalog, templates_dir, _ = _catalog(tmp_path)

    assert catalog.metadata_file == templates_dir / "templates.json"
