"""Planner-less evaluation of one task result through the Pi Agent Runtime.

The runtime's `/evaluate` route runs the same two tools the chat planner would
(`qdash_build_qcal_evidence`, then `qcal_evaluate`) for one task result and
returns the record of what the evaluation model saw and answered.
"""

from __future__ import annotations

import logging
from typing import Any, cast

import httpx

from qdash.api.services.pi_chat_service import RUNTIME_URL, QDashAuth, _runtime_headers

logger = logging.getLogger(__name__)

# The calibration VLM answers in tens of seconds; connect and write stay short.
EVALUATE_TIMEOUT = httpx.Timeout(connect=10.0, read=600.0, write=30.0, pool=10.0)


class EvaluationRuntimeError(RuntimeError):
    """The runtime could not evaluate the task result."""

    def __init__(self, stage: str, detail: str) -> None:
        super().__init__(f"{stage}: {detail}")
        self.stage = stage
        self.detail = detail


async def evaluate_task_result(
    task_id: str,
    *,
    auth: QDashAuth,
    question: str | None = None,
    max_figures: int | None = None,
    mode: str = "direct",
    model: dict[str, str] | None = None,
    thinking_level: str | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, Any]:
    """Ask the runtime to evaluate one task result as the given user.

    `mode` is "direct" (the evidence and evaluation tools run as such) or
    "planner" (a planner turn on `model` calls them). Returns the runtime's
    record (task, figures, knowledge, evaluation, evaluator, planner). Raises
    `EvaluationRuntimeError` with the failing stage when the runtime answered
    with an error, and `httpx.HTTPError` when it could not be reached.
    """
    payload: dict[str, Any] = {"task_id": task_id, "mode": mode}
    if question:
        payload["question"] = question
    if max_figures:
        payload["max_figures"] = max_figures
    if model:
        # The planner in planner mode; in direct mode only pi-qcaleval's fallback.
        payload["model"] = {"provider": model["provider"], "name": model["name"]}
    if thinking_level:
        payload["thinking_level"] = thinking_level
    # trust_env=False: the runtime is an internal service, so an ambient
    # HTTP(S)_PROXY must not be applied to it.
    async with httpx.AsyncClient(
        timeout=EVALUATE_TIMEOUT, trust_env=False, transport=transport
    ) as client:
        response = await client.post(
            f"{RUNTIME_URL}/evaluate",
            headers={**_runtime_headers(), **auth.headers()},
            json=payload,
        )
    if response.status_code == httpx.codes.OK:
        return cast("dict[str, Any]", response.json())
    try:
        body = response.json()
    except ValueError:
        body = {}
    stage = str(body.get("stage") or "runtime")
    detail = str(body.get("error") or f"HTTP {response.status_code}")
    raise EvaluationRuntimeError(stage, detail)
