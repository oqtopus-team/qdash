"""Tests for the host-side system updater."""

from collections.abc import Sequence
from pathlib import Path

import pytest

from qdash.updater.models import UpdateState
from qdash.updater.service import (
    CommandResult,
    UpdateBlockedError,
    UpdaterService,
    UpdaterSettings,
)


class FakeCommandRunner:
    """Small stateful Git/Compose fake for updater orchestration tests."""

    def __init__(self, *, dirty: bool = False) -> None:
        self.current_tag = "v1.0.0"
        self.current_commit = "a" * 40
        self.dirty = dirty
        self.commands: list[tuple[str, ...]] = []

    def run(self, args: Sequence[str], *, timeout: int) -> CommandResult:
        del timeout
        command = tuple(args)
        self.commands.append(command)
        if command == ("git", "rev-parse", "HEAD"):
            return CommandResult(self.current_commit, "")
        if command == ("git", "tag", "--points-at", "HEAD"):
            return CommandResult(self.current_tag, "")
        if command == ("git", "status", "--porcelain", "--untracked-files=no"):
            return CommandResult(" M compose.yaml" if self.dirty else "", "")
        if command == ("git", "fetch", "origin", "--tags", "--prune"):
            return CommandResult("", "")
        if command == ("git", "tag", "--list", "v*"):
            return CommandResult("v1.0.0\nv1.1.0\nv1.1.0-beta.1", "")
        if command == ("git", "show", "v1.1.0:update-manifest.json"):
            return CommandResult(
                '{"schema_version":1,"automatic_update":true,"migration_mode":"compose"}',
                "",
            )
        if command == ("git", "checkout", "--detach", "v1.1.0"):
            self.current_tag = "v1.1.0"
            self.current_commit = "b" * 40
            return CommandResult("", "")
        if command[:2] == ("docker", "compose"):
            return CommandResult("compose ok", "")
        raise AssertionError(f"Unexpected command: {command}")


def make_service(tmp_path: Path, runner: FakeCommandRunner) -> UpdaterService:
    repository = tmp_path / "repo"
    (repository / ".git").mkdir(parents=True)
    return UpdaterService(
        UpdaterSettings(
            repository_path=repository,
            state_path=tmp_path / "state.json",
            health_timeout_seconds=1,
        ),
        runner=runner,
    )


@pytest.mark.asyncio
async def test_status_selects_latest_stable_manifest_release(tmp_path: Path) -> None:
    service = make_service(tmp_path, FakeCommandRunner())

    status = await service.get_status()

    assert status.current_version == "v1.0.0"
    assert status.latest_version == "v1.1.0"
    assert status.update_available is True
    assert status.can_update is True
    assert status.blocked_reason is None


@pytest.mark.asyncio
async def test_status_blocks_dirty_worktree(tmp_path: Path) -> None:
    service = make_service(tmp_path, FakeCommandRunner(dirty=True))

    status = await service.get_status()

    assert status.can_update is False
    assert status.dirty is True
    assert status.blocked_reason == "The QDash working tree has tracked changes"


@pytest.mark.asyncio
async def test_update_stops_checks_out_deploys_and_persists_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = FakeCommandRunner()
    service = make_service(tmp_path, runner)
    monkeypatch.setattr(service, "_wait_for_health", lambda: None)

    operation = await service.start_update("v1.0.0")
    await next(iter(service._background_tasks))

    completed = service.get_operation(operation.operation_id)
    assert completed is not None
    assert completed.state == UpdateState.SUCCEEDED
    assert completed.progress == 100
    assert (
        "docker",
        "compose",
        "stop",
        "api",
        "ui",
        "deployment-service",
        "user-flow-worker",
    ) in runner.commands
    assert ("git", "checkout", "--detach", "v1.1.0") in runner.commands
    assert ("docker", "compose", "up", "-d", "--build") in runner.commands
    assert service.settings.state_path.exists()


@pytest.mark.asyncio
async def test_update_rejects_stale_current_version(tmp_path: Path) -> None:
    service = make_service(tmp_path, FakeCommandRunner())

    with pytest.raises(UpdateBlockedError, match="Current version changed"):
        await service.start_update("v0.9.0")
