"""Safe host-side update orchestration for source-based QDash deployments."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Protocol
from urllib.parse import urlparse
from uuid import uuid4

from qdash.updater.models import (
    UpdateManifest,
    UpdateOperation,
    UpdateState,
    UpdateStatus,
)
from qdash.updater.runtime import updater_runtime_dir

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from collections.abc import Sequence

STABLE_TAG_PATTERN = re.compile(r"^v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
RELEASE_BRANCH = "main"
ACTIVE_STATES = {UpdateState.QUEUED, UpdateState.RUNNING, UpdateState.ROLLING_BACK}
APP_SERVICES = ("api", "ui", "deployment-service", "user-flow-worker")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _env_value(name: str, default: str) -> str:
    value = os.environ.get(name, "").strip()
    return value or default


def _stable_version(tag: str) -> tuple[int, int, int] | None:
    match = STABLE_TAG_PATTERN.fullmatch(tag)
    if match is None:
        return None
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


@dataclass(frozen=True, slots=True)
class UpdaterSettings:
    """Environment-backed updater settings."""

    repository_path: Path
    remote: str = "origin"
    state_path: Path = Path("/var/lib/qdash-updater/state.json")
    health_url: str = "http://127.0.0.1:5715/docs"
    command_timeout_seconds: int = 1800
    status_fetch_timeout_seconds: int = 30
    status_fetch_interval_seconds: int = 60
    health_timeout_seconds: int = 180

    @classmethod
    def from_env(cls) -> UpdaterSettings:
        """Load updater settings without depending on the QDash API configuration."""
        repository_path = Path(_env_value("QDASH_UPDATER_REPOSITORY", os.getcwd())).resolve()
        runtime_dir = updater_runtime_dir()
        state_path = Path(
            _env_value(
                "QDASH_UPDATER_STATE_PATH",
                str(runtime_dir / "state.json"),
            )
        ).resolve()
        api_port = _env_value("API_PORT", "5715")
        return cls(
            repository_path=repository_path,
            remote=_env_value("QDASH_UPDATER_REMOTE", "origin"),
            state_path=state_path,
            health_url=_env_value(
                "QDASH_UPDATER_HEALTH_URL",
                f"http://127.0.0.1:{api_port}/docs",
            ),
            command_timeout_seconds=int(
                _env_value("QDASH_UPDATER_COMMAND_TIMEOUT_SECONDS", "1800")
            ),
            status_fetch_timeout_seconds=int(
                _env_value("QDASH_UPDATER_STATUS_FETCH_TIMEOUT_SECONDS", "30")
            ),
            status_fetch_interval_seconds=int(
                _env_value("QDASH_UPDATER_STATUS_FETCH_INTERVAL_SECONDS", "60")
            ),
            health_timeout_seconds=int(_env_value("QDASH_UPDATER_HEALTH_TIMEOUT_SECONDS", "180")),
        )


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Captured command result."""

    stdout: str
    stderr: str


class CommandRunner(Protocol):
    """Interface used to isolate subprocess execution in tests."""

    def run(self, args: Sequence[str], *, timeout: int) -> CommandResult:
        """Run one allowlisted command."""


