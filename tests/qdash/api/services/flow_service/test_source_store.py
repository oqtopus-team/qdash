"""Tests for project-scoped flow file storage."""

from pathlib import Path

import pytest
from fastapi import HTTPException

from qdash.api.services.flow_service.source_store import FlowSourceStore


def test_path_for_sanitizes_the_project_and_creates_its_directory(tmp_path: Path) -> None:
    """A project id with unsupported characters maps to a safe directory."""
    store = FlowSourceStore(tmp_path)

    path = store.path_for("project/1", "my_flow")

    assert path == tmp_path / "project_1" / "my_flow.py"
    assert path.parent.is_dir()


def test_write_and_read_round_trip_the_source(tmp_path: Path) -> None:
    """Saved source is returned unchanged."""
    store = FlowSourceStore(tmp_path)
    path = store.path_for("project-1", "my_flow")

    store.write(path, "print('hello')\n")

    assert store.exists(path)
    assert store.read(path) == "print('hello')\n"


def test_write_failure_is_reported_as_a_server_error(tmp_path: Path) -> None:
    """A write that cannot complete raises the save error."""
    store = FlowSourceStore(tmp_path)

    with pytest.raises(HTTPException) as exc_info:
        store.write(tmp_path, "print('hello')\n")

    assert exc_info.value.status_code == 500
    assert str(exc_info.value.detail).startswith("Failed to save flow file:")


def test_read_failure_is_reported_as_a_server_error(tmp_path: Path) -> None:
    """A missing file raises the read error."""
    store = FlowSourceStore(tmp_path)

    with pytest.raises(HTTPException) as exc_info:
        store.read(tmp_path / "missing.py")

    assert exc_info.value.status_code == 500
    assert str(exc_info.value.detail).startswith("Failed to read flow file:")


def test_delete_removes_the_file(tmp_path: Path) -> None:
    """Deleting a flow file removes it from disk."""
    store = FlowSourceStore(tmp_path)
    path = store.path_for("project-1", "my_flow")
    store.write(path, "print('hello')\n")

    store.delete(path)

    assert not path.exists()


def test_delete_failure_is_reported_as_a_server_error(tmp_path: Path) -> None:
    """Deleting a file that is gone raises the delete error."""
    store = FlowSourceStore(tmp_path)

    with pytest.raises(HTTPException) as exc_info:
        store.delete(tmp_path / "missing.py")

    assert exc_info.value.status_code == 500
    assert str(exc_info.value.detail).startswith("Failed to delete flow file:")


def test_to_deployment_path_maps_host_user_flow_path(tmp_path: Path) -> None:
    """A host path inside the user flow tree maps to its container path."""
    host_user_flows = tmp_path / "src/qdash/workflow/user_flows"
    store = FlowSourceStore(host_user_flows)
    flow_path = host_user_flows / "project-1" / "myflow.py"

    assert store.to_deployment_path(flow_path) == Path(
        "/app/qdash/workflow/user_flows/project-1/myflow.py"
    )


def test_to_deployment_path_leaves_unrelated_path_unchanged(tmp_path: Path) -> None:
    """A path outside the user flow tree is passed through."""
    store = FlowSourceStore(tmp_path / "user_flows")

    assert store.to_deployment_path(Path("/tmp/myflow.py")) == Path("/tmp/myflow.py")
