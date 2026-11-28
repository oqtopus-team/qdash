"""The reviewed content of a stored calibration pipeline plan, shared by the API and the worker.

A plan is a validated ``CalibrationPipelineSpec`` that QDash stored so that a person can
approve it by reference. What the person approves is its *review content*: the normalized
spec with every default task list written out, the initial targets expanded to qubits, the
resolved calls of every step, and the run defaults. ``review_digest`` is a full SHA-256 of
that content, versioned, so an approval binds to exactly what was shown.

The API builds the content from the spec (``review_steps``); the worker builds the same
shape from the Step objects it is about to run and the qubits its targets resolve to
(``qdash.workflow.service.plan_approval``) and refuses to measure when the two differ. The
content describes the plan only: calibration values, the scientific defaults of a task, the
hardware state and the task code are read when the run happens and are not part of it.

This module stays free of workflow imports so the API can use it without a Prefect runtime.
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

from qdash.common.mux_mapping import canonical_qid
from qdash.datamodel.calibration_pipeline import (
    STEP_CATALOG,
    BringUpStep,
    CalibrationPipelineSpec,
    ConfigureAllStep,
    OneQubitCheckStep,
    OneQubitFineTuneStep,
    TwoQubitCalibrationStep,
    step_calls,
    step_continue_on_failure,
    step_id,
)
from qdash.datamodel.task_call import calls_json
from qdash.datamodel.two_qubit_execution_mode import DEFAULT_MAX_PARALLEL_OPS

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

    from qdash.datamodel.calibration_pipeline import PipelineStep

# Version of the review content and its digest; a change of shape gets a new version.
PLAN_REVIEW_VERSION = 1
REVIEW_DIGEST_PREFIX = f"sha256:v{PLAN_REVIEW_VERSION}:"
REVIEW_DIGEST_PATTERN = r"^sha256:v[0-9]+:[0-9a-f]{64}$"

# The pipeline flow's ``approved_plan`` parameter carries this key in its JSON schema, and the
# deployment registered from that flow records the schema. The API dispatches a stored plan
# only to a deployment whose recorded schema advertises this exact contract: an
# ``ApprovedPipelinePlan`` checked by ``qdash.workflow.service.plan_approval`` against review
# content of ``PLAN_REVIEW_VERSION``. A change to either side gets a new contract number.
APPROVED_PLAN_CONTRACT_KEY = "x-qdash-approved-plan-contract"
APPROVED_PLAN_CONTRACT = 1

# Steps whose omitted ``tasks`` mean the catalog's default list.
_DEFAULT_TASK_STEPS = (
    BringUpStep,
    OneQubitCheckStep,
    OneQubitFineTuneStep,
    TwoQubitCalibrationStep,
)
# Transform settings that decide what a transform keeps or schedules.
_TRANSFORM_FIELDS = ("step", "call_id", "metric", "threshold", "max_parallel_ops", "inverse")


def materialize_default_tasks(spec: CalibrationPipelineSpec) -> CalibrationPipelineSpec:
    """The same spec with every omitted default task list written out.

    A stored plan then names the calls it runs, so a worker whose default lists differ from
    the API's runs the approved calls or refuses, never its own defaults. A Configure call
    that ``configure=True`` prepends stays implicit: the flag is kept and the listed tasks are
    the default list without it.
    """
    data = spec.model_dump(mode="json", exclude_none=True)
    for index, step in enumerate(spec.steps):
        if isinstance(step, _DEFAULT_TASK_STEPS) and step.tasks is None:
            data["steps"][index]["tasks"] = calls_json(list(STEP_CATALOG[step.type].default_tasks))
    return CalibrationPipelineSpec.model_validate(data)


def _execution_mode(step: Any) -> str | None:
    mode = getattr(step, "execution_mode", None)
    return str(mode) if mode is not None else None


def _two_qubit_cap(mode: str | None, cap: Any) -> int | None:
    """The cap an automatic two-qubit step schedules with; none for a manual step."""
    if mode == "manual":
        return None
    return DEFAULT_MAX_PARALLEL_OPS if cap is None else int(cap)


def review_step(
    *,
    index: int,
    type_name: str,
    kind: str,
    resolved_step_id: str | None,
    continue_on_failure: bool,
    calls: list[dict[str, Any]],
    execution_mode: str | None,
    fields: Mapping[str, Any],
) -> dict[str, Any]:
    """One step of the review content, built the same way on both sides."""
    entry: dict[str, Any] = {"index": index, "type": type_name, "kind": kind}
    if kind == "calibration":
        entry["step_id"] = resolved_step_id
        entry["continue_on_failure"] = continue_on_failure
        entry["calls"] = calls
        if execution_mode is not None:
            entry["execution_mode"] = execution_mode
        if type_name in ("TwoQubitCalibration", "CustomTwoQubit"):
            entry["max_parallel_ops"] = _two_qubit_cap(
                execution_mode, fields.get("max_parallel_ops")
            )
        if type_name == "ConfigureAll":
            mux_ids = fields.get("mux_ids")
            entry["mux_ids"] = list(mux_ids) if mux_ids is not None else None
    else:
        entry["settings"] = {
            key: fields[key] for key in _TRANSFORM_FIELDS if fields.get(key) is not None
        }
    return entry


def review_steps(spec: CalibrationPipelineSpec) -> list[dict[str, Any]]:
    """The review entries of a spec's steps: identity, mode, and the calls each target runs."""
    entries: list[dict[str, Any]] = []
    for index, step in enumerate(spec.steps, start=1):
        kind = STEP_CATALOG[step.type].kind
        entries.append(
            review_step(
                index=index,
                type_name=step.type,
                kind=kind,
                resolved_step_id=step_id(step),
                continue_on_failure=step_continue_on_failure(step),
                calls=calls_json(step_calls(step)),
                execution_mode=_execution_mode(step) if kind == "calibration" else None,
                fields=_step_fields(step),
            )
        )
    return entries


