"""Tests for the host-side system updater."""

from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

import pytest

from qdash.updater.models import UpdateOperation, UpdateState
from qdash.updater.service import (
    CommandResult,
    UpdateBlockedError,
    UpdaterService,
    UpdaterSettings,
)


class FakeCommandRunner:
    """Small stateful Git/Compose fake for updater orchestration tests."""

    def __init__(self, *, dirty: bool = False, branch: str = "main") -> None:
        self.current_tag = "v1.0.0"
        self.current_commit = "a" * 40
        self.dirty = dirty
        self.branch = branch
        self.commands: list[tuple[str, ...]] = []
        self.command_timeouts: list[tuple[tuple[str, ...], int]] = []

    def run(self, args: Sequence[str], *, timeout: int) -> CommandResult:
        command = tuple(args)
        self.commands.append(command)
        self.command_timeouts.append((command, timeout))
        if command == ("git", "rev-parse", "HEAD"):
            return CommandResult(self.current_commit, "")
        if command == ("git", "tag", "--points-at", "HEAD"):
            return CommandResult(self.current_tag, "")
        if command == ("git", "symbolic-ref", "--short", "HEAD"):
            return CommandResult(self.branch, "")
        if command == ("git", "status", "--porcelain", "--untracked-files=no"):
            return CommandResult(" M compose.yaml" if self.dirty else "", "")
        if command == ("git", "fetch", "origin", "--tags", "--prune"):
            return CommandResult("", "")
        if command == ("git", "tag", "--merged", "origin/main", "--list", "v*"):
            return CommandResult("v1.0.0\nv1.1.0\nv1.1.0-beta.1", "")
        if command == ("git", "show", "v1.1.0:update-manifest.json"):
            return CommandResult(
                '{"schema_version":1,"automatic_update":true,"migration_mode":"compose"}',
                "",
            )
        if command == ("git", "merge", "--ff-only", "v1.1.0"):
            self.current_tag = "v1.1.0"
            self.current_commit = "b" * 40
            return CommandResult("", "")
        if command[:3] == ("git", "reset", "--hard"):
            self.current_commit = command[3]
            self.current_tag = "v1.0.0"
            return CommandResult("", "")
        if command[:2] == ("docker", "compose"):
            return CommandResult("compose ok", "")
        raise AssertionError(f"Unexpected command: {command}")


def make_service(tmp_path: Path, runner: FakeCommandRunner) -> UpdaterService:
    repository = tmp_path / "repo"
    (repository / ".git").mkdir(parents=True, exist_ok=True)
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
async def test_status_throttles_remote_fetches(tmp_path: Path) -> None:
    runner = FakeCommandRunner()
    service = make_service(tmp_path, runner)

    await service.get_status()
    await service.get_status()

    assert runner.commands.count(("git", "fetch", "origin", "--tags", "--prune")) == 1
    assert (
        ("git", "fetch", "origin", "--tags", "--prune"),
        service.settings.status_fetch_timeout_seconds,
    ) in runner.command_timeouts


@pytest.mark.asyncio
async def test_status_rejects_unknown_manifest_schema_version(tmp_path: Path) -> None:
    runner = FakeCommandRunner()
    service = make_service(tmp_path, runner)
    original_run = runner.run

    def run_with_unknown_schema(args: Sequence[str], *, timeout: int) -> CommandResult:
        if tuple(args) == ("git", "show", "v1.1.0:update-manifest.json"):
            return CommandResult(
                '{"schema_version":2,"automatic_update":true,"migration_mode":"compose"}',
                "",
            )
        return original_run(args, timeout=timeout)

    runner.run = run_with_unknown_schema  # type: ignore[method-assign]

    status = await service.get_status()

    assert status.can_update is False
    assert status.blocked_reason == "The target release does not declare automatic update support"


@pytest.mark.asyncio
async def test_status_blocks_dirty_worktree(tmp_path: Path) -> None:
    service = make_service(tmp_path, FakeCommandRunner(dirty=True))

    status = await service.get_status()

    assert status.can_update is False
    assert status.dirty is True
    assert status.blocked_reason == "The QDash working tree has tracked changes"


@pytest.mark.asyncio
async def test_status_blocks_non_main_branch(tmp_path: Path) -> None:
    service = make_service(tmp_path, FakeCommandRunner(branch="develop"))

    status = await service.get_status()

    assert status.can_update is False
    assert status.blocked_reason == "QDash must be running from the main branch"


@pytest.mark.asyncio
async def test_update_fast_forwards_main_deploys_and_persists_success(
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
    assert ("git", "merge", "--ff-only", "v1.1.0") in runner.commands
    assert ("docker", "compose", "up", "-d", "--build") in runner.commands
    assert service.settings.state_path.exists()


@pytest.mark.asyncio
async def test_update_rejects_stale_current_version(tmp_path: Path) -> None:
    service = make_service(tmp_path, FakeCommandRunner())

    with pytest.raises(UpdateBlockedError, match="Current version changed"):
        await service.start_update("v0.9.0")


@pytest.mark.asyncio
async def test_recovery_rolls_back_an_interrupted_deployment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = FakeCommandRunner()
    service = make_service(tmp_path, runner)
    operation = UpdateOperation(
        operation_id="update-1",
        state=UpdateState.RUNNING,
        source_version="v1.0.0",
        target_version="v1.1.0",
        stage="deploying",
        message="Deploying",
        progress=60,
        started_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        previous_commit="a" * 40,
    )
    service._operation = operation
    service._persist_operation()
    recovered = make_service(tmp_path, runner)
    monkeypatch.setattr(recovered, "_wait_for_health", lambda: None)

    await recovered.recover_interrupted_update()

    completed = recovered.get_operation("update-1")
    assert completed is not None
    assert completed.state == UpdateState.ROLLED_BACK
    assert ("git", "reset", "--hard", "a" * 40) in runner.commands
    assert ("docker", "compose", "up", "-d", "--build") in runner.commands
