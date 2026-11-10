"""Run a step's task calls on its targets and record one result per call.

Two execution shapes exist, and they keep their own synchronization:

* :func:`run_target_calls` runs every call of the step on one target in order.
  It is used for a qubit, a MUX member, or a coupling inside a worker. Targets in
  different workers progress independently: one target's second call does not
  wait for another target's first call.
* :func:`run_batch_calls` runs each call once over a batch of qubits with
  ``execute_task_batch``. Every call is a barrier for the batch, because the
  hardware experiment measures the qubits together.

A step boundary is the all-target barrier: the pipeline finishes a step's
Execution before the next step starts.

Each target's result keeps every call in order, so a task that runs twice in a
step leaves two entries instead of one overwriting the other::

    {
        "status": "failed",
        "calls": [
            {"call_id": "ramsey_coarse", "name": "CheckRamsey", "status": "success",
             "task_id": "...", "output": {...}},
            {"call_id": "ramsey_fine", "name": "CheckRamsey", "status": "failed",
             "task_id": "...", "error": "..."},
            {"call_id": "t1", "name": "CheckT1", "status": "skipped",
             "reason": "stopped_after_failure"},
        ],
        "error": "ramsey_fine (CheckRamsey): ...",
    }
"""

from __future__ import annotations

import traceback
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from qdash.datamodel.task_call import StepCalls, TaskCall
    from qdash.workflow.service._internal.session import CalibSession

SUCCESS = "success"
FAILED = "failed"
SKIPPED = "skipped"
NOT_MUX_REPRESENTATIVE = "not_mux_representative"
STOPPED_AFTER_FAILURE = "stopped_after_failure"

_RESULT_KEYS = frozenset({"task_id", "status", "error", "message"})


def format_exception_details(e: BaseException) -> str:
    """Format exception details, including sub-exceptions for ExceptionGroup."""
    if hasattr(e, "exceptions"):
        parts = [f"{e}"]
        for i, sub_exc in enumerate(e.exceptions, 1):
            tb_str = "".join(
                traceback.format_exception(type(sub_exc), sub_exc, sub_exc.__traceback__)
            )
            parts.append(f"\n--- Sub-exception {i} ---\n{tb_str}")
        return "".join(parts)
    return "".join(traceback.format_exception(type(e), e, e.__traceback__))


def _call_entry(call: TaskCall, status: str, **fields: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "call_id": call.resolved_call_id,
        "name": call.name,
        "status": status,
    }
    entry.update({key: value for key, value in fields.items() if value is not None})
    return entry


def _success_entry(call: TaskCall, result: Mapping[str, Any]) -> dict[str, Any]:
    output = {key: value for key, value in result.items() if key not in _RESULT_KEYS}
    return _call_entry(call, SUCCESS, task_id=result.get("task_id"), output=output)


def _failure_entry(call: TaskCall, exc: BaseException, target: str) -> dict[str, Any]:
    task_ids = getattr(exc, "qdash_task_ids", None) or {}
    return _call_entry(
        call,
        FAILED,
        task_id=task_ids.get(target),
        error=str(exc),
        error_details=format_exception_details(exc),
    )


def summarize_target(calls: list[dict[str, Any]]) -> dict[str, Any]:
    """The target's result: its calls in order and an overall status."""
    failures = [call for call in calls if call["status"] == FAILED]
    result: dict[str, Any] = {"status": FAILED if failures else SUCCESS, "calls": calls}
    if failures:
        result["error"] = "; ".join(
            f"{call['call_id']} ({call['name']}): {call.get('error', '')}" for call in failures
        )
        details = [call["error_details"] for call in failures if call.get("error_details")]
        if details:
            result["error_details"] = "\n\n".join(details)
    return result


def run_target_calls(
    session: CalibSession,
    target: str,
    plan: StepCalls,
    logger: Any,
    *,
    skip_call: Callable[[TaskCall, str], bool] | None = None,
) -> dict[str, Any]:
    """Run the step's calls on one target, in order, and return its result.

    A failed call stops the target's later calls when the plan says so (see
    ``StepCalls.stops_after_failure``); the skipped calls stay in the result.
    ``skip_call`` marks calls a target does not run, such as a MUX task on a
    qubit that is not the MUX representative.
    """
    calls: list[dict[str, Any]] = []
    stopped_by: str | None = None
    for call in plan.calls:
        if stopped_by is not None:
            calls.append(
                _call_entry(call, SKIPPED, reason=STOPPED_AFTER_FAILURE, after_call_id=stopped_by)
            )
            continue
        if skip_call is not None and skip_call(call, target):
            logger.info(
                f"Skipping MUX task {call.name} ({call.resolved_call_id}) for {target} "
                "(not MUX representative)"
            )
            calls.append(_call_entry(call, SKIPPED, reason=NOT_MUX_REPRESENTATIVE))
            continue
        try:
            result = session.execute_task(
                call.name,
                target,
                parameters=call.settings(),
                invocation=plan.invocation(call),
            )
        except Exception as exc:
            entry = _failure_entry(call, exc, target)
            logger.error(
                f"Failed to execute {call.name} ({call.resolved_call_id}) for {target}:\n"
                f"{entry.get('error_details', '')}"
            )
            calls.append(entry)
            if plan.stops_after_failure(call):
                stopped_by = call.resolved_call_id
            continue
        calls.append(_success_entry(call, result))
    return summarize_target(calls)


