"""Stored calibration pipeline plans: create, read, and check one for execution.

A plan lets a person approve a pipeline by reference: Code Mode (or any client) builds a
spec, stores it here as a plan, and the model passes only the plan ID to
``qdash_run_pipeline``. The host fetches the plan, shows its review content, and binds the
approval to its ``review_digest``; execution names that digest and runs only when the plan
still has it.

Creating a plan writes out every default task list and then validates the spec as
``/validate`` does, so the written-out tasks are checked too and a spec that omits ``tasks``
can be refused here although ``/validate`` accepts it; nothing is stored when it is not
valid. It reads the chip, the backend's tasks and calibration data, and never touches
hardware, a run, or a calibration session. Plans are immutable, belong to their creator in
their project (another user's plan is not found), and expire after ``PLAN_TTL``. Expiry is
checked on every read, independent of the TTL deletion that removes the document
``PLAN_RETENTION_AFTER_EXPIRY`` later; a plan never becomes executable again, and a new plan
always gets a new ID. The creation key is deduplicated only while the plan is stored: after
the deletion the same key creates a new plan, which needs its own approval.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from fastapi import HTTPException, status
from pydantic import ValidationError
from pymongo.errors import DuplicateKeyError

from qdash.api.schemas.calibration_pipeline import (
    PipelinePlanResponse,
    PipelineProblem,
    ResolvedPipelineStep,
    ResolvedPipelineTargets,
    ValidatePipelineResponse,
)
from qdash.api.services.agent_execution_links import utc
from qdash.common.utils.datetime import now
from qdash.datamodel.calibration_pipeline import SPEC_VERSION, CalibrationPipelineSpec
from qdash.datamodel.calibration_plan import (
    PLAN_REVIEW_VERSION,
    content_differences,
    materialize_default_tasks,
    review_content,
    review_digest,
)
from qdash.dbmodel.calibration_pipeline_plan import (
    MAX_PLAN_SPEC_BYTES,
    PLAN_RETENTION_AFTER_EXPIRY,
    PLAN_TTL,
    CalibrationPipelinePlanDocument,
)
from qdash.repository.calibration_pipeline_plan import find_plan, find_plan_by_scope, insert_plan
from qdash.repository.run_ledger import key_scope

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

    from qdash.api.services.calibration_pipeline_service import CalibrationPipelineService


def _invalid(problems: list[PipelineProblem], message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail={"message": message, "problems": [problem.model_dump() for problem in problems]},
    )


def _creation_hash(chip_id: str, spec: dict[str, Any], backend_name: str | None) -> str:
    payload = json.dumps(
        {"chip_id": chip_id, "spec": spec, "backend_name": backend_name},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _not_found(plan_id: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Calibration pipeline plan {plan_id} not found",
    )


def _expired(doc: CalibrationPipelinePlanDocument) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_410_GONE,
        detail=(
            f"Calibration pipeline plan {doc.plan_id} expired at {utc(doc.expires_at)}; "
            "it cannot be run or renewed. Create a new plan and have it approved."
        ),
    )


@dataclass(frozen=True)
class ValidatedPlan:
    """A plan checked for one execution request, as the run ledger hands it on."""

    doc: CalibrationPipelinePlanDocument
    result: ValidatePipelineResponse
    review: dict[str, Any]

    # The run ledger and the decision check read these from what was validated.
    @property
    def spec(self) -> dict[str, Any]:
        return self.doc.spec

    @property
    def targets(self) -> ResolvedPipelineTargets | None:
        return self.result.targets

    @property
    def backend_name(self) -> str:
        return self.doc.backend_name

    @property
    def steps(self) -> list[ResolvedPipelineStep]:
        return self.result.steps


class PipelinePlanService:
    """Create, read, and check stored plans for one project's signed-in user."""

    def __init__(
        self,
        pipelines: CalibrationPipelineService,
        *,
        clock: Callable[[], datetime] = now,
    ) -> None:
        self._pipelines = pipelines
        self._clock = clock

    # ------------------------------------------------------------------ helpers

    def _is_expired(self, doc: CalibrationPipelinePlanDocument) -> bool:
        expires = utc(doc.expires_at)
        return expires is None or self._clock() >= expires

    def response(
        self, doc: CalibrationPipelinePlanDocument, *, replayed: bool = False
    ) -> PipelinePlanResponse:
        """The plan as the API answers it."""
        preview = doc.preview
        return PipelinePlanResponse(
            plan_id=doc.plan_id,
            chip_id=doc.chip_id,
            backend_name=doc.backend_name,
            created_by=doc.created_by,
            created_at=utc(doc.created_at) or doc.created_at,
            expires_at=utc(doc.expires_at) or doc.expires_at,
            expired=self._is_expired(doc),
            review_version=int(doc.review.get("version", PLAN_REVIEW_VERSION)),
            review_digest=doc.review_digest,
            spec=doc.spec,
            spec_digest=preview.get("spec_digest"),
            targets=preview.get("targets"),
            target_qids=list(doc.review.get("target_qids") or []),
            steps=preview.get("steps") or [],
            warnings=preview.get("warnings") or [],
            task_run_count=int(preview.get("task_run_count") or 0),
            default_run_parameters=dict(doc.review.get("default_run_parameters") or {}),
            task_parameters=dict(doc.review.get("task_parameters") or {}),
            replayed=replayed,
        )

    def _review(
        self, project_id: str, chip_id: str, result: ValidatePipelineResponse
    ) -> tuple[CalibrationPipelineSpec, dict[str, Any]]:
        """The parsed spec of a valid result and its review content, or a 422."""
        assert result.spec is not None  # a valid result carries its normalized spec
        parsed = CalibrationPipelineSpec.model_validate(result.spec)
        qids, problem = self._pipelines.initial_target_qids(project_id, chip_id, parsed)
        if problem is not None or qids is None:
            raise _invalid(
                [problem] if problem else [], "calibration pipeline targets cannot be resolved"
            )
        return parsed, review_content(
            chip_id=chip_id,
            backend_name=result.backend_name,
            spec=parsed,
            target_qids=qids,
        )

    def _validate(
        self, project_id: str, chip_id: str, spec: dict[str, Any], backend_name: str | None
    ) -> ValidatePipelineResponse:
        result = self._pipelines.validate(
            project_id=project_id, chip_id=chip_id, spec=spec, backend_name=backend_name
        )
        if not result.valid or result.spec is None:
            raise _invalid(result.problems, "calibration pipeline spec is not valid")
        return result

    @staticmethod
    def _materialized(spec: dict[str, Any]) -> dict[str, Any]:
        """The spec with default task lists written out; unparsable specs pass unchanged.

        ``validate`` then reports the problems of a spec that does not parse as ``/validate``
        does. A spec that parses is checked with its default tasks written out, which is
        stricter than ``/validate``: an omitted task list whose default names a task the
        backend does not provide is a problem here and not there.
        """
        if not isinstance(spec, dict) or spec.get("spec_version", 1) != SPEC_VERSION:
            return spec
        try:
            parsed = CalibrationPipelineSpec.model_validate(spec)
        except (ValidationError, ValueError):
            return spec
        return materialize_default_tasks(parsed).model_dump(mode="json", exclude_none=True)

    # ------------------------------------------------------------------- create

    def create(
        self,
        *,
        project_id: str,
        username: str,
        chip_id: str,
        spec: dict[str, Any],
        backend_name: str | None,
        idempotency_key: str,
    ) -> PipelinePlanResponse:
        """Store a valid spec as a new plan, or return the plan this key already stored."""
        size = len(json.dumps(spec, separators=(",", ":"), default=str).encode())
        if size > MAX_PLAN_SPEC_BYTES:
            raise _invalid(
                [
                    PipelineProblem(
                        path="spec",
                        message=f"the spec is {size} bytes; a plan holds at most "
                        f"{MAX_PLAN_SPEC_BYTES}",
                    )
                ],
                "calibration pipeline spec is too large for a plan",
            )
        scope = key_scope(username, idempotency_key)
        request_hash = _creation_hash(chip_id, spec, backend_name)
        existing = find_plan_by_scope(project_id, scope)
        if existing is not None:
            return self._replay(existing, request_hash)

        result = self._validate(project_id, chip_id, self._materialized(spec), backend_name)
        _, review = self._review(project_id, chip_id, result)
        created = self._clock()
        expires = created + PLAN_TTL
        doc = CalibrationPipelinePlanDocument(
            plan_id=f"cpp-{uuid4().hex}",
            project_id=project_id,
            created_by=username,
            chip_id=chip_id,
            backend_name=result.backend_name,
            creation_scope=scope,
            request_hash=request_hash,
            spec=review["spec"],
            review=review,
            review_digest=review_digest(review),
            preview={
                "spec_digest": result.plan_digest,
                "targets": result.targets.model_dump(mode="json") if result.targets else None,
                "steps": [step.model_dump(mode="json") for step in result.steps],
                "warnings": [warning.model_dump(mode="json") for warning in result.warnings],
                "task_run_count": result.task_run_count,
            },
            created_at=created,
            expires_at=expires,
            delete_after=expires + PLAN_RETENTION_AFTER_EXPIRY,
        )
        try:
            insert_plan(doc)
        except DuplicateKeyError:
            # A concurrent creation with the same key stored its plan first.
            raced = find_plan_by_scope(project_id, scope)
            if raced is None:
                raise
            return self._replay(raced, request_hash)
        return self.response(doc)

    def _replay(
        self, existing: CalibrationPipelinePlanDocument, request_hash: str
    ) -> PipelinePlanResponse:
        if existing.request_hash != request_hash:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"This idempotency key already created plan {existing.plan_id} for a "
                    "different request; use a new key for a new plan."
                ),
            )
        if self._is_expired(existing):
            raise _expired(existing)
        return self.response(existing, replayed=True)

    # --------------------------------------------------------------------- read

    def get(self, *, project_id: str, username: str, plan_id: str) -> PipelinePlanResponse:
        """The signed-in user's plan, expired or not; another user's plan is not found."""
        doc = find_plan(project_id, username, plan_id)
        if doc is None:
            raise _not_found(plan_id)
        return self.response(doc)

    # ------------------------------------------------------------------ execute

    def for_execution(
        self,
        *,
        project_id: str,
        username: str,
        plan_id: str,
        chip_id: str,
        backend_name: str | None,
        expected_review_digest: str,
    ) -> ValidatedPlan:
        """The plan, checked again for running it now exactly as it was approved.

        Refused when it is not the user's, expired, for another chip or backend, or has
        another review digest; when its spec is no longer valid; and when its review
        content resolved now (default tasks, MUX expansion, settings) no longer has the
        stored digest. Nothing is substituted: a changed plan is refused, never adjusted.
        """
        doc = find_plan(project_id, username, plan_id)
        if doc is None:
            raise _not_found(plan_id)
        if self._is_expired(doc):
            raise _expired(doc)
        if doc.chip_id != chip_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Plan {plan_id} is for chip {doc.chip_id}, not {chip_id}",
            )
        if backend_name is not None and backend_name.strip() != doc.backend_name:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Plan {plan_id} is for backend {doc.backend_name}, not {backend_name}",
            )
        if expected_review_digest != doc.review_digest:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Plan {plan_id} has review digest {doc.review_digest}, not the approved "
                    f"{expected_review_digest}; nothing was started."
                ),
            )
        result = self._validate(project_id, chip_id, doc.spec, doc.backend_name)
        _, review = self._review(project_id, chip_id, result)
        if review_digest(review) != doc.review_digest:
            differences = content_differences(doc.review, review)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Plan {plan_id} no longer resolves to what was approved (changed: "
                    f"{', '.join(differences) or 'review content'}); nothing was started. "
                    "Create a new plan and have it approved."
                ),
            )
        return ValidatedPlan(doc=doc, result=result, review=review)
