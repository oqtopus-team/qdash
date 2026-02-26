"""Structured domain knowledge model for calibration tasks.

Provides a ``TaskKnowledge`` Pydantic model and a central registry
(``TASK_KNOWLEDGE_REGISTRY``) that maps task class names to their
knowledge entries.

Knowledge is loaded from ``config/task-knowledge/task-knowledge.json``
(cloned knowledge repo), which is generated from Markdown files by
``scripts/generate_task_knowledge.py`` (run via ``task knowledge``).

The registry lives in ``datamodel`` so that both the API container and
the workflow container can access it without cross-importing.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class TaskKnowledgeImage(BaseModel):
    """Image reference extracted from a Markdown knowledge file."""

    alt_text: str = Field(description="Alt text from ![alt](path)")
    relative_path: str = Field(description="Relative path from the markdown file")
    section: str = Field(description="H2 section where the image was found")
    base64_data: str = Field(default="", description="Base64-encoded image data")


class RelatedContextItem(BaseModel):
    """Declarative specification for additional data to load during analysis.

    Parsed from ``## Related context`` section in Markdown knowledge files.
    """

    type: str = Field(description="Context type: 'history' | 'neighbor_qubits' | 'coupling'")
    params: list[str] = Field(default_factory=list, description="Parameter names to extract")
    last_n: int = Field(default=5, description="Number of recent results (for history type)")


class ExpectedResult(BaseModel):
    """Structured description of the expected experimental result."""

    description: str = Field(
        default="", description="Natural-language description of expected result"
    )
    result_type: str = Field(
        default="",
        description="Result type: decay_curve|oscillation|2d_map|histogram|scatter_plot|peak_curve|scalar_metric",
    )
    x_axis: str = Field(default="", description="X-axis label and unit")
    y_axis: str = Field(default="", description="Y-axis label and unit")
    z_axis: str = Field(default="", description="Z-axis label and unit (for 2D maps)")
    fit_model: str = Field(default="", description="Fitting model equation (if applicable)")
    typical_range: str = Field(default="", description="Typical value range for the metric")
    good_visual: str = Field(default="", description="Visual characteristics of a good result")


class FailureMode(BaseModel):
    """Structured failure pattern with severity and remediation info."""

    severity: str = Field(description="Severity level: 'critical', 'warning', or 'info'")
    description: str = Field(description="Description of the failure pattern")
    cause: str = Field(default="", description="Root cause explanation")
    visual: str = Field(default="", description="Visual characteristics in the result graph")
    next_action: str = Field(default="", description="Recommended next action")


class OutputParameterInfo(BaseModel):
    """Description of an output parameter and its expected value."""

    name: str = Field(description="Parameter key name")
    description: str = Field(description="Explanation and expected value range")


class KnowledgeCase(BaseModel):
    """A concrete case derived from an issue postmortem.

    Represents a real-world incident and its resolution, providing
    the LLM with specific examples to draw on during analysis.
    """

    title: str = Field(description="Short descriptive title of the case")
    date: str = Field(default="", description="Date of the incident (YYYY-MM-DD)")
    severity: str = Field(default="warning", description="Severity: critical, warning, info")
    chip_id: str = Field(default="", description="Chip identifier")
    qid: str = Field(default="", description="Qubit identifier")
    status: str = Field(default="resolved", description="Case status: resolved, open, workaround")
    symptom: str = Field(default="", description="Observed symptom")
    root_cause: str = Field(default="", description="Identified root cause")
    resolution: str = Field(default="", description="How the issue was resolved")
    lesson_learned: list[str] = Field(
        default_factory=list,
        description="Key takeaways from the case",
    )
    images: list[TaskKnowledgeImage] = Field(
        default_factory=list,
        description="Image references from the case file (with base64 data)",
    )


class TaskKnowledge(BaseModel):
    """LLM-oriented structured knowledge for a calibration task."""

    name: str = Field(description="Task name (e.g. CheckT1)")
    category: str = Field(default="", description="Category slug (e.g. td-characterization)")
    summary: str = Field(description="One-line experiment summary")
    what_it_measures: str = Field(description="What physical quantity is measured")
    physical_principle: str = Field(
        description="Concise explanation of the physical principle, including pulse sequences"
    )
    expected_result: ExpectedResult = Field(
        default_factory=lambda: ExpectedResult(),
        description="Expected shape and features of the result",
    )
    evaluation_criteria: str = Field(
        default="",
        description="Qualitative evaluation criteria (thresholds are in copilot.yaml)",
    )
    check_questions: list[str] = Field(
        default_factory=list,
        description="Rubric-style questions for LLM to evaluate",
    )
    failure_modes: list[FailureMode] = Field(
        default_factory=list,
        description="Common failure patterns with severity and remediation",
    )
    tips: list[str] = Field(
        default_factory=list,
        description="Practical tips for improving results",
    )
    output_parameters_info: list[OutputParameterInfo] = Field(
        default_factory=list,
        description="Descriptions of output parameter keys",
    )
    analysis_guide: list[str] = Field(
        default_factory=list,
        description="Step-by-step reasoning guide for the LLM",
    )
    prerequisites: list[str] = Field(
        default_factory=list,
        description="Tasks that should be completed before this one",
    )
    images: list[TaskKnowledgeImage] = Field(
        default_factory=list,
        description="Image references from the markdown file",
    )
    related_context: list[RelatedContextItem] = Field(
        default_factory=list,
        description="Additional data sources to load during analysis",
    )
    cases: list[KnowledgeCase] = Field(
        default_factory=list,
        description="Concrete cases derived from issue postmortems",
    )

    def to_prompt(self) -> str:
        """Convert to a markdown string suitable for an LLM system prompt.

        Note: Deployment-specific scoring thresholds are NOT included here;
        they are injected separately by copilot_agent._build_system_prompt().
        """
        lines = [
            f"## Experiment: {self.name}",
            self.summary,
            "",
            "### What it measures",
            self.what_it_measures,
            "",
            "### Physical principle",
            self.physical_principle,
            "",
            "### Expected result",
            self.expected_result.description,
        ]
        # Add structured metadata if present
        er = self.expected_result
        meta_parts = []
        if er.result_type:
            meta_parts.append(f"- Result type: {er.result_type}")
        if er.x_axis:
            meta_parts.append(f"- X-axis: {er.x_axis}")
        if er.y_axis:
            meta_parts.append(f"- Y-axis: {er.y_axis}")
        if er.z_axis:
            meta_parts.append(f"- Z-axis: {er.z_axis}")
        if er.fit_model:
            meta_parts.append(f"- Fit model: {er.fit_model}")
        if er.typical_range:
            meta_parts.append(f"- Typical range: {er.typical_range}")
        if er.good_visual:
            meta_parts.append(f"- Good result looks like: {er.good_visual}")
        if meta_parts:
            lines += ["", *meta_parts]

        if self.evaluation_criteria:
            lines += [
                "",
                "### Evaluation criteria",
                self.evaluation_criteria,
            ]
        if self.check_questions:
            lines += ["", "**Check questions:**"]
            lines += [f"- {q}" for q in self.check_questions]

        if self.output_parameters_info:
            lines += ["", "### Output parameters"]
            for p in self.output_parameters_info:
                lines.append(f"- **{p.name}**: {p.description}")

        if self.failure_modes:
            lines += ["", "### Common failure patterns"]
            for f in self.failure_modes:
                lines.append(f"- [{f.severity}] {f.description}")
                if f.cause:
                    lines.append(f"  - Cause: {f.cause}")
                if f.visual:
                    lines.append(f"  - Visual: {f.visual}")
                if f.next_action:
                    lines.append(f"  - Next: {f.next_action}")

        if self.tips:
            lines += [
                "",
                "### Tips for improvement",
                *[f"- {t}" for t in self.tips],
            ]

        if self.analysis_guide:
            lines += ["", "### Analysis guide"]
            for i, step in enumerate(self.analysis_guide, 1):
                lines.append(f"{i}. {step}")

        if self.prerequisites:
            lines += ["", "### Prerequisites"]
            lines += [f"- {p}" for p in self.prerequisites]

        if self.images:
            lines += ["", "### Reference figures"]
            for img in self.images:
                lines.append(f"- {img.alt_text}: {img.relative_path}")

        if self.cases:
            lines += ["", "### Past cases"]
            for i, case in enumerate(self.cases, 1):
                header = f"{i}. [{case.severity}] {case.title}"
                if case.date:
                    header += f" ({case.date}"
                    if case.qid:
                        header += f", {case.qid}"
                    header += ")"
                lines.append(header)
                if case.symptom:
                    lines.append(f"   - Symptom: {case.symptom}")
                if case.root_cause:
                    lines.append(f"   - Root cause: {case.root_cause}")
                if case.resolution:
                    lines.append(f"   - Resolution: {case.resolution}")
                if case.lesson_learned:
                    lines.append(f"   - Lessons: {'; '.join(case.lesson_learned)}")
                if case.images:
                    for img in case.images:
                        lines.append(f"   - Image: {img.alt_text} ({img.relative_path})")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Registry building (from generated JSON)
# ---------------------------------------------------------------------------


def _resolve_json_path() -> Path | None:
    """Locate ``task-knowledge.json`` under the config root.

    Checks ``config/task-knowledge/task-knowledge.json`` first (cloned
    knowledge repo), then falls back to ``config/task-knowledge.json``
    for backward compatibility.
    """
    from qdash.common.config_loader import ConfigLoader

    config_dir = ConfigLoader.get_config_dir()
    # Primary: inside the cloned knowledge repo directory
    repo_path = config_dir / "task-knowledge" / "task-knowledge.json"
    if repo_path.is_file():
        return repo_path
    # Fallback: legacy location at config root
    legacy_path = config_dir / "task-knowledge.json"
    if legacy_path.is_file():
        return legacy_path
    return None


def _build_registry() -> dict[str, TaskKnowledge]:
    """Build the task knowledge registry from the generated JSON file."""
    json_path = _resolve_json_path()
    if json_path is None:
        logger.warning("task-knowledge.json not found; run 'task knowledge' to generate it")
        return {}

    raw = json.loads(json_path.read_text(encoding="utf-8"))
    registry: dict[str, TaskKnowledge] = {}
    for name, data in raw.items():
        registry[name] = TaskKnowledge(**data)
    logger.info("Loaded %d task knowledge entries from %s", len(registry), json_path)
    return registry


TASK_KNOWLEDGE_REGISTRY: dict[str, TaskKnowledge] = _build_registry()


def get_task_knowledge(task_name: str) -> TaskKnowledge | None:
    """Look up TaskKnowledge by task class name."""
    return TASK_KNOWLEDGE_REGISTRY.get(task_name)


def list_all_task_knowledge() -> list[TaskKnowledge]:
    """Return all task knowledge entries."""
    return list(TASK_KNOWLEDGE_REGISTRY.values())


# Category slug → display name mapping
CATEGORY_DISPLAY_NAMES: dict[str, str] = {
    "box-setup": "Box Setup",
    "system": "System",
    "cw-characterization": "CW Characterization",
    "td-characterization": "TD Characterization",
    "one-qubit-gate-calibration": "One-Qubit Gate Calibration",
    "two-qubit-gate-calibration": "Two-Qubit Gate Calibration",
    "benchmarking": "Benchmarking",
}

# Canonical task → category directory mapping.
# This is the single source of truth used by both the API and the
# ``generate_task_knowledge.py`` script.
TASK_TO_CATEGORY_DIR: dict[str, str] = {}
_CATEGORIES: list[tuple[str, str, list[str]]] = [
    (
        "Box Setup",
        "box-setup",
        [
            "CheckStatus",
            "LinkUp",
            "DumpBox",
            "CheckNoise",
            "Configure",
            "ReadoutConfigure",
        ],
    ),
    (
        "System",
        "system",
        [
            "CheckSkew",
        ],
    ),
    (
        "CW Characterization",
        "cw-characterization",
        [
            "CheckResonatorFrequencies",
            "CheckResonatorSpectroscopy",
            "CheckReflectionCoefficient",
            "CheckElectricalDelay",
            "CheckReadoutAmplitude",
            "CheckQubitFrequencies",
            "CheckQubitSpectroscopy",
        ],
    ),
    (
        "TD Characterization",
        "td-characterization",
        [
            "CheckQubit",
            "CheckQubitFrequency",
            "CheckReadoutFrequency",
            "CheckRabi",
            "CheckT1",
            "CheckT2Echo",
            "CheckRamsey",
            "CheckDispersiveShift",
            "CheckOptimalReadoutAmplitude",
            "ReadoutClassification",
            "ChevronPattern",
        ],
    ),
    (
        "One-Qubit Gate Calibration",
        "one-qubit-gate-calibration",
        [
            "CheckPIPulse",
            "CheckHPIPulse",
            "CheckDRAGPIPulse",
            "CheckDRAGHPIPulse",
            "CreatePIPulse",
            "CreateHPIPulse",
            "CreateDRAGPIPulse",
            "CreateDRAGHPIPulse",
        ],
    ),
    (
        "Two-Qubit Gate Calibration",
        "two-qubit-gate-calibration",
        [
            "CheckCrossResonance",
            "CheckZX90",
            "CreateZX90",
            "CheckBellState",
            "CheckBellStateTomography",
        ],
    ),
    (
        "Benchmarking",
        "benchmarking",
        [
            "RandomizedBenchmarking",
            "X90InterleavedRandomizedBenchmarking",
            "X180InterleavedRandomizedBenchmarking",
            "ZX90InterleavedRandomizedBenchmarking",
        ],
    ),
]
for _cat_name, _cat_dir, _cat_tasks in _CATEGORIES:
    for _t in _cat_tasks:
        TASK_TO_CATEGORY_DIR[_t] = _cat_dir


def get_task_category_dir(task_name: str) -> str:
    """Return the category directory slug for a task name.

    First checks the static ``TASK_TO_CATEGORY_DIR`` mapping (covers
    all known tasks even without a knowledge entry), then falls back
    to the loaded registry's ``category`` field.
    Returns ``"other"`` if the task is completely unknown.
    """
    cat = TASK_TO_CATEGORY_DIR.get(task_name)
    if cat:
        return cat
    entry = TASK_KNOWLEDGE_REGISTRY.get(task_name)
    if entry and entry.category:
        return entry.category
    return "other"
