"""Tests for AI review evaluation capture and replay helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import patch

from qdash.copilot.config import AnalysisConfig, CopilotConfig, ModelConfig
from qdash.copilot.contracts import AnalysisContextResult, TaskAnalysisContext
from qdash.copilot.evals.ai_review import (
    AIReviewEvalSnapshot,
    AIReviewExpectedImage,
    AIReviewModelRef,
    AIReviewSourceRef,
    capture_ai_review_snapshot,
    run_ai_review_snapshot,
    write_ai_review_run_artifacts,
)

if TYPE_CHECKING:
    from pathlib import Path


def _config() -> CopilotConfig:
    return CopilotConfig(
        enabled=True,
        model=ModelConfig(provider="openai", name="gpt-4.1"),
        analysis_models=[ModelConfig(provider="openai", name="gpt-5.1", max_output_tokens=2048)],
        analysis=AnalysisConfig(
            enabled=True,
            ai_review_tasks=["CheckQubitSpectroscopy"],
            ai_review_message="Review this run carefully.",
        ),
    )


def _context(task_knowledge_prompt: str = "knowledge-v1") -> TaskAnalysisContext:
    return TaskAnalysisContext(
        task_knowledge_prompt=task_knowledge_prompt,
        chip_id="chip-1",
        qid="4",
        qubit_params={"t1": 12.3},
        input_parameters={"freq": 4.2},
        output_parameters={"coarse_qubit_frequency": {"value": 4.21}},
        run_parameters={},
    )


def _bundle(task_knowledge_prompt: str = "knowledge-v1") -> AnalysisContextResult:
    return AnalysisContextResult(
        context=_context(task_knowledge_prompt),
        image_base64=None,
        expected_images=[("abc123", "expected image")],
        figure_paths=["/tmp/figure.png"],
    )


def _snapshot() -> AIReviewEvalSnapshot:
    return AIReviewEvalSnapshot(
        captured_at=datetime(2026, 5, 14, tzinfo=UTC),
        source=AIReviewSourceRef(
            task_name="CheckQubitSpectroscopy",
            chip_id="chip-1",
            qid="4",
            task_id="task-1",
        ),
        selected_model=AIReviewModelRef(
            provider="openai",
            name="gpt-5.1",
            api_style="responses",
            max_output_tokens=2048,
        ),
        user_message="stored prompt",
        context=_context(),
        expected_images=[AIReviewExpectedImage(alt_text="expected image", base64_data="abc123")],
        figure_paths=["/tmp/figure.png"],
    )


def test_capture_ai_review_snapshot_uses_live_context() -> None:
    with patch("qdash.copilot.evals.ai_review.build_ai_review_context", return_value=_bundle()):
        snapshot = capture_ai_review_snapshot(
            task_name="CheckQubitSpectroscopy",
            chip_id="chip-1",
            qid="4",
            task_id="task-1",
            config=_config(),
        )

    assert snapshot.source.task_name == "CheckQubitSpectroscopy"
    assert snapshot.selected_model.name == "gpt-5.1"
    assert snapshot.context.task_knowledge_prompt == "knowledge-v1"
    assert snapshot.expected_images[0].alt_text == "expected image"
    assert "Review this run carefully." in snapshot.user_message


def test_run_ai_review_snapshot_frozen_uses_current_prompt_without_rebuild() -> None:
    with (
        patch(
            "qdash.copilot.evals.ai_review.render_ai_review_markdown",
            return_value="review markdown",
        ) as render,
        patch("qdash.copilot.evals.ai_review.build_ai_review_context") as rebuild,
    ):
        result = run_ai_review_snapshot(
            _snapshot(),
            mode="frozen",
            config=_config(),
        )

    rebuild.assert_not_called()
    render.assert_called_once()
    assert result.context.task_knowledge_prompt == "knowledge-v1"
    assert result.markdown == "review markdown"
    assert "Review this run carefully." in result.user_message


def test_run_ai_review_snapshot_rebuild_refreshes_context() -> None:
    refreshed_bundle = _bundle(task_knowledge_prompt="knowledge-v2")

    with (
        patch(
            "qdash.copilot.evals.ai_review.build_ai_review_context",
            return_value=refreshed_bundle,
        ) as rebuild,
        patch(
            "qdash.copilot.evals.ai_review.render_ai_review_markdown",
            return_value="review markdown",
        ),
    ):
        result = run_ai_review_snapshot(
            _snapshot(),
            mode="rebuild",
            config=_config(),
        )

    rebuild.assert_called_once()
    assert result.context.task_knowledge_prompt == "knowledge-v2"


def test_write_ai_review_run_artifacts_writes_expected_files(tmp_path: Path) -> None:
    with patch(
        "qdash.copilot.evals.ai_review.render_ai_review_markdown",
        return_value="review markdown",
    ):
        result = run_ai_review_snapshot(
            _snapshot(),
            mode="frozen",
            config=_config(),
        )

    output_dir = write_ai_review_run_artifacts(result, tmp_path / "run-1")

    assert (output_dir / "result.md").read_text(encoding="utf-8").strip() == "review markdown"
    assert "task_knowledge_prompt" in (output_dir / "context.json").read_text(encoding="utf-8")
    assert "selected_model" in (output_dir / "report.json").read_text(encoding="utf-8")
