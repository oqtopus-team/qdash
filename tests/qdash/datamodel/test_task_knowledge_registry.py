"""The task knowledge registry follows task-knowledge.json on disk."""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING

import pytest

from qdash.datamodel import task_knowledge as tk

if TYPE_CHECKING:
    from pathlib import Path


def _entry(name: str, summary: str) -> dict[str, object]:
    return {"name": name, "category": "td-characterization", "background": summary}


@pytest.fixture
def knowledge_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    repo = tmp_path / "task-knowledge"
    repo.mkdir()
    (repo / "task-knowledge.json").write_text(
        json.dumps({"CheckT1": _entry("CheckT1", "before")}), encoding="utf-8"
    )
    monkeypatch.setattr(
        "qdash.common.config.loader.ConfigLoader.get_config_dir", classmethod(lambda cls: tmp_path)
    )
    monkeypatch.setattr(tk, "_REGISTRY_CACHE", (None, {}))
    return repo


def test_registry_reloads_when_the_json_changes(knowledge_repo: Path) -> None:
    before = tk.get_task_knowledge("CheckT1")
    assert before is not None
    assert before.summary == "before"

    json_path = knowledge_repo / "task-knowledge.json"
    json_path.write_text(
        json.dumps({"CheckT1": _entry("CheckT1", "after"), "CheckT2": _entry("CheckT2", "new")}),
        encoding="utf-8",
    )
    # Same second as the first write is possible; make the identity differ regardless.
    stat = json_path.stat()
    os.utime(json_path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))

    after = tk.get_task_knowledge("CheckT1")
    assert after is not None
    assert after.summary == "after"
    assert sorted(k.name for k in tk.list_all_task_knowledge()) == ["CheckT1", "CheckT2"]


def test_registry_is_cached_while_the_json_is_unchanged(knowledge_repo: Path) -> None:
    first = tk.list_all_task_knowledge()[0]
    assert tk.get_task_knowledge("CheckT1") is first


def test_regenerate_runs_the_repository_generator(knowledge_repo: Path) -> None:
    (knowledge_repo / "generate.py").write_text(
        "import json, sys\n"
        "out = sys.argv[sys.argv.index('--output') + 1]\n"
        "json.dump({'CheckT1': "
        + json.dumps(_entry("CheckT1", "generated"))
        + "}, open(out, 'w'))\n",
        encoding="utf-8",
    )

    output = tk.regenerate_task_knowledge_json(knowledge_repo)

    assert output == knowledge_repo / "task-knowledge.json"
    assert json.loads(output.read_text())["CheckT1"]["background"] == "generated"


def test_regenerate_reports_a_failing_generator(knowledge_repo: Path) -> None:
    (knowledge_repo / "generate.py").write_text(
        "import sys; print('boom', file=sys.stderr); sys.exit(3)\n", encoding="utf-8"
    )

    with pytest.raises(RuntimeError, match="boom"):
        tk.regenerate_task_knowledge_json(knowledge_repo)


def test_regenerate_requires_the_generator(knowledge_repo: Path) -> None:
    with pytest.raises(RuntimeError, match=r"generate\.py not found"):
        tk.regenerate_task_knowledge_json(knowledge_repo)


def test_previous_format_entries_still_load(knowledge_repo: Path) -> None:
    (knowledge_repo / "task-knowledge.json").write_text(
        json.dumps(
            {
                "CheckRabi": {
                    "name": "CheckRabi",
                    "category": "td-characterization",
                    "summary": "Rabi oscillation.",
                    "what_it_measures": "Drive amplitude calibration.",
                    "physical_principle": "ignored",
                    "expected_result": {"description": "A damped cosine."},
                    "images": [
                        {"alt_text": "expected", "relative_path": "./rabi.png", "base64_data": "x"}
                    ],
                    "failure_modes": [{"severity": "critical", "description": "no oscillation"}],
                }
            }
        ),
        encoding="utf-8",
    )
    tk._REGISTRY_CACHE = (None, {})

    knowledge = tk.get_task_knowledge("CheckRabi")

    assert knowledge is not None
    assert knowledge.summary == "Rabi oscillation."
    assert knowledge.background == "Rabi oscillation.\n\nDrive amplitude calibration."
    assert knowledge.expected_plot == "A damped cosine."
    assert knowledge.expected_figures[0].path == "./rabi.png"
    assert knowledge.outcomes == []


def test_prompt_rendering_and_example_labels() -> None:
    knowledge = tk.TaskKnowledge(
        name="CheckT1",
        background="Measures T1.",
        expected_plot="Exponential decay.",
        outcomes=[tk.KnowledgeOutcome(outcome="expected", description="clean decay")],
        parameters=[tk.KnowledgeParameter(name="t1", description="T1 (μs)")],
        examples=[
            tk.KnowledgeExample(
                id="e1",
                title="Short T1",
                outcome="suboptimal",
                fit_quality="good",
                verdict="pass_with_note",
                diagnosis="T1 = 14 μs with a clean fit.",
            )
        ],
    )

    prompt = knowledge.to_prompt()
    assert prompt.splitlines()[0] == "## Experiment: CheckT1"
    assert "### Labeled examples" not in prompt
    assert "- t1: T1 (μs)" in prompt
    assert "Short T1 (suboptimal, pass_with_note): T1 = 14 μs" in knowledge.to_prompt(
        include_examples=True
    )
    assert knowledge.examples[0].label() == (
        "Outcome: suboptimal\nFit quality: good\nVerdict: pass_with_note\nT1 = 14 μs with a clean fit."
    )