def _step_fields(step: PipelineStep) -> dict[str, Any]:
    fields = {key: getattr(step, key, None) for key in _TRANSFORM_FIELDS}
    if isinstance(step, ConfigureAllStep):
        fields["mux_ids"] = step.mux_ids
    return fields


def canonical_qids(qids: Iterable[str]) -> list[str]:
    """Qubit IDs in canonical form, sorted and without repeats, for comparison."""
    return sorted({canonical_qid(qid) for qid in qids})


def review_content(
    *,
    chip_id: str,
    backend_name: str,
    spec: CalibrationPipelineSpec,
    target_qids: Sequence[str],
) -> dict[str, Any]:
    """Everything an approval of the plan covers, as JSON data.

    ``target_qids`` are the qubits the spec's targets resolve to when the run starts, as the
    worker resolves them. Later filters choose among them at run time from results; the
    content fixes the filter settings, not their outcome.
    """
    return {
        "version": PLAN_REVIEW_VERSION,
        "chip_id": chip_id,
        "backend_name": backend_name,
        "spec": spec.model_dump(mode="json", exclude_none=True),
        "target_qids": canonical_qids(target_qids),
        "target_pairs": [list(pair) for pair in spec.targets.pairs or []],
        "steps": review_steps(spec),
        "default_run_parameters": dict(spec.default_run_parameters),
        "task_parameters": spec.canonical_task_parameters(),
    }


def canonical_json(value: Any) -> str:
    """``value`` as the canonical JSON text the review digest hashes.

    Comparing this text, not Python values, keeps JSON types apart: ``False == 0`` and
    ``True == 1`` hold in Python, but ``false`` and ``0`` are different settings and give
    different digests.
    """
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def same_json(left: Any, right: Any) -> bool:
    """Whether two JSON values are equal with their JSON types, as the digest compares them."""
    return canonical_json(left) == canonical_json(right)


def review_digest(content: Mapping[str, Any]) -> str:
    """The versioned full SHA-256 of review content."""
    return REVIEW_DIGEST_PREFIX + hashlib.sha256(canonical_json(content).encode()).hexdigest()


def content_differences(approved: Mapping[str, Any], observed: Mapping[str, Any]) -> list[str]:
    """The top-level parts of review content that differ, with the first differing step.

    Values are compared as canonical JSON, so a Boolean that became a number (or the
    reverse) is a difference, at the top level and inside a step.
    """
    differences: list[str] = []
    for key in sorted(set(approved) | set(observed)):
        if same_json(approved.get(key), observed.get(key)):
            continue
        if key == "steps":
            mine, theirs = list(approved.get(key) or []), list(observed.get(key) or [])
            changed = [
                index + 1
                for index in range(max(len(mine), len(theirs)))
                if index >= len(mine)
                or index >= len(theirs)
                or not same_json(mine[index], theirs[index])
            ]
            differences.append(f"steps (first at step {changed[0]})" if changed else "steps")
        else:
            differences.append(key)
    return differences


class ApprovedPipelinePlan(BaseModel):
    """The plan a run was approved as, handed to the worker with the spec.

    The worker checks ``review`` against ``review_digest`` and against what it is about to
    run, and refuses before any measurement or hardware reservation when they differ.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    plan_id: str = Field(min_length=1)
    review_digest: str = Field(pattern=REVIEW_DIGEST_PATTERN)
    review: dict[str, Any]
