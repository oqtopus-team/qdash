"""Tests for TaskService."""

from pathlib import Path
from unittest.mock import patch

from qdash.api.services.task_service import TaskService
from qdash.datamodel.task_knowledge import KnowledgeCase, TaskKnowledge, TaskKnowledgeImage


def _knowledge() -> TaskKnowledge:
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


def test_get_task_knowledge_markdown_embeds_referenced_and_case_images(tmp_path: Path) -> None:
    knowledge_dir = tmp_path / "task-knowledge"
    task_dir = knowledge_dir / "cw-characterization" / "CheckQubitSpectroscopy"
    task_dir.mkdir(parents=True)
    (task_dir / "index.md").write_text(
        "# CheckQubitSpectroscopy\n\n![overview](./figures/overview.png)\n",
        encoding="utf-8",
    )

    with (
        patch("qdash.api.services.task_service._lookup_knowledge", return_value=_knowledge()),
        patch("qdash.api.services.task_service.ConfigLoader.get_config_dir", return_value=tmp_path),
    ):
        markdown = TaskService(task_definition_repository=None).get_task_knowledge_markdown(
            "CheckQubitSpectroscopy"
        )

    assert "![overview](data:image/png;base64,b3ZlcnZpZXc=)" in markdown
    assert "## Past case figures" in markdown
    assert "### Weak f12 support" in markdown
    assert "![qid 12 raw spectroscopy](data:image/png;base64,cmF3)" in markdown
    assert "![qid 12 marked spectroscopy](data:image/jpeg;base64,bWFya2Vk)" in markdown
    assert markdown.count("![overview]") == 1


def test_get_task_knowledge_response_includes_case_images() -> None:
    with patch("qdash.api.services.task_service._lookup_knowledge", return_value=_knowledge()):
        response = TaskService(task_definition_repository=None).get_task_knowledge(
            "CheckQubitSpectroscopy"
        )

    assert response.cases[0].images[0].relative_path == "./figures/q12_raw.png"
    assert response.cases[0].images[0].base64_data == "cmF3"


def test_get_task_knowledge_markdown_falls_back_to_registry_prompt(tmp_path: Path) -> None:
    with (
        patch("qdash.api.services.task_service._lookup_knowledge", return_value=_knowledge()),
        patch("qdash.api.services.task_service.ConfigLoader.get_config_dir", return_value=tmp_path),
    ):
        markdown = TaskService(task_definition_repository=None).get_task_knowledge_markdown(
            "CheckQubitSpectroscopy"
        )

    assert "## Experiment: CheckQubitSpectroscopy" in markdown
    assert "## Reference figures" in markdown
    assert "## Past case figures" in markdown
    assert markdown.count("data:image/") == 3
