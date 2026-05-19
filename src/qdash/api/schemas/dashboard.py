"""Schemas for dashboard-level operational insights."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

InsightSeverity = Literal["info", "warning", "critical"]
InsightConfidence = Literal["low", "medium", "high"]
InsightCategory = Literal[
    "review_cluster",
    "model_failure",
    "data_consistency",
    "metric_outlier",
    "coverage_gap",
    "provenance_impact",
    "note_cluster",
    "other",
]


class DashboardInsight(BaseModel):
    """One operator-facing dashboard insight."""

    title: str
    severity: InsightSeverity
    affected_targets: list[str] = Field(default_factory=list)
    category: InsightCategory = "other"
    evidence: list[str] = Field(default_factory=list)
    recommended_action: str
    confidence: InsightConfidence = "medium"


class DashboardInsightSuppressed(BaseModel):
    """Summary of routine items intentionally omitted from the insight card."""

    routine_pass_count: int = 0
    reason: str = ""


class DashboardAiInsightsResponse(BaseModel):
    """Dashboard-level AI insight response."""

    chip_id: str
    summary: str
    insights: list[DashboardInsight] = Field(default_factory=list)
    suppressed: DashboardInsightSuppressed = Field(default_factory=DashboardInsightSuppressed)