class SubprocessCommandRunner:
    """Run commands from the configured repository without invoking a shell."""

    def __init__(self, repository_path: Path) -> None:
        self._repository_path = repository_path

    def run(self, args: Sequence[str], *, timeout: int) -> CommandResult:
        completed = subprocess.run(  # noqa: S603 - arguments are constructed internally
            list(args),
            cwd=self._repository_path,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return CommandResult(stdout=completed.stdout.strip(), stderr=completed.stderr.strip())


class UpdateBlockedError(RuntimeError):
    """Raised when update preconditions are not satisfied."""


class UpdaterService:
    """Inspect stable tags and execute one serialized source update."""

    def __init__(
        self,
        settings: UpdaterSettings,
        runner: CommandRunner | None = None,
    ) -> None:
        self.settings = settings
        self._runner = runner or SubprocessCommandRunner(settings.repository_path)
        self._lock = asyncio.Lock()
        self._status_lock = asyncio.Lock()
        self._last_status_fetch_at: float | None = None
        self._operation = self._load_operation()
        self._background_tasks: set[asyncio.Task[None]] = set()

    async def get_status(self) -> UpdateStatus:
        """Refresh tags and report whether the latest stable release is installable."""
        return await self._get_status()

    async def recover_interrupted_update(self) -> None:
        """Restore the previous revision when the updater stopped during deployment."""
        async with self._lock:
            operation = self._operation
            if operation is None or operation.state not in ACTIVE_STATES:
                return
            if operation.previous_commit:
                await self._rollback(
                    operation.operation_id,
                    operation.previous_commit,
                    RuntimeError("Updater restarted before the operation completed"),
                )
                return
            self._set_operation(
                operation.operation_id,
                state=UpdateState.FAILED,
                stage="interrupted",
                message="Updater restarted before deployment began",
                progress=100,
                completed=True,
            )

    async def start_update(
        self,
        expected_current_version: str | None,
        operation_id: str | None = None,
    ) -> UpdateOperation:
        """Queue an update after an atomic in-process concurrency check."""
        async with self._lock:
            if self._operation is not None and self._operation.state in ACTIVE_STATES:
                raise UpdateBlockedError("Another system update is already running")

            status = await self._get_status()
            if expected_current_version and expected_current_version != status.current_version:
                raise UpdateBlockedError(
                    "Current version changed; refresh update status before retrying"
                )
            if not status.can_update or status.latest_version is None:
                raise UpdateBlockedError(status.blocked_reason or "No update is available")

            operation = UpdateOperation(
                operation_id=operation_id or str(uuid4()),
                state=UpdateState.QUEUED,
                source_version=status.current_version,
                target_version=status.latest_version,
                stage="queued",
                message="System update queued",
                progress=0,
                started_at=_now(),
                updated_at=_now(),
            )
            self._operation = operation
            self._persist_operation()
            task = asyncio.create_task(self._run_update(operation.operation_id))
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)
            return operation.model_copy(deep=True)

    async def _get_status(self) -> UpdateStatus:
        """Serialize status inspection so polling cannot fan out Git fetches."""
        async with self._status_lock:
            return await asyncio.to_thread(self._inspect_status)

    def get_operation(self, operation_id: str) -> UpdateOperation | None:
        """Return the current persisted operation when its identifier matches."""
        if self._operation is None or self._operation.operation_id != operation_id:
            return None
        return self._operation.model_copy(deep=True)

    def _git(self, *args: str) -> CommandResult:
        return self._runner.run(
            ("git", *args),
            timeout=self.settings.command_timeout_seconds,
        )

    def _compose(self, *args: str) -> CommandResult:
        return self._runner.run(
            ("docker", "compose", *args),
            timeout=self.settings.command_timeout_seconds,
        )

    def _inspect_status(self) -> UpdateStatus:
        repository = self.settings.repository_path
        if not (repository / ".git").exists():
            return self._blocked_status("unknown", "unknown", "Repository is not a Git checkout")

        try:
            current_commit = self._git("rev-parse", "HEAD").stdout
            current_version = self._exact_current_tag() or current_commit[:12]
            current_branch = self._current_branch()
            dirty = bool(self._git("status", "--porcelain", "--untracked-files=no").stdout)
            now = time.monotonic()
            if (
                self._last_status_fetch_at is None
                or now - self._last_status_fetch_at >= self.settings.status_fetch_interval_seconds
            ):
                self._runner.run(
                    ("git", "fetch", self.settings.remote, "--tags", "--prune"),
                    timeout=self.settings.status_fetch_timeout_seconds,
                )
                self._last_status_fetch_at = now
            latest_version = self._latest_stable_tag()
        except (subprocess.SubprocessError, OSError) as exc:
            return self._blocked_status(
                "unknown",
                "unknown",
                f"Unable to inspect releases: {exc}",
            )

        blocked_reason: str | None = None
        current_semver = _stable_version(current_version)
        latest_semver = _stable_version(latest_version) if latest_version else None
        update_available = bool(
            current_semver is not None
            and latest_semver is not None
            and latest_semver > current_semver
        )

        if current_branch != RELEASE_BRANCH:
            blocked_reason = f"QDash must be running from the {RELEASE_BRANCH} branch"
        elif dirty:
            blocked_reason = "The QDash working tree has tracked changes"
        elif current_semver is None:
            blocked_reason = "QDash is not running from an exact stable release tag"
        elif latest_version is None:
            blocked_reason = "No stable release tag was found"
        elif not update_available:
            blocked_reason = "QDash is already on the latest stable release"
        else:
            manifest = self._read_manifest(latest_version)
            if manifest is None:
                blocked_reason = "The target release does not declare automatic update support"
            elif not manifest.automatic_update:
                blocked_reason = manifest.notes or "The target release requires a manual update"
            elif manifest.migration_mode != "compose":
                blocked_reason = manifest.notes or "The target release requires manual migration"

        operation = self._operation
        if operation is not None and operation.state in ACTIVE_STATES:
            blocked_reason = "Another system update is already running"

        return UpdateStatus(
            current_version=current_version,
            current_commit=current_commit,
            latest_version=latest_version,
            update_available=update_available,
            can_update=blocked_reason is None,
            dirty=dirty,
            blocked_reason=blocked_reason,
            operation_id=operation.operation_id if operation else None,
            operation_state=operation.state if operation else UpdateState.IDLE,
            checked_at=_now(),
        )

    def _blocked_status(self, version: str, commit: str, reason: str) -> UpdateStatus:
        operation = self._operation
        return UpdateStatus(
            current_version=version,
            current_commit=commit,
            blocked_reason=reason,
            operation_id=operation.operation_id if operation else None,
            operation_state=operation.state if operation else UpdateState.IDLE,
            checked_at=_now(),
        )

    def _exact_current_tag(self) -> str | None:
        try:
            tags = self._git("tag", "--points-at", "HEAD").stdout.splitlines()
        except subprocess.SubprocessError:
            return None
        stable_tags = [tag for tag in tags if _stable_version(tag) is not None]
        return max(stable_tags, key=lambda tag: _stable_version(tag) or (0, 0, 0), default=None)

    def _current_branch(self) -> str | None:
        try:
            return self._git("symbolic-ref", "--short", "HEAD").stdout
        except subprocess.SubprocessError:
            return None

    def _latest_stable_tag(self) -> str | None:
        remote_branch = f"{self.settings.remote}/{RELEASE_BRANCH}"
        tags = self._git("tag", "--merged", remote_branch, "--list", "v*").stdout.splitlines()
        stable_tags = [tag for tag in tags if _stable_version(tag) is not None]
        return max(stable_tags, key=lambda tag: _stable_version(tag) or (0, 0, 0), default=None)

    def _read_manifest(self, tag: str) -> UpdateManifest | None:
        try:
            payload = self._git("show", f"{tag}:update-manifest.json").stdout
            return UpdateManifest.model_validate_json(payload)
        except (subprocess.SubprocessError, ValueError):
            return None

    async def _run_update(self, operation_id: str) -> None:
        previous_commit = ""
        try:
            self._set_operation(
                operation_id,
                state=UpdateState.RUNNING,
                stage="preflight",
                message="Validating target release",
                progress=10,
            )
            status = await self._get_status()
            operation = self.get_operation(operation_id)
            if operation is None:
                raise RuntimeError("Update operation state was lost")
            if status.current_version != operation.source_version:
                raise UpdateBlockedError("Current release changed after the update was queued")
            if status.latest_version != operation.target_version:
                raise UpdateBlockedError(
                    "Latest stable release changed after the update was queued"
                )
            if status.dirty:
                raise UpdateBlockedError("The QDash working tree has tracked changes")
            manifest = await asyncio.to_thread(self._read_manifest, operation.target_version)
            if (
                manifest is None
                or not manifest.automatic_update
                or manifest.migration_mode != "compose"
            ):
                raise UpdateBlockedError("The target release is not safe for automatic update")

            previous_commit = (await asyncio.to_thread(self._git, "rev-parse", "HEAD")).stdout
            self._set_operation(
                operation_id,
                stage="stopping",
                message="Stopping QDash application services",
                progress=25,
                previous_commit=previous_commit,
            )
            await asyncio.to_thread(self._compose, "stop", *APP_SERVICES)

            self._set_operation(
                operation_id,
                stage="fast-forward",
                message=f"Advancing {RELEASE_BRANCH} to {operation.target_version}",
                progress=40,
            )
            await asyncio.to_thread(self._git, "merge", "--ff-only", operation.target_version)
            await asyncio.to_thread(self._compose, "config", "--quiet")

            self._set_operation(
                operation_id,
                stage="deploying",
                message="Building images and starting QDash",
                progress=60,
            )
            result = await asyncio.to_thread(self._compose, "up", "-d", "--build")
            self._append_log(operation_id, result.stdout, result.stderr)

            self._set_operation(
                operation_id,
                stage="health-check",
                message="Waiting for the QDash API health check",
                progress=90,
            )
            await asyncio.to_thread(self._wait_for_health)
            self._set_operation(
                operation_id,
                state=UpdateState.SUCCEEDED,
                stage="complete",
                message=f"Updated QDash to {operation.target_version}",
                progress=100,
                completed=True,
            )
        except Exception as exc:
            logger.exception("QDash update %s failed", operation_id)
            self._append_log(operation_id, str(exc))
            if previous_commit:
                await self._rollback(operation_id, previous_commit, exc)
            else:
                self._set_operation(
                    operation_id,
                    state=UpdateState.FAILED,
                    stage="failed",
                    message=str(exc),
                    progress=100,
                    completed=True,
                )

    async def _rollback(self, operation_id: str, previous_commit: str, cause: Exception) -> None:
        self._set_operation(
            operation_id,
            state=UpdateState.ROLLING_BACK,
            stage="rollback",
            message="Update failed; restoring the previous QDash revision",
            progress=95,
        )
        try:
            await asyncio.to_thread(self._git, "reset", "--hard", previous_commit)
            result = await asyncio.to_thread(self._compose, "up", "-d", "--build")
            self._append_log(operation_id, result.stdout, result.stderr)
            await asyncio.to_thread(self._wait_for_health)
            self._set_operation(
                operation_id,
                state=UpdateState.ROLLED_BACK,
                stage="rolled-back",
                message=f"Update failed and the previous revision was restored: {cause}",
                progress=100,
                completed=True,
            )
        except Exception as rollback_exc:
            logger.exception("Rollback for QDash update %s failed", operation_id)
            self._append_log(operation_id, str(rollback_exc))
            self._set_operation(
                operation_id,
                state=UpdateState.FAILED,
                stage="rollback-failed",
                message=f"Update failed and rollback also failed: {rollback_exc}",
                progress=100,
                completed=True,
            )

    def _wait_for_health(self) -> None:
        parsed_url = urlparse(self.settings.health_url)
        if parsed_url.scheme not in {"http", "https"}:
            raise ValueError("QDASH_UPDATER_HEALTH_URL must use http or https")
        deadline = time.monotonic() + self.settings.health_timeout_seconds
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(  # noqa: S310 - scheme is validated above
                    self.settings.health_url,
                    timeout=5,
                ) as response:
                    if 200 <= response.status < 400:
                        return
            except (urllib.error.URLError, TimeoutError):
                pass
            time.sleep(2)
        raise TimeoutError(f"QDash health check timed out: {self.settings.health_url}")

    def _set_operation(
        self,
        operation_id: str,
        *,
        state: UpdateState | None = None,
        stage: str,
        message: str,
        progress: int,
        previous_commit: str | None = None,
        completed: bool = False,
    ) -> None:
        if self._operation is None or self._operation.operation_id != operation_id:
            raise RuntimeError("Update operation state was lost")
        self._operation.state = state or self._operation.state
        self._operation.stage = stage
        self._operation.message = message
        self._operation.progress = progress
        if previous_commit is not None:
            self._operation.previous_commit = previous_commit
        self._operation.updated_at = _now()
        if completed:
            self._operation.completed_at = _now()
        self._persist_operation()

    def _append_log(self, operation_id: str, *chunks: str) -> None:
        if self._operation is None or self._operation.operation_id != operation_id:
            return
        lines = [line for chunk in chunks if chunk for line in chunk.splitlines()]
        self._operation.log_tail = (self._operation.log_tail + lines)[-100:]
        self._operation.updated_at = _now()
        self._persist_operation()

    def _persist_operation(self) -> None:
        if self._operation is None:
            return
        path = self.settings.state_path
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = path.with_suffix(f"{path.suffix}.tmp")
        temporary_path.write_text(self._operation.model_dump_json(indent=2), encoding="utf-8")
        temporary_path.replace(path)

    def _load_operation(self) -> UpdateOperation | None:
        path = self.settings.state_path
        if not path.exists():
            return None
        try:
            operation = UpdateOperation.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            logger.warning("Ignoring invalid updater state file at %s", path, exc_info=True)
            return None
        return operation
