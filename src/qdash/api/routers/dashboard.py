"""Dashboard-level operational insight endpoints."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from qdash.api.lib.project import ProjectContext, get_project_context
from qdash.api.schemas.dashboard import (
    DashboardAiInsightsResponse,
    DashboardInsight,
    DashboardInsightSuppressed,
)
from qdash.datamodel.note import NoteModel
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

router = APIRouter()

AI_REVIEW_RE = re.compile(r"^## AI review\n\n(?P<body>.*?)(?=\n\n---\n\n|$)", re.DOTALL)


@router.get(
    "/chips/{chip_id}/ai-insights",
    summary="Generate dashboard-level AI insight candidates",
    operation_id="getDashboardAiInsights",
    response_model=DashboardAiInsightsResponse,
)
def get_dashboard_ai_insights(
    chip_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    task_name: Annotated[str | None, Query(description="Optional task-name filter")] = None,
    latest_only: Annotated[
        bool,
        Query(description="If true, use only the latest result per task and target"),
    ] = True,
    selection_mode: Annotated[
        str | None,
        Query(description="Dashboard selection mode; accepted for filter-state traceability"),
    ] = None,
    start_at: Annotated[
        str | None,
        Query(description="Dashboard lower time bound; accepted for filter-state traceability"),
    ] = None,
    end_at: Annotated[
        str | None,
        Query(description="Dashboard upper time bound; accepted for filter-state traceability"),
    ] = None,
) -> DashboardAiInsightsResponse:
    """Return compact operational insights for the dashboard.

    The first implementation is deterministic: it extracts high-signal patterns
    from persisted AI review notes and task-result metadata. A later LLM
    synthesis layer can consume the same structured candidate contract.
    """
    _ = (selection_mode, start_at, end_at)
    docs = _load_reviewed_task_results(
        project_id=ctx.project_id,
        chip_id=chip_id,
        task_name=task_name,
        latest_only=latest_only,
    )
    records = [_parse_review_record(doc) for doc in docs]
    insights = _build_insights(records)
    routine_pass_count = sum(
        1 for record in records if record["decision"] in {"PASS", "PASS_WITH_NOTE"}
    )
    summary = _summary(chip_id, records, insights)
    return DashboardAiInsightsResponse(
        chip_id=chip_id,
        summary=summary,
        insights=insights[:5],
        suppressed=DashboardInsightSuppressed(
            routine_pass_count=routine_pass_count,
            reason=(
                "Routine PASS/PASS_WITH_NOTE task review results are suppressed unless they "
                "form a chip-level pattern."
            ),
        ),
    )


def _load_reviewed_task_results(
    *,
    project_id: str,
    chip_id: str,
    task_name: str | None,
    latest_only: bool,
) -> list[TaskResultHistoryDocument]:
    query: dict[str, Any] = {
        "project_id": project_id,
        "chip_id": chip_id,
        "$or": [
            {"ai_review.status": {"$exists": True, "$ne": ""}},
            {"ai_review_note.content": {"$regex": "^## AI review"}},
            {"user_note.content": {"$regex": "^## AI review"}},
        ],
    }
    if task_name:
        query["name"] = task_name
    docs = list(TaskResultHistoryDocument.find(query).run())
    docs.sort(key=lambda d: d.start_at or datetime.min, reverse=True)
    if not latest_only:
        return docs

    latest: dict[tuple[str, str], TaskResultHistoryDocument] = {}
    for doc in docs:
        key = (doc.name, doc.qid)
        current = latest.get(key)
        if current is None:
            latest[key] = doc
            continue
        if _has_terminal_review_signal(current):
            continue
        if _has_terminal_review_signal(doc):
            latest[key] = doc
    return list(latest.values())


def _has_terminal_review_signal(doc: TaskResultHistoryDocument) -> bool:
    content = _ai_review_note_content(doc)
    return bool(
        AI_REVIEW_RE.search(content)
        or getattr(doc.ai_review, "status", "") in {"completed", "failed"}
    )


def _parse_review_record(doc: TaskResultHistoryDocument) -> dict[str, Any]:
    content = _ai_review_note_content(doc)
    match = AI_REVIEW_RE.search(content)
    body = match.group("body") if match else content
    decision = _field(body, "Decision")
    if not decision and "必要なレビュー・ブロック" in body:
        decision = "FORMAT_ERROR"
    if not decision and doc.ai_review.status == "failed":
        decision = "FORMAT_ERROR"
    decision = decision or "UNKNOWN"
    labels = _field(body, "Suggested labels")
    return {
        "task_id": doc.task_id,
        "task_name": doc.name,
        "qid": doc.qid,
        "target": _format_target(doc.qid),
        "execution_id": doc.execution_id,
        "status": doc.ai_review.status,
        "model": "/".join(
            part for part in [doc.ai_review.model_provider, doc.ai_review.model_name] if part
        ),
        "decision": decision,
        "human_label": _field(body, "Human label suggestion"),
        "accepted_parameters": _field(body, "Accepted parameter(s)"),
        "needs_review": _field(body, "Needs review"),
        "primary_reason": _field(body, "Primary reason"),
        "suggested_labels": labels,
        "recommended_action": _field(body, "Recommended action"),
        "is_missing_output": "No f01 output parameter" in body
        or ("no_signal" in labels.lower() and "Deterministic safety guard" in body),
        "is_format_error": decision == "FORMAT_ERROR" or "model_format_error" in body,
    }


def _ai_review_note_content(doc: TaskResultHistoryDocument) -> str:
    ai_review_note = getattr(doc, "ai_review_note", NoteModel())
    return ai_review_note.content or doc.user_note.content or ""


def _field(text: str, name: str) -> str:
    pattern = re.compile(
        rf"^-\s*{re.escape(name)}:\s*`?(?P<value>.+?)`?\s*$",
        re.MULTILINE,
    )
    match = pattern.search(text)
    if not match:
        return ""
    return match.group("value").strip().strip("`")


def _format_target(qid: str) -> str:
    if not qid:
        return "unknown"
    return qid if qid.startswith("Q") else f"Q{qid}"


def _qid_int(record: dict[str, Any]) -> int | None:
    qid = str(record.get("qid") or "").removeprefix("Q")
    try:
        return int(qid)
    except ValueError:
        return None


def _qid_sort_key(record: dict[str, Any]) -> int:
    qid = _qid_int(record)
    return qid if qid is not None else 10**9


def _mux_key(record: dict[str, Any]) -> str:
    qid = _qid_int(record)
    if qid is None:
        return "unknown"
    return f"MUX {qid // 4}"


def _targets(records: list[dict[str, Any]]) -> list[str]:
    return [
        record["target"]
        for record in sorted(
            records,
            key=_qid_sort_key,
        )
    ]


def _build_insights(records: list[dict[str, Any]]) -> list[DashboardInsight]:
    insights: list[DashboardInsight] = []

    missing = [record for record in records if record["is_missing_output"]]
    if missing:
        by_mux: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for record in missing:
            by_mux[_mux_key(record)].append(record)
        for mux, group in sorted(by_mux.items(), key=lambda item: item[0]):
            if len(group) < 2:
                continue
            insights.append(
                DashboardInsight(
                    title=f"{mux} has a repeated missing-output-parameter pattern",
                    severity="warning",
                    affected_targets=_targets(group),
                    category="data_consistency",
                    evidence=[
                        f"{len(group)} task results were guarded before VLM review because no persisted f01 output parameter was found.",
                        "Treat this as a data/persistence consistency signal unless the plots also show no signal.",
                    ],
                    recommended_action=(
                        "Inspect task-result output_parameters and figure/export consistency before "
                        "treating these as independent spectroscopy failures."
                    ),
                    confidence="high",
                )
            )

    format_errors = [record for record in records if record["is_format_error"]]
    if format_errors:
        insights.append(
            DashboardInsight(
                title="Some task reviews failed because the local model output was not parseable",
                severity="info",
                affected_targets=_targets(format_errors),
                category="model_failure",
                evidence=[
                    f"{len(format_errors)} task result(s) were classified as format/model failures.",
                    "These should be separated from calibration-quality failures.",
                ],
                recommended_action=(
                    "Rerun AI review for these targets or inspect parser fallback logs before "
                    "counting them as calibration review cases."
                ),
                confidence="high",
            )
        )

    review_like = [
        record
        for record in records
        if record["decision"] in {"REVIEW", "FAIL", "FORMAT_ERROR"}
        and not record["is_missing_output"]
        and not record["is_format_error"]
    ]
    by_task = defaultdict(list)
    for record in review_like:
        by_task[record["task_name"]].append(record)
    for task, group in sorted(by_task.items(), key=lambda item: len(item[1]), reverse=True):
        if len(group) < 2:
            continue
        decisions = Counter(record["decision"] for record in group)
        insights.append(
            DashboardInsight(
                title=f"{task} has clustered review decisions",
                severity="warning",
                affected_targets=_targets(group),
                category="review_cluster",
                evidence=[
                    ", ".join(f"{decision}: {count}" for decision, count in decisions.items()),
                    "The grouped pattern is more useful than reading each task note separately.",
                ],
                recommended_action=(
                    "Open the affected task results as a group and check whether they share a "
                    "common calibration, data, or model-failure cause."
                ),
                confidence="medium",
            )
        )

    failed_status = [
        record
        for record in records
        if record["status"] == "failed" and record["decision"] == "UNKNOWN"
    ]
    if failed_status:
        insights.append(
            DashboardInsight(
                title="Some AI review requests failed without a structured decision",
                severity="info",
                affected_targets=_targets(failed_status),
                category="model_failure",
                evidence=[f"{len(failed_status)} review request(s) have failed status."],
                recommended_action="Check model availability and retry these AI review requests.",
                confidence="medium",
            )
        )

    return _sort_insights(insights)


def _sort_insights(insights: list[DashboardInsight]) -> list[DashboardInsight]:
    severity_rank = {"critical": 0, "warning": 1, "info": 2}
    confidence_rank = {"high": 0, "medium": 1, "low": 2}
    return sorted(
        insights,
        key=lambda insight: (
            severity_rank[insight.severity],
            confidence_rank[insight.confidence],
            -len(insight.affected_targets),
        ),
    )


def _summary(
    chip_id: str,
    records: list[dict[str, Any]],
    insights: list[DashboardInsight],
) -> str:
    if not records:
        return f"No AI review records were found for {chip_id}."
    if not insights:
        return (
            f"No high-signal dashboard insight was detected from {len(records)} "
            "AI review record(s)."
        )
    return (
        f"Detected {len(insights)} dashboard insight candidate(s) from "
        f"{len(records)} AI review record(s) on {chip_id}."
    )
