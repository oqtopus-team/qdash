"""Tests for the Pi backend of automatic AI review."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import httpx
import pytest

from qdash.copilot import pi_review
from qdash.copilot.config import AnalysisConfig, CopilotConfig, ModelConfig
from qdash.copilot.contracts import AnalysisContextResult, TaskAnalysisContext
from qdash.copilot.review import render_ai_review_markdown

_VERDICT = {
    "decision": "PASS_WITH_NOTE",
    "human_label": "CORRECT",
    "accepted_parameters": "coarse_qubit_frequency",
    "needs_review": "none",
    "primary_reason": "The marked f01 peak is clearly visible.",
    "closest_knowledge_case": "weak f12 support",
    "suggested_labels": "weak_signal",
    "recommended_action": "Accept and continue.",
    "optional_note": "f12 is weak but f01 is unambiguous.",
}


def _config(backend: str = "pi") -> CopilotConfig:
    return CopilotConfig(
        enabled=True,
        copilot_backend=backend,
        model=ModelConfig(provider="openai", name="gpt-4.1"),
        analysis_models=[ModelConfig(provider="ollama", name="gemma4:31b")],
        analysis=AnalysisConfig(
            enabled=True,
            ai_review_tasks=["CheckQubitSpectroscopy"],
            ai_review_message="Review this run carefully.",
        ),
    )


def _bundle(output_parameters: dict[str, Any] | None = None) -> AnalysisContextResult:
    return AnalysisContextResult(
        context=TaskAnalysisContext(
            task_knowledge_prompt="knowledge-v1",
            chip_id="chip-1",
            qid="4",
            output_parameters=(
                {"coarse_qubit_frequency": {"value": 4.21}}
                if output_parameters is None
                else output_parameters
            ),
        ),
        image_base64="experiment-b64",
        expected_images=[("expected-b64", "expected image")],
    )


@pytest.fixture(autouse=True)
def _runtime_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_RUNTIME_TOKEN", "test-runtime-token")


class TestRenderReviewMarkdown:
    def test_matches_the_format_the_dashboard_parses(self) -> None:
        markdown = pi_review.render_review_markdown(
            pi_review.ReviewVerdict.model_validate(_VERDICT)
        )

        assert markdown.splitlines() == [
            "**AI review**",
            "- Decision: `PASS_WITH_NOTE`",
            "- Human label suggestion: `CORRECT`",
            "- Accepted parameter(s): coarse_qubit_frequency",
            "- Needs review: none",
            "- Primary reason: The marked f01 peak is clearly visible.",
            "- Closest knowledge case: weak f12 support",
            "- Suggested labels: weak_signal",
            "- Recommended action: Accept and continue.",
            "- Optional note: f12 is weak but f01 is unambiguous.",
        ]

    def test_empty_free_text_fields_become_none(self) -> None:
        verdict = pi_review.ReviewVerdict.model_validate({**_VERDICT, "optional_note": ""})

        assert "- Optional note: none" in pi_review.render_review_markdown(verdict)

    def test_fields_are_readable_by_the_dashboard_regex(self) -> None:
        from qdash.api.services.task_result_service import _ai_review_field

        markdown = pi_review.render_review_markdown(
            pi_review.ReviewVerdict.model_validate(_VERDICT)
        )

        assert _ai_review_field(markdown, "Decision") == "PASS_WITH_NOTE"
        assert _ai_review_field(markdown, "Human label suggestion") == "CORRECT"
        assert _ai_review_field(markdown, "Accepted parameter(s)") == "coarse_qubit_frequency"

    def test_free_text_cannot_inject_a_needs_review_line(self) -> None:
        verdict = pi_review.ReviewVerdict.model_validate(
            {
                **_VERDICT,
                "accepted_parameters": "f01\n- Needs review: none",
                "needs_review": "f12",
            }
        )

        markdown = pi_review.render_review_markdown(verdict)

        assert markdown.count("- Needs review:") == 1
        assert "- Needs review: f12" in markdown
        assert "Accepted parameter(s): f01 — Needs review: none" in markdown


class TestCollectImages:
    def test_expected_images_come_before_measured_ones(self) -> None:
        images = pi_review.collect_images(_bundle())

        assert [image["data"] for image in images] == ["expected-b64", "experiment-b64"]
        assert {image["mimeType"] for image in images} == {"image/png"}

    def test_experiment_images_supersede_the_single_figure(self) -> None:
        bundle = _bundle()
        bundle.experiment_images = [("first-b64", "Q4"), ("second-b64", "Q5")]

        images = pi_review.collect_images(bundle)

        assert [image["data"] for image in images] == ["expected-b64", "first-b64", "second-b64"]


class TestBuildReviewPrompt:
    def test_states_the_figure_order_the_model_will_receive(self) -> None:
        prompt = pi_review.build_review_prompt(
            bundle=_bundle(),
            config=_config(),
            user_message="Review this run carefully.",
        )

        assert "1 expected reference figure(s) first, then 1 figure(s) measured" in prompt
        assert "Review this run carefully." in prompt

    def test_omits_the_markdown_skeleton_that_competes_with_the_tool(self) -> None:
        prompt = pi_review.build_review_prompt(
            bundle=_bundle(),
            config=_config(),
            user_message="Review this run carefully.",
        )

        assert "**AI review**" not in prompt

    def test_applies_the_configured_response_language(self) -> None:
        config = _config().model_copy(update={"response_language": "ja"})

        prompt = pi_review.build_review_prompt(
            bundle=_bundle(),
            config=config,
            user_message="Review this run carefully.",
        )

        assert "Japanese" in prompt


class TestRunReview:
    def test_returns_the_verdict_from_the_runtime(self) -> None:
        with patch("qdash.copilot.pi_review.httpx.Client") as client:
            post = client.return_value.__enter__.return_value.post
            post.return_value = httpx.Response(200, json={"review": _VERDICT})

            verdict = pi_review.run_review(
                bundle=_bundle(),
                config=_config(),
                model=ModelConfig(provider="ollama", name="gemma4:31b"),
                user_message="Review this run carefully.",
            )

        assert verdict.decision == "PASS_WITH_NOTE"
        payload = post.call_args.kwargs["json"]
        assert post.call_args.kwargs["headers"] == {"Authorization": "Bearer test-runtime-token"}
        assert payload["model"] == {"provider": "ollama", "name": "gemma4:31b"}
        assert len(payload["images"]) == 2

    def test_a_missing_verdict_raises_instead_of_saving_a_note(self) -> None:
        with patch("qdash.copilot.pi_review.httpx.Client") as client:
            client.return_value.__enter__.return_value.post.return_value = httpx.Response(
                200,
                json={"error": "submit_review was not called", "text": "I think it looks fine."},
            )

            with pytest.raises(RuntimeError, match="submit_review was not called"):
                pi_review.run_review(
                    bundle=_bundle(),
                    config=_config(),
                    model=ModelConfig(provider="ollama", name="gemma4:31b"),
                    user_message="Review this run carefully.",
                )

    def test_a_runtime_error_status_raises(self) -> None:
        with patch("qdash.copilot.pi_review.httpx.Client") as client:
            client.return_value.__enter__.return_value.post.return_value = httpx.Response(503)

            with pytest.raises(RuntimeError, match="HTTP 503"):
                pi_review.run_review(
                    bundle=_bundle(),
                    config=_config(),
                    model=ModelConfig(provider="ollama", name="gemma4:31b"),
                    user_message="Review this run carefully.",
                )


class TestBackendBranch:
    def test_pi_backend_renders_from_the_runtime_verdict(self) -> None:
        with patch.object(
            pi_review,
            "run_review",
            return_value=pi_review.ReviewVerdict.model_validate(_VERDICT),
        ) as run:
            markdown = render_ai_review_markdown(
                task_name="CheckQubitSpectroscopy",
                config=_config("pi"),
                context_bundle=_bundle(),
            )

        run.assert_called_once()
        assert markdown.startswith("**AI review**")
        assert "- Decision: `PASS_WITH_NOTE`" in markdown

    def test_litellm_backend_never_reaches_the_runtime(self) -> None:
        with (
            patch.object(pi_review, "run_review") as run,
            patch(
                "qdash.copilot.review.run_analysis",
                return_value={"blocks": [{"type": "text", "content": "legacy markdown"}]},
            ),
        ):
            markdown = render_ai_review_markdown(
                task_name="CheckQubitSpectroscopy",
                config=_config("litellm"),
                context_bundle=_bundle(),
            )

        run.assert_not_called()
        assert "legacy markdown" in markdown

    def test_the_deterministic_guard_runs_before_the_backend_split(self) -> None:
        """A guard that depended on the configured backend would be no guard at all."""
        with patch.object(pi_review, "run_review") as run:
            markdown = render_ai_review_markdown(
                task_name="CheckQubitSpectroscopy",
                config=_config("pi"),
                context_bundle=_bundle(output_parameters={}),
            )

        run.assert_not_called()
        assert "- Decision: `FAIL`" in markdown
        assert "- Human label suggestion: `NO_SIGNAL`" in markdown