def batch_preflight_problems(
    plan: StepCalls,
    task_defaults: Mapping[str, Mapping[str, Any]],
    batch_tasks: Mapping[str, bool],
) -> list[str]:
    """Reasons the batch path cannot run the plan, found before any hardware work.

    ``batch_tasks`` maps each task name to whether it implements ``batch_run``.
    Batch execution measures every qubit together, so per-call calibration input
    overrides are not supported there, from the call or from the per-task defaults.
    """
    problems: list[str] = []
    for call in plan.calls:
        label = f"{plan.step_id}.{call.resolved_call_id} ({call.name})"
        supports = batch_tasks.get(call.name)
        if supports is None:
            problems.append(f"{label}: task is not registered for this backend")
        elif not supports:
            problems.append(f"{label}: task does not support batch execution")
        effective = call.effective_settings(task_defaults)
        if effective.get("input"):
            problems.append(
                f"{label}: batch execution does not support calibration input overrides "
                f"({', '.join(sorted(effective['input']))})"
            )
    return problems


def run_batch_calls(
    session: CalibSession,
    qids: list[str],
    plan: StepCalls,
    logger: Any,
) -> dict[str, dict[str, Any]]:
    """Run each call once over the batch of qubits and return per-qubit results.

    Every call waits for the whole batch. A qubit whose call failed with a
    stopping policy leaves the batch for the rest of the step; the others go on.
    """
    calls_by_qid: dict[str, list[dict[str, Any]]] = {qid: [] for qid in qids}
    stopped_by: dict[str, str] = {}
    for call in plan.calls:
        active = [qid for qid in qids if qid not in stopped_by]
        for qid in qids:
            if qid in stopped_by:
                calls_by_qid[qid].append(
                    _call_entry(
                        call, SKIPPED, reason=STOPPED_AFTER_FAILURE, after_call_id=stopped_by[qid]
                    )
                )
        if not active:
            continue
        logger.info(f"Running batch call {call.resolved_call_id} ({call.name}) for qids={active}")
        try:
            results = session.execute_task_batch(
                call.name,
                active,
                parameters=call.settings(),
                invocation=plan.invocation(call),
            )
        except Exception as exc:
            for qid in active:
                calls_by_qid[qid].append(_failure_entry(call, exc, qid))
                if plan.stops_after_failure(call):
                    stopped_by[qid] = call.resolved_call_id
            logger.error(f"Batch call {call.resolved_call_id} failed: {exc}")
            continue
        for qid in active:
            result = results.get(qid)
            if result is None:
                result = {
                    "status": FAILED,
                    "error": f"Batch call {call.resolved_call_id} returned no result for target {qid}",
                }
            if result.get("status", SUCCESS) == SUCCESS:
                calls_by_qid[qid].append(_success_entry(call, result))
                continue
            calls_by_qid[qid].append(
                _call_entry(
                    call,
                    FAILED,
                    task_id=result.get("task_id"),
                    error=str(result.get("error") or result.get("message") or result.get("status")),
                )
            )
            if plan.stops_after_failure(call):
                stopped_by[qid] = call.resolved_call_id
    return {qid: summarize_target(calls) for qid, calls in calls_by_qid.items()}


def call_results(target_result: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The ordered call entries of one target's result."""
    calls = target_result.get("calls")
    return [call for call in calls if isinstance(call, dict)] if isinstance(calls, list) else []


def latest_call_output(target_result: Mapping[str, Any], task_name: str) -> dict[str, Any]:
    """Output of the target's last call of ``task_name``, empty when it did not succeed.

    This is the "latest by task" view the built-in steps' metrics use. It never
    falls back to an earlier call of the task when the last one failed.
    """
    for call in reversed(call_results(target_result)):
        if call.get("name") != task_name:
            continue
        if call.get("status") != SUCCESS:
            return {}
        output = call.get("output")
        return dict(output) if isinstance(output, dict) else {}
    return {}
