"""Typed settings shared by every session of one calibration run.

``SessionSettings`` is the single record of how a run measures and publishes:
context, backend, configuration mode, shared and per-task defaults, snapshot
source, quality override and GitHub policy. Parent, worker, single-task and
rerun sessions are all built from it, so no caller enumerates fields again.

Inheritance policy for isolated workers (``SessionSettings.for_worker``):

- inherited unchanged: context, backend, configuration mode, run metadata,
  ``default_run_parameters``, per-task defaults, the snapshot source
  (``source_execution_id``, ``source_task_id``, exempt tasks) and
  ``force_update_params``. A worker therefore measures exactly as its parent.
- replaced by lifecycle policy: GitHub pull and push are disabled (the owner
  pulls before the step and pushes when it finishes); the worker borrows the
  owner's Execution and hardware reservation (:class:`WorkerLease`) and never
  claims, creates, finishes, locks or unlocks either.

The models are frozen pydantic models so Prefect and Dask can pass them to
worker processes.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from qdash.common.execution_resources import ExecutionResourceScope
from qdash.common.mux_mapping import MuxMappingSnapshot  # noqa: TC001 - pydantic field type
from qdash.workflow.engine.task_parameters import (
    normalize_default_run_parameters,
    normalize_task_parameters,
)
from qdash.workflow.service.github import ConfigFileType, GitHubPushConfig


class SnapshotSource(BaseModel):
    """Where a re-execution restores parameters from.

    Attributes:
        execution_id: Execution whose parameter snapshot is restored.
        task_id: Task result whose snapshot is restored.
        exempt_tasks: Tasks that do not restore snapshot parameters.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    execution_id: str | None = None
    task_id: str | None = None
    exempt_tasks: frozenset[str] = frozenset()

    @property
    def active(self) -> bool:
        """Whether a snapshot is restored at all."""
        return self.execution_id is not None or self.task_id is not None


class GitHubPolicy(BaseModel):
    """Whether a session pulls configuration and pushes results.

    The default is :meth:`disabled`, so settings built without an explicit
    policy never touch the configuration repository. Workflow and single-task
    runs use :meth:`from_deployment`; internal callers that need a specific
    policy for one run pass :meth:`disabled` or :meth:`pull_and_push`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    pull: bool = False
    push: GitHubPushConfig = Field(default_factory=GitHubPushConfig)

    @classmethod
    def disabled(cls) -> GitHubPolicy:
        """No pull and no push."""
        return cls(pull=False, push=GitHubPushConfig(enabled=False))

    @classmethod
    def pull_and_push(cls, *, branch: str = "main") -> GitHubPolicy:
        """Pull before and push the calibration note and parameters after each step."""
        return cls(
            pull=True,
            push=GitHubPushConfig(
                enabled=True,
                file_types=[ConfigFileType.CALIB_NOTE, ConfigFileType.ALL_PARAMS],
                branch=branch,
            ),
        )

    @classmethod
    def from_deployment(cls, backend_name: str) -> GitHubPolicy:
        """The policy the deployment configures for runs on ``backend_name``.

        Reads ``github.enabled`` (default ``true``) and ``github.branch``
        (default ``"main"``) from ``config/app/workflow.yaml``. Only the qubex
        backend reads and writes the configuration repository, so every other
        backend, such as ``fake``, gets :meth:`disabled`.
        """
        from qdash.common.config.loader import ConfigLoader

        github_settings = ConfigLoader.load_workflow().get("github") or {}
        if not isinstance(github_settings, dict):
            raise ValueError("workflow.github must be a mapping")
        if github_settings.get("enabled", True) is not True or backend_name != "qubex":
            return cls.disabled()
        branch = github_settings.get("branch", "main")
        if not isinstance(branch, str) or not branch:
            raise ValueError("workflow.github.branch must be a non-empty string")
        return cls.pull_and_push(branch=branch)


class ReservationScope(BaseModel):
    """Serializable form of an :class:`ExecutionResourceScope`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    chip_id: str
    resources: tuple[str, ...] = ()
    exclusive: bool = False

    @classmethod
    def of(cls, scope: ExecutionResourceScope) -> ReservationScope:
        return cls(chip_id=scope.chip_id, resources=scope.resources, exclusive=scope.exclusive)

    def to_scope(self) -> ExecutionResourceScope:
        return ExecutionResourceScope(self.chip_id, self.resources, self.exclusive)


class SessionSettings(BaseModel):
    """Everything that decides how the sessions of one run measure and publish."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    username: str
    chip_id: str
    project_id: str
    backend_name: str
    flow_name: str | None = None
    tags: list[str] | None = None
    note: dict[str, Any] | None = None
    default_run_parameters: dict[str, Any] = Field(default_factory=dict)
    task_defaults: dict[str, dict[str, Any]] = Field(default_factory=dict)
    configuration_mode: str | None = None
    snapshot: SnapshotSource = Field(default_factory=SnapshotSource)
    force_update_params: bool = False
    github: GitHubPolicy = Field(default_factory=GitHubPolicy.disabled)

    def model_post_init(self, __context: Any) -> None:
        # Normalize once so every derived session sees the canonical form.
        object.__setattr__(
            self,
            "default_run_parameters",
            normalize_default_run_parameters(self.default_run_parameters),
        )
        object.__setattr__(self, "task_defaults", normalize_task_parameters(self.task_defaults))

    def with_metadata(
        self, *, flow_name: str | None, note: dict[str, Any] | None
    ) -> SessionSettings:
        """The same settings for one pipeline step's Execution."""
        return self.model_copy(update={"flow_name": flow_name, "note": note})

    def with_configuration_mode(self, configuration_mode: str | None) -> SessionSettings:
        """Record the configuration mode the owner resolved, for its workers."""
        return self.model_copy(update={"configuration_mode": configuration_mode})

    def for_worker(self) -> SessionSettings:
        """Settings of an isolated worker; see the module docstring for the policy."""
        return self.model_copy(update={"github": GitHubPolicy.disabled()})


class WorkerLease(BaseModel):
    """The Execution and hardware reservation a worker borrows from its owner."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    execution_id: str
    reservation: ReservationScope | None = None


class WorkerSpec(BaseModel):
    """What an isolated worker process needs to run calls under its owner's Execution.

    ``mux_mapping`` is the MUX membership the owner planned the run with. A
    worker uses it for representatives, scope checks and MUX result fan-out
    instead of reading the chip topology again, so an edit to the chip's
    topology during the run cannot split the owner and its workers. It is
    required: an owner that cannot resolve its mapping creates no worker, so
    no worker ever resolves a topology the owner did not plan with.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    settings: SessionSettings
    lease: WorkerLease
    mux_mapping: MuxMappingSnapshot
