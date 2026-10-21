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
    return {"name": name, "category": "one_qubit_coarse", "background": summary}


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


def test_previous_format_entries_still_load(knowledge_repo: Path) -> None:
    (knowledge_repo / "task-knowledge.json").write_text(
        json.dumps(
            {
                "CheckRabi": {
                    "name": "CheckRabi",
                    "category": "one_qubit_coarse",
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
    assert knowledge.figures[0].path == "./rabi.png"
    assert knowledge.examples == []


def test_prompt_rendering_and_example_labels() -> None:
    knowledge = tk.TaskKnowledge(
        name="CheckT1",
        background="Measures T1.\n\nExponential decay; extract t1 (μs).",
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
    assert prompt == "## Experiment: CheckT1\nMeasures T1.\n\nExponential decay; extract t1 (μs)."
    assert "### Labeled examples" not in prompt
    assert "Short T1 (suboptimal, pass_with_note): T1 = 14 μs" in knowledge.to_prompt(
        include_examples=True
    )
    assert knowledge.examples[0].label() == (
        "Outcome: suboptimal\nFit quality: good\nVerdict: pass_with_note\nT1 = 14 μs with a clean fit."
    )


def test_category_is_the_calibtasks_package_of_the_knowledge_entry(knowledge_repo: Path) -> None:
    assert tk.get_task_category_dir("CheckT1") == "one_qubit_coarse"
    assert tk.get_task_category_dir("Nope") == "other"


CHECK_RABI_INDEX = """Measures Rabi oscillation to extract drive amplitude, frequency, and IQ-plane parameters.

Rabi oscillation parameters: amplitude, frequency (drive strength), phase, offset.

## Expected plot

Damped sinusoidal oscillation of the rotated IQ signal vs pulse duration. Frequency gives Ω_R,
envelope gives the decay time τ. A good result: clear sinusoidal oscillation with high contrast
and slow decay envelope.

Axes: Pulse duration (ns), Rotated IQ signal (arb. units).

## Common failures

- Low contrast (<70%) — small oscillation amplitude, large DC offset; next: check readout fidelity.
- Rapid decay — oscillation amplitude drops quickly with pulse duration; next: check T1.
- Short T1 (<20 μs): the curve flattens well before the maximum delay; check TLS
  defects near the qubit frequency.

## Parameters to extract

- rabi_frequency: Rabi oscillation frequency (MHz)
- rabi_amplitude: Rabi oscillation amplitude (a.u.)
- contrast_ok: whether the contrast is sufficient (bool)
- oscillation_count: number of visible periods
"""


def test_reference_is_derived_from_the_index_template() -> None:
    reference = tk.TaskKnowledge(name="CheckRabi", background=CHECK_RABI_INDEX).reference()

    assert reference.background == (
        "This is a CheckRabi experiment: Measures Rabi oscillation to extract drive amplitude, "
        "frequency, and IQ-plane parameters. Damped sinusoidal oscillation of the rotated IQ "
        "signal vs pulse duration. Frequency gives Ω_R, envelope gives the decay time τ. A good "
        "result: clear sinusoidal oscillation with high contrast and slow decay envelope."
    )
    assert list(reference.statuses) == ["SUCCESS", "LOW_CONTRAST", "RAPID_DECAY", "SHORT_T1"]
    assert reference.statuses["SUCCESS"] == (
        "clear sinusoidal oscillation with high contrast and slow decay envelope"
    )
    assert reference.statuses["LOW_CONTRAST"] == "small oscillation amplitude, large DC offset"
    assert reference.statuses["RAPID_DECAY"] == (
        "oscillation amplitude drops quickly with pulse duration"
    )
    assert reference.statuses["SHORT_T1"] == "the curve flattens well before the maximum delay"
    assert reference.parameters == {
        "rabi_frequency": "float",
        "rabi_amplitude": "float",
        "contrast_ok": "true | false",
        "oscillation_count": "int",
    }
    assert reference.guidance == []
    assert reference.range_format is None


def test_reference_without_template_sections_still_has_a_background_and_success() -> None:
    reference = tk.TaskKnowledge(name="LinkUp", background="Links the boxes up.").reference()

    assert reference.background == "This is a LinkUp experiment: Links the boxes up."
    assert reference.statuses == {"SUCCESS": "The result matches the expected plot"}
    assert reference.parameters == {}

    bare = tk.derive_reference("", "")
    assert bare.background == "This is a calibration experiment."


def test_example_demonstration_fields_are_optional_and_labeled() -> None:
    example = tk.KnowledgeExample(
        id="e1",
        title="Short T1",
        outcome="suboptimal",
        status="SHORT_T1",
        suggested_range="(0, 50) [μs]",
        parameters='{"t1": 14.2}',
        diagnosis="T1 = 14 μs.",
    )

    assert example.label() == "Outcome: suboptimal\nStatus: SHORT_T1\nT1 = 14 μs."
    assert (example.status, example.suggested_range, example.parameters) == (
        "SHORT_T1",
        "(0, 50) [μs]",
        '{"t1": 14.2}',
    )
    assert tk.KnowledgeExample(id="e2", title="t", outcome="expected").status == ""
