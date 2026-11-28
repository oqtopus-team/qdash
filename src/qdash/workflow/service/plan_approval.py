"""Worker-side check that a run carries out the calibration pipeline plan it was approved as.

A run started from a stored plan (``POST /calibration-pipelines/plans/{id}/execute``) reaches
the worker with the approved review content (``ApprovedPipelinePlan``). Before any step
reserves hardware or measures, the worker rebuilds that content from what it is about to
run: the Step objects built from the dispatched spec, the qubits its targets resolve to with
the session's MUX mapping and wiring, and the run defaults of its settings. A difference,
whether from a dispatched spec that is not the approved one, a default the worker resolves
differently, a target override or a MUX expansion that changed, stops the run with
``PlanApprovalMismatch``.

Only the start of the run is fixed this way. Filters and CR schedules still choose their
qubits and couplings from results as the run goes; the check fixes their settings, not what
they select. Calibration values, task defaults inside task code, and hardware state are
read when the run happens and are not covered.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from qdash.datamodel.calibration_plan import (
    ApprovedPipelinePlan,
    canonical_qids,
    content_differences,
    review_digest,
    review_step,
    same_json,
)
from qdash.datamodel.task_call import calls_json
from qdash.datamodel.task_settings import (
    normalize_default_run_parameters,
    normalize_task_parameters,
)
from qdash.workflow.service.steps.base import CalibrationStep

if TYPE_CHECKING:
    from collections.abc import Sequence

    from qdash.workflow.service.steps import Step
    from qdash.workflow.service.targets import Target

_FIELD_NAMES = ("step", "call_id", "metric", "threshold", "max_parallel_ops", "inverse", "mux_ids")


class PlanApprovalMismatch(RuntimeError):
    """The run differs from the plan it was approved as; nothing was reserved or measured."""


def observed_review_steps(steps: Sequence[Step]) -> list[dict[str, Any]]:
    """The review entries of the Step objects the worker is about to run."""
    entries: list[dict[str, Any]] = []
    for index, step in enumerate(steps, start=1):
        calibration = step if isinstance(step, CalibrationStep) else None
        mode = getattr(step, "execution_mode", None) if calibration else None
        entries.append(
            review_step(
                index=index,
                type_name=type(step).__name__,
                kind="calibration" if calibration else "transform",
                resolved_step_id=calibration.resolved_step_id if calibration else None,
                continue_on_failure=calibration.continue_on_failure if calibration else False,
                calls=calls_json(calibration.calls()) if calibration else [],
                execution_mode=str(mode) if mode is not None else None,
                fields={key: getattr(step, key, None) for key in _FIELD_NAMES},
            )
        )
    return entries


def check_dispatched_plan(
    approved: ApprovedPipelinePlan,
    *,
    chip_id: str,
    backend_name: str,
    spec: dict[str, Any],
) -> None:
    """Check the approved content is intact and is the plan this flow run was given."""
    if review_digest(approved.review) != approved.review_digest:
        raise PlanApprovalMismatch(
            f"The approved content of plan {approved.plan_id} does not match its review "
            "digest; nothing was run."
        )
    review = approved.review
    differences = [
        name
        for name, value in (("chip_id", chip_id), ("backend_name", backend_name), ("spec", spec))
        # Compared as canonical JSON: ``false`` and ``0`` are different settings.
        if not same_json(review.get(name), value)
    ]
    if differences:
        raise PlanApprovalMismatch(
            f"This run is not the plan {approved.plan_id} that was approved "
            f"(differs in {', '.join(differences)}); nothing was run."
        )


class ApprovedPlanCheck:
    """Compare what the run is about to do with its approved plan, before any reservation."""

    def __init__(self, approved: ApprovedPipelinePlan) -> None:
        self.approved = approved

    def __call__(
        self,
        *,
        targets: Target,
        qids: Sequence[str],
        steps: Sequence[Step],
        default_run_parameters: dict[str, Any],
        task_parameters: dict[str, Any],
    ) -> None:
        review = self.approved.review
        expected = {
            "target_qids": review.get("target_qids"),
            "target_pairs": review.get("target_pairs"),
            "steps": review.get("steps"),
            "default_run_parameters": normalize_default_run_parameters(
                dict(review.get("default_run_parameters") or {})
            ),
            "task_parameters": normalize_task_parameters(dict(review.get("task_parameters") or {})),
        }
        pairs = getattr(targets, "pairs", None)
        observed = {
            "target_qids": canonical_qids(qids),
            "target_pairs": [list(pair) for pair in pairs] if pairs else [],
            "steps": observed_review_steps(steps),
            "default_run_parameters": dict(default_run_parameters),
            "task_parameters": dict(task_parameters),
        }
        differences = content_differences(expected, observed)
        if differences:
            raise PlanApprovalMismatch(
                f"The run would not carry out the approved plan {self.approved.plan_id} "
                f"(review digest {self.approved.review_digest}): it differs in "
                f"{', '.join(differences)}. Nothing was reserved or measured; create a new "
                "plan and approve it again."
            )
