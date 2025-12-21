"""Pydantic models for execution state.

This module defines structured models for execution metadata,
replacing untyped dict[str, Any] with proper type annotations.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class StageResult(BaseModel):
    """Result of a calibration stage execution."""

    result: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime | None = None


class ExecutionNote(BaseModel):
    """Structured note for execution metadata.

    This replaces the untyped dict[str, Any] note with a proper model.
    All fields are optional for backwards compatibility.

    Attributes:
        stage_results: Results from each calibration stage
        github_push_results: Results from GitHub push operations
        config_commit_id: Git commit ID of the config used
        extra: Additional unstructured data for extensibility
    """

    stage_results: dict[str, StageResult] = Field(default_factory=dict)
    github_push_results: dict[str, Any] = Field(default_factory=dict)
    config_commit_id: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)

    def record_stage(self, stage_name: str, result: dict[str, Any], timestamp: datetime) -> None:
        """Record a stage result.

        Args:
            stage_name: Name of the stage
            result: Stage result data
            timestamp: Timestamp when the stage was recorded
        """
        self.stage_results[stage_name] = StageResult(result=result, timestamp=timestamp)

    def get_stage(self, stage_name: str) -> StageResult | None:
        """Get a stage result.

        Args:
            stage_name: Name of the stage

        Returns:
            Stage result or None if not found
        """
        return self.stage_results.get(stage_name)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for persistence.

        Returns:
            Dictionary representation compatible with legacy format
        """
        data: dict[str, Any] = {}

        if self.stage_results:
            data["stage_results"] = {
                name: {"result": sr.result, "timestamp": sr.timestamp}
                for name, sr in self.stage_results.items()
            }

        if self.github_push_results:
            data["github_push_results"] = self.github_push_results

        if self.config_commit_id:
            data["config_commit_id"] = self.config_commit_id

        # Merge extra fields
        data.update(self.extra)

        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ExecutionNote":
        """Create from dictionary (legacy format).

        Args:
            data: Dictionary data (may be None or legacy format)

        Returns:
            ExecutionNote instance
        """
        if not data:
            return cls()

        stage_results: dict[str, StageResult] = {}
        raw_stages = data.get("stage_results", {})
        for name, sr_data in raw_stages.items():
            if isinstance(sr_data, dict):
                stage_results[name] = StageResult(
                    result=sr_data.get("result", {}),
                    timestamp=sr_data.get("timestamp", ""),
                )

        # Collect extra fields (anything not in known fields)
        known_fields = {"stage_results", "github_push_results", "config_commit_id"}
        extra = {k: v for k, v in data.items() if k not in known_fields}

        return cls(
            stage_results=stage_results,
            github_push_results=data.get("github_push_results", {}),
            config_commit_id=data.get("config_commit_id"),
            extra=extra,
        )
