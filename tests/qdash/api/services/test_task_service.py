"""Tests for TaskService."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from qdash.api.services.task_service import TaskService
from qdash.datamodel.task_knowledge import (
    ExpectedResult,
    FailureMode,
    KnowledgeCase,
    OutputParameterInfo,
    TaskKnowledge,
    TaskKnowledgeImage,
)


def _service() -> TaskService:
    return TaskService(task_definition_repository=MagicMock())


def _qubit_knowledge() -> TaskKnowledge:
    return TaskKnowledge(
        name="CheckQubitSpectroscopy",
        category="cw-characterization",
        summary="summary",
        what_it_measures="measure",
        physical_principle="principle",
        images=[
            TaskKnowledgeImage(
                alt_text="overview",
                relative_path="./figures/overview.png",
                section="Expected result",
                base64_data="b3ZlcnZpZXc=",
            )
        ],
        cases=[
            KnowledgeCase(
                title="Weak f12 support",
                images=[
                    TaskKnowledgeImage(
                        alt_text="qid 12 raw spectroscopy",
                        relative_path="./figures/q12_raw.png",
                        section="Figures",
                        base64_data="cmF3",
                    ),
                    TaskKnowledgeImage(
                        alt_text="qid 12 marked spectroscopy",
                        relative_path="./figures/q12_marked.jpg",
                        section="Figures",
                        base64_data="bWFya2Vk",
                    ),
                ],
            )
        ],
    )


def _resonator_knowledge() -> TaskKnowledge:
    return TaskKnowledge(
        name="CheckResonatorSpectroscopy",
        category="cw-characterization",
        summary="High-resolution 2D spectroscopy of all resonators in a readout multiplexer.",
        what_it_measures="Readout resonator frequencies within one MUX.",
        physical_principle="Resonator response is swept across frequency and power.",
        expected_result=ExpectedResult(
            description="A 2D map with annotated resonator peaks.",
            good_visual="Four clean resonator trajectories with stable peak assignment.",
        ),
        evaluation_criteria="All expected resonators should be visible and separable.",
        check_questions=["Are all expected resonators detected?"],
        failure_modes=[
            FailureMode(
                severity="critical",
                description="Missing resonator peaks",
                visual="Fewer peaks than expected",
                next_action="Widen the scan range",
            )
        ],
        output_parameters_info=[
            OutputParameterInfo(
                name="readout_frequency",
                description="Assigned resonator frequency for the qubit under review.",
            )
        ],
        analysis_guide=["Review the annotated 2D map."],
        images=[
            TaskKnowledgeImage(
                alt_text="Expected resonator map",
                relative_path="expected-map.png",
                section="expected_result",
                base64_data="task-image-b64",
            )
        ],
        review_markdown=(
            "# CheckResonatorSpectroscopy AI Review Guide\n\n"
            "Use REVIEW when peak assignment is ambiguous.\n\n"
            "![AI review example](review.png)"
        ),
        review_images=[
            TaskKnowledgeImage(
                alt_text="AI review example",
                relative_path="review.png",
                section="review",
                base64_data="review-image-b64",
            )
        ],
        cases=[
            KnowledgeCase(
                title="Overlapping resonators in one MUX",
                severity="warning",
                human_review_decision="Escalate for human review.",
                boundary_criteria="Two resonators overlap near the assigned slot.",
                lesson_learned=["Peak overlap should block auto-pass."],
                images=[
                    TaskKnowledgeImage(
                        alt_text="Case overlap map",
                        relative_path="cases/overlap.png",
                        section="cases",
                        base64_data="case-image-b64",
                    )
                ],
            )
        ],
    )


def test_get_task_knowledge_markdown_embeds_referenced_and_case_images(tmp_path: Path) -> None:
    knowledge_dir = tmp_path / "task-knowledge"
    task_dir = knowledge_dir / "cw-characterization" / "CheckQubitSpectroscopy"
    task_dir.mkdir(parents=True)
    (task_dir / "index.md").write_text(
        "# CheckQubitSpectroscopy\n\n![overview](./figures/overview.png)\n",
        encoding="utf-8",
    )

    with (
        patch("qdash.api.services.task_service._lookup_knowledge", return_value=_qubit_knowledge()),
        patch("qdash.api.services.task_service.ConfigLoader.get_config_dir", return_value=tmp_path),
    ):
        markdown = _service().get_task_knowledge_markdown("CheckQubitSpectroscopy")

    assert "![overview](data:image/png;base64,b3ZlcnZpZXc=)" in markdown
    assert "## Past case figures" in markdown
    assert "### Weak f12 support" in markdown
    assert "![qid 12 raw spectroscopy](data:image/png;base64,cmF3)" in markdown
    assert "![qid 12 marked spectroscopy](data:image/jpeg;base64,bWFya2Vk)" in markdown
    assert markdown.count("![overview]") == 1


def test_get_task_knowledge_response_includes_case_images() -> None:
    with patch(
        "qdash.api.services.task_service._lookup_knowledge", return_value=_qubit_knowledge()
    ):
        response = _service().get_task_knowledge("CheckQubitSpectroscopy")

    assert response.cases[0].images[0].relative_path == "./figures/q12_raw.png"
    assert response.cases[0].images[0].base64_data == "cmF3"


def test_get_task_knowledge_markdown_falls_back_to_registry_prompt(tmp_path: Path) -> None:
    with (
        patch("qdash.api.services.task_service._lookup_knowledge", return_value=_qubit_knowledge()),
        patch("qdash.api.services.task_service.ConfigLoader.get_config_dir", return_value=tmp_path),
    ):
        markdown = _service().get_task_knowledge_markdown("CheckQubitSpectroscopy")

    assert "## Experiment: CheckQubitSpectroscopy" in markdown
    assert "## Reference figures" in markdown
    assert "## Past case figures" in markdown
    assert markdown.count("data:image/") == 3


def test_list_task_knowledge_sets_has_review_guide_from_markdown() -> None:
    knowledge = _resonator_knowledge()
    service = _service()

    with patch("qdash.api.services.task_service._list_all_knowledge", return_value=[knowledge]):
        response = service.list_task_knowledge()

    assert len(response.items) == 1
    assert response.items[0].name == "CheckResonatorSpectroscopy"
    assert response.items[0].has_analysis_guide is True
    assert response.items[0].has_review_guide is True
    assert response.items[0].case_count == 1
    assert response.items[0].image_count == 1


def test_get_task_knowledge_includes_review_prompt_and_case_images() -> None:
    knowledge = _resonator_knowledge()
    service = _service()

    with patch("qdash.api.services.task_service._lookup_knowledge", return_value=knowledge):
        response = service.get_task_knowledge("CheckResonatorSpectroscopy")

    assert response.review_markdown == knowledge.review_markdown
    assert response.review_images[0].base64_data == "review-image-b64"
    assert response.cases[0].images[0].base64_data == "case-image-b64"
    assert response.prompt_text
    assert "### AI review guidance" in response.review_prompt_text
    assert "Use REVIEW when peak assignment is ambiguous." in response.review_prompt_text
    assert "![AI review example]" not in response.review_prompt_text
