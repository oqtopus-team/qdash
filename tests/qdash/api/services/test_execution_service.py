from types import SimpleNamespace
from unittest.mock import MagicMock

from qdash.api.services.execution_service import ExecutionService


def test_get_lock_status_includes_latest_execution_metadata() -> None:
    history_repository = MagicMock()
    history_repository.find_latest_by_project.return_value = SimpleNamespace(
        execution_id="exec-running",
        chip_id="chip-1",
        name="quick-run:CheckChevron",
        status="running",
    )
    lock_repository = MagicMock()
    lock_repository.get_lock_status.return_value = True
    service = ExecutionService(history_repository, lock_repository)

    result = service.get_lock_status("project-1")

    assert result.model_dump() == {
        "lock": True,
        "execution_id": "exec-running",
        "chip_id": "chip-1",
        "name": "quick-run:CheckChevron",
        "status": "running",
    }
    history_repository.find_latest_by_project.assert_called_once_with("project-1")


def test_get_lock_status_without_execution_returns_lock_only() -> None:
    history_repository = MagicMock()
    history_repository.find_latest_by_project.return_value = None
    lock_repository = MagicMock()
    lock_repository.get_lock_status.return_value = False
    service = ExecutionService(history_repository, lock_repository)

    result = service.get_lock_status("project-1")

    assert result.lock is False
    assert result.execution_id is None
