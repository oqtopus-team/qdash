"""Structured domain knowledge model for calibration tasks.

Provides a ``TaskKnowledge`` Pydantic model and a central registry
(``TASK_KNOWLEDGE_REGISTRY``) that maps task class names to their
knowledge entries.

Knowledge is loaded from ``config/task-knowledge.json``, which is
generated from Markdown files by ``scripts/generate_task_knowledge.py``
(run via ``task knowledge``).

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


class RelatedContextItem(BaseModel):
    """Declarative specification for additional data to load during analysis.

    Parsed from ``## Related context`` section in Markdown knowledge files.
    """

    type: str = Field(description="Context type: 'history' | 'neighbor_qubits' | 'coupling'")
    params: list[str] = Field(default_factory=list, description="Parameter names to extract")
    last_n: int = Field(default=5, description="Number of recent results (for history type)")


class TaskKnowledge(BaseModel):
    """LLM-oriented structured knowledge for a calibration task."""

    name: str = Field(description="Task name (e.g. CheckT1)")
    summary: str = Field(description="One-line experiment summary")
    what_it_measures: str = Field(description="What physical quantity is measured")
    physical_principle: str = Field(
        description="Concise explanation of the physical principle, including pulse sequences"
    )
    expected_curve: str = Field(description="Expected shape and features of the result graph")
    good_threshold: str = Field(description="Quantitative criteria for good / excellent results")
    failure_modes: list[str] = Field(
        default_factory=list,
        description="Common failure patterns and their likely causes",
    )
    tips: list[str] = Field(
        default_factory=list,
        description="Practical tips for improving results",
    )
    raw_markdown: str = Field(
        default="",
        description="Original markdown source for LLM context",
    )
    images: list[TaskKnowledgeImage] = Field(
        default_factory=list,
        description="Image references from the markdown file",
    )
    related_context: list[RelatedContextItem] = Field(
        default_factory=list,
        description="Additional data sources to load during analysis",
    )

    def to_prompt(self) -> str:
        """Convert to a markdown string suitable for an LLM system prompt."""
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
            "### Expected graph",
            self.expected_curve,
            "",
            "### Evaluation criteria",
            self.good_threshold,
        ]
        if self.failure_modes:
            lines += [
                "",
                "### Common failure patterns",
                *[f"- {f}" for f in self.failure_modes],
            ]
        if self.tips:
            lines += [
                "",
                "### Tips for improvement",
                *[f"- {t}" for t in self.tips],
            ]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Registry building (from generated JSON)
# ---------------------------------------------------------------------------


def _resolve_json_path() -> Path | None:
    """Locate ``task-knowledge.json`` under the config root."""
    from qdash.common.config_loader import ConfigLoader

    json_path = ConfigLoader.get_config_dir() / "task-knowledge.json"
    if json_path.is_file():
        return json_path
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
