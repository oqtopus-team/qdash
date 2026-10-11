"""Tests for TaskService."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from qdash.api.services.task_service import TaskService
from qdash.datamodel.task_knowledge import (
    KnowledgeExample,
    KnowledgeFigure,
    KnowledgeOutcome,
    KnowledgeParameter,
    TaskKnowledge,
)


def _service() -> TaskService:
    return TaskService(task_definition_repository=MagicMock())


PNG = b"\x89PNG\r\n\x1a\n"


def _knowledge_repo(tmp_path: Path) -> Path:
    """A knowledge checkout with one task: index.md, an expected figure, one example."""
    task_dir = tmp_path / "task-knowledge" / "cw-characterization" / "CheckQubitSpectroscopy"
    (task_dir / "examples" / "figures").mkdir(parents=True)
    (task_dir / "index.md").write_text(
        "# CheckQubitSpectroscopy\n\nBackground.\n\n## Expected plot\n\n"
        "![overview](./figures/overview.png)\n",
        encoding="utf-8",
    )
    (task_dir / "figures").mkdir()
    (task_dir / "figures" / "overview.png").write_bytes(PNG)
    (task_dir / "examples" / "figures" / "q12_raw.jpg").write_bytes(b"\xff\xd8raw")
    return tmp_path


def _qubit_knowledge() -> TaskKnowledge:
    return TaskKnowledge(
        name="CheckQubitSpectroscopy",
        category="cw-characterization",
        background="Background.\n\nMore background.",
        expected_plot="A clear f01 peak.",
        expected_figures=[KnowledgeFigure(alt="overview", path="figures/overview.png")],
        outcomes=[
            KnowledgeOutcome(outcome="expected", description="sharp peak"),
            KnowledgeOutcome(outcome="apparatus", description="flat trace"),
        ],
        parameters=[KnowledgeParameter(name="qubit_frequency", description="f01 (GHz)")],
        examples=[
            KnowledgeExample(
                id="2026-05-05_weak-f12",
                title="Weak f12 support",
                outcome="suboptimal",
                verdict="pass_with_note",
                figures=[KnowledgeFigure(alt="qid 12 raw", path="examples/figures/q12_raw.jpg")],
                diagnosis="The f01 peak is supported; the f12 marker is weak.",
            )
        ],
    )


def test_get_task_knowledge_markdown_inlines_figures_from_the_checkout(tmp_path: Path) -> None:
    repo = _knowledge_repo(tmp_path)
    with (
        patch("qdash.api.services.task_service._lookup_knowledge", return_value=_qubit_knowledge()),
        patch(
            "qdash.datamodel.task_knowledge._resolve_repo_dir", return_value=repo / "task-knowledge"
        ),
    ):
        markdown = _service().get_task_knowledge_markdown("CheckQubitSpectroscopy")

    assert markdown.startswith("# CheckQubitSpectroscopy")
    assert "![overview](data:image/png;base64," in markdown
    assert markdown.count("![overview]") == 1


def test_get_task_knowledge_markdown_falls_back_to_the_rendered_prompt(tmp_path: Path) -> None:
    with (
        patch("qdash.api.services.task_service._lookup_knowledge", return_value=_qubit_knowledge()),
        patch("qdash.datamodel.task_knowledge._resolve_repo_dir", return_value=tmp_path),
    ):
        markdown = _service().get_task_knowledge_markdown("CheckQubitSpectroscopy")

    assert "## Experiment: CheckQubitSpectroscopy" in markdown
    assert "### Outcomes" in markdown
    assert "- apparatus: flat trace" in markdown


def test_get_task_knowledge_response_inlines_example_figures(tmp_path: Path) -> None:
    repo = _knowledge_repo(tmp_path)
    with (
        patch("qdash.api.services.task_service._lookup_knowledge", return_value=_qubit_knowledge()),
        patch(
            "qdash.datamodel.task_knowledge._resolve_repo_dir", return_value=repo / "task-knowledge"
        ),
    ):
        response = _service().get_task_knowledge("CheckQubitSpectroscopy")

    assert response.expected_figures[0].mime_type == "image/png"
    assert response.expected_figures[0].base64_data
    example = response.examples[0]
    assert example.verdict == "pass_with_note"
    assert example.figures[0].mime_type == "image/jpeg"
    assert example.figures[0].path == "examples/figures/q12_raw.jpg"
    assert "### Labeled examples" not in response.prompt_text
    assert "- qubit_frequency: f01 (GHz)" in response.prompt_text


def test_list_task_knowledge_counts_outcomes_examples_and_figures() -> None:
    with patch(
        "qdash.api.services.task_service._list_all_knowledge", return_value=[_qubit_knowledge()]
    ):
        listing = _service().list_task_knowledge()

    item = listing.items[0]
    assert item.summary == "Background."
    assert (item.outcome_count, item.example_count, item.figure_count) == (2, 1, 2)
    assert listing.categories["cw-characterization"] == "CW Characterization"


def test_figure_paths_cannot_escape_the_task_directory(tmp_path: Path) -> None:
    repo = _knowledge_repo(tmp_path)
    (repo / "secret.png").write_bytes(PNG)
    with patch(
        "qdash.datamodel.task_knowledge._resolve_repo_dir", return_value=repo / "task-knowledge"
    ):
        knowledge = _qubit_knowledge()
        assert knowledge.load_figure("../../secret.png") is None
        assert knowledge.load_figure("figures/overview.png") == (PNG, "image/png")
