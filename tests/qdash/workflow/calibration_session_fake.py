"""A recording stand-in for ``CalibrationSession`` in template tests.

Templates build ``qdash.calibration`` definitions and pass them to
``CalibrationSession.from_context(context).run(...)``. The fake converts them with
the worker's own conversion (``qdash.workflow.service.definitions``), so the tests
check the runtime steps and targets the worker would run, and records the run
options in the shape the legacy ``CalibService`` arguments had.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from qdash.workflow.service.definitions import runtime_steps, runtime_target

if TYPE_CHECKING:
    import pytest


@dataclass(frozen=True)
class FakeContext:
    username: str
    chip_id: str
    project_id: str | None
    backend: str | None


def fake_resolve_calib_context(
    username: str, chip_id: str, *, project_id: str | None = None, backend: str | None = None
) -> FakeContext:
    return FakeContext(username, chip_id, project_id, backend)


def fake_session_class() -> type[Any]:
    """A fresh fake class, so ``last_kwargs`` is not shared between test modules."""

    class FakeCalibrationSession:
        last_kwargs: dict[str, Any] | None = None
        last_definitions: list[Any] | None = None

        def __init__(self, context: FakeContext) -> None:
            self.context = context
            self.args = (context.username, context.chip_id)
            self.kwargs: dict[str, Any] = {}

        @classmethod
        def from_context(cls, context: FakeContext) -> FakeCalibrationSession:
            return cls(context)

        def run(
            self,
            targets: Any,
            steps: list[Any],
            *,
            default_run_parameters: dict[str, Any] | None = None,
            name: str | None = None,
            tags: list[str] | None = None,
            note: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            kwargs: dict[str, Any] = {
                "flow_name": name,
                "tags": tags,
                "project_id": self.context.project_id,
            }
            if default_run_parameters is not None:
                kwargs["default_run_parameters"] = default_run_parameters
            if note is not None:
                kwargs["note"] = note
            self.kwargs = kwargs
            type(self).last_kwargs = kwargs
            type(self).last_definitions = list(steps)
            return {
                "targets": runtime_target(targets),
                "steps": runtime_steps(steps),
                "definitions": list(steps),
                "definition_targets": targets,
                "args": self.args,
                "kwargs": kwargs,
                "context": self.context,
            }

    return FakeCalibrationSession


def install_fake_session(
    monkeypatch: pytest.MonkeyPatch, module: Any, fake: type[Any] | None = None
) -> type[Any]:
    """Replace ``CalibrationSession`` and ``resolve_calib_context`` in a template module."""
    fake = fake or fake_session_class()
    monkeypatch.setattr(module, "CalibrationSession", fake)
    monkeypatch.setattr(module, "resolve_calib_context", fake_resolve_calib_context)
    return fake
