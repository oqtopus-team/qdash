"""Tests for project-scoped flow file storage."""

from pathlib import Path

import pytest

from qdash.api.lib.errors import OperationFailedError
from qdash.api.services.flow_service.source_store import FlowSourceStore


def _assert_safe_failure(error: OperationFailedError, code: str, message: str) -> None:
    """The error names the operation, carries an ID, and leaks no exception text."""
    assert error.status_code == 500
    assert error.code == code
    assert error.detail == message
    assert len(error.error_id) == 32


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

    with pytest.raises(OperationFailedError) as exc_info:
        store.write(tmp_path, "print('hello')\n")

    _assert_safe_failure(exc_info.value, "flow_source_write_failed", "Failed to save the flow file")
    assert isinstance(exc_info.value.__cause__, OSError)


def test_read_failure_is_reported_as_a_server_error(tmp_path: Path) -> None:
    """A missing file raises the read error."""
    store = FlowSourceStore(tmp_path)

    with pytest.raises(OperationFailedError) as exc_info:
        store.read(tmp_path / "missing.py")

    _assert_safe_failure(exc_info.value, "flow_source_read_failed", "Failed to read the flow file")
    assert isinstance(exc_info.value.__cause__, FileNotFoundError)


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

    with pytest.raises(OperationFailedError) as exc_info:
        store.delete(tmp_path / "missing.py")

    _assert_safe_failure(
        exc_info.value, "flow_source_delete_failed", "Failed to delete the flow file"
    )
    assert isinstance(exc_info.value.__cause__, FileNotFoundError)


def test_create_failure_is_reported_as_a_save_error(tmp_path: Path) -> None:
    """A create into a missing directory raises the save error; an existing file does not."""
    store = FlowSourceStore(tmp_path)

    with pytest.raises(OperationFailedError) as exc_info:
        store.create(tmp_path / "missing" / "flow.py", "print('hello')\n")

    _assert_safe_failure(exc_info.value, "flow_source_write_failed", "Failed to save the flow file")
    existing = tmp_path / "flow.py"
    existing.write_text("# keep\n", encoding="utf-8")
    with pytest.raises(FileExistsError):
        store.create(existing, "print('hello')\n")


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


def test_base_dir_returns_configured_root(tmp_path: Path) -> None:
    store = FlowSourceStore(tmp_path)
    assert store.base_dir == tmp_path


def test_exists_reports_presence(tmp_path: Path) -> None:
    store = FlowSourceStore(tmp_path)
    path = tmp_path / "missing.py"
    assert store.exists(path) is False
    path.write_text("# ok\n", encoding="utf-8")
    assert store.exists(path) is True
