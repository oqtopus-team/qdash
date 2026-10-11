"""Structured domain knowledge model for calibration tasks.

Provides a ``TaskKnowledge`` Pydantic model and a registry that maps task
class names to their knowledge entries.

Knowledge is loaded from ``config/task-knowledge/task-knowledge.json``
(cloned knowledge repo), which that repo's ``generate.py`` builds from the
Markdown sources. The registry re-reads the file whenever it changes.

The registry lives in ``datamodel`` so that both the API container and
the workflow container can access it without cross-importing.
"""

from __future__ import annotations

import base64
import json
import logging
import os
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


OUTCOMES = ("expected", "suboptimal", "anomalous", "apparatus")
"""Plot classification the evaluation model answers with (QCalEval's four outcomes)."""

VERDICTS = ("pass", "pass_with_note", "fail")
"""A human's decision about a result; separate from the plot's outcome."""

_MIME_BY_SUFFIX = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


class KnowledgeFigure(BaseModel):
    """An image file in the knowledge repository, relative to the task directory."""

    alt: str = Field(default="", description="Alt text from ![alt](path)")
    path: str = Field(description="Path relative to the task directory")


class KnowledgeExample(BaseModel):
    """One expert-labeled plot: a demonstration for in-context evaluation."""

    id: str = Field(description="File stem under examples/")
    title: str
    date: str = ""
    chip: str = ""
    qid: str = ""
    outcome: str = Field(description="One of the four outcomes")
    fit_quality: str = Field(default="", description="good | marginal | poor")
    verdict: str = Field(default="", description="pass | pass_with_note | fail")
    source: str = ""
    figures: list[KnowledgeFigure] = Field(default_factory=list)
    diagnosis: str = Field(default="", description="The diagnosis the way the model should answer")

    def label(self) -> str:
        """The demonstration label shown after the example's figure."""
        parts = [f"Outcome: {self.outcome}"]
        if self.fit_quality:
            parts.append(f"Fit quality: {self.fit_quality}")
        if self.verdict:
            parts.append(f"Verdict: {self.verdict}")
        return "\n".join([*parts, self.diagnosis]).strip()


class TaskKnowledge(BaseModel):
    """What the knowledge repository says about one calibration task.

    The shape follows the QCalEval / Ising-Calibration papers: a prose
    background for the experiment (the task's ``index.md``) and labeled
    example plots. The category is the calibtasks package the task lives in.
    Old-format entries (summary, what_it_measures, ...) are read for their
    background only.
    """

    model_config = ConfigDict(extra="ignore")

    name: str = Field(description="Task name (e.g. CheckT1)")
    category: str = Field(default="", description="calibtasks package (e.g. one_qubit_coarse)")
    background: str = Field(
        default="", description="The task's index.md: what the experiment does and shows"
    )
    figures: list[KnowledgeFigure] = Field(
        default_factory=list, description="Figures index.md references"
    )
    examples: list[KnowledgeExample] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _accept_previous_format(cls, data: Any) -> Any:
        if not isinstance(data, dict) or data.get("background") or not data.get("summary"):
            return data
        data = dict(data)
        parts = [data.get("summary", ""), data.get("what_it_measures", "")]
        data["background"] = "\n\n".join(p for p in parts if p)
        data.setdefault(
            "figures",
            [
                {"alt": img.get("alt_text", ""), "path": img.get("relative_path", "")}
                for img in data.get("images", [])
                if isinstance(img, dict) and img.get("relative_path")
            ],
        )
        return data

    @property
    def summary(self) -> str:
        """The background's first paragraph, for listings."""
        return self.background.split("\n\n", 1)[0].strip()

    def to_prompt(self, *, include_examples: bool = False) -> str:
        """Render the task's reference text for a model: the background as written.

        Examples are appended as text only on request (the chat opens with
        them); the evaluation path shows them as figure + label pairs instead.
        """
        lines = [f"## Experiment: {self.name}", self.background.strip()]
        if include_examples and self.examples:
            lines += ["", "### Labeled examples"]
            for example in self.examples:
                lines.append(
                    f"- {example.title} ({example.outcome}"
                    + (f", {example.verdict}" if example.verdict else "")
                    + f"): {example.diagnosis}"
                )
        return "\n".join(lines).strip()

    # --- figures on disk ---

    def task_dir(self) -> Path | None:
        """The task's directory in the cloned knowledge repository, if present."""
        repo_dir = _resolve_repo_dir()
        if repo_dir is None or not self.category:
            return None
        task_dir = repo_dir / self.category / self.name
        return task_dir if task_dir.is_dir() else None

    def figure_file(self, relative_path: str) -> Path | None:
        """Resolve a figure path inside the task directory; ``None`` if outside or missing."""
        task_dir = self.task_dir()
        if task_dir is None:
            return None
        candidate = (task_dir / relative_path.strip().lstrip("./")).resolve()
        try:
            candidate.relative_to(task_dir.resolve())
        except ValueError:
            return None
        return candidate if candidate.is_file() else None

    def load_figure(self, relative_path: str) -> tuple[bytes, str] | None:
        """Read a figure's bytes and media type."""
        file = self.figure_file(relative_path)
        if file is None:
            return None
        return file.read_bytes(), _MIME_BY_SUFFIX.get(
            file.suffix.lower(), "application/octet-stream"
        )

    def load_figure_base64(self, relative_path: str) -> tuple[str, str] | None:
        """A figure as (base64, media type), for JSON responses and model inputs."""
        loaded = self.load_figure(relative_path)
        if loaded is None:
            return None
        data, mime = loaded
        return base64.b64encode(data).decode("ascii"), mime


# ---------------------------------------------------------------------------
# Registry building (from generated JSON)
# ---------------------------------------------------------------------------


def _resolve_json_path() -> Path | None:
    """Locate ``task-knowledge.json`` under the config root.

    Checks ``config/task-knowledge/task-knowledge.json`` first (cloned
    knowledge repo), then falls back to ``config/task-knowledge.json``
    for backward compatibility.
    """
    from qdash.common.config.loader import ConfigLoader

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


def _resolve_repo_dir() -> Path | None:
    """Locate the cloned task-knowledge repository directory, if available."""
    from qdash.common.config.loader import ConfigLoader

    repo_dir = ConfigLoader.get_config_dir() / "task-knowledge"
    if repo_dir.is_dir():
        return repo_dir

    json_path = _resolve_json_path()
    if json_path is not None and json_path.parent.name == "task-knowledge":
        return json_path.parent

    return None


def _build_registry(json_path: Path) -> dict[str, TaskKnowledge]:
    """Build the task knowledge registry from the generated JSON file."""
    raw = json.loads(json_path.read_text(encoding="utf-8"))
    registry: dict[str, TaskKnowledge] = {}
    for name, data in raw.items():
        registry[name] = TaskKnowledge(**data)
    logger.info("Loaded %d task knowledge entries from %s", len(registry), json_path)
    return registry


# The registry follows the JSON file on disk: it is rebuilt whenever the file's
# identity (path, mtime, size) changes, so a save through the knowledge editor,
# a pull, or ``task knowledge-pull`` on the host reaches every API worker
# without a restart.
_REGISTRY_CACHE: tuple[tuple[str, int, int] | None, dict[str, TaskKnowledge]] = (None, {})
_WARNED_MISSING = False


def _registry() -> dict[str, TaskKnowledge]:
    global _REGISTRY_CACHE, _WARNED_MISSING
    json_path = _resolve_json_path()
    if json_path is None:
        if not _WARNED_MISSING:
            logger.warning("task-knowledge.json not found; run 'task knowledge-pull' to fetch it")
            _WARNED_MISSING = True
        _REGISTRY_CACHE = (None, {})
        return {}
    stat = json_path.stat()
    key = (str(json_path), stat.st_mtime_ns, stat.st_size)
    cached_key, cached = _REGISTRY_CACHE
    if cached_key == key:
        return cached
    registry = _build_registry(json_path)
    _REGISTRY_CACHE = (key, registry)
    return registry


def regenerate_task_knowledge_json(repo_dir: Path | None = None) -> Path:
    """Rebuild ``task-knowledge.json`` from the markdown sources with the repo's own generator.

    The knowledge repository ships ``generate.py`` (the same script its CI runs on
    merge); running it after an edit makes the edit visible to the API and the
    runtime before a pull request is merged. Returns the JSON path.
    """
    import subprocess
    import sys

    repo_dir = repo_dir or _resolve_repo_dir()
    if repo_dir is None:
        raise RuntimeError("task-knowledge repository directory not found")
    generator = repo_dir / "generate.py"
    if not generator.is_file():
        raise RuntimeError(f"generate.py not found in {repo_dir}")
    output = repo_dir / "task-knowledge.json"
    result = subprocess.run(  # noqa: S603 -- fixed argv: the repo's own generator, no user input
        [sys.executable, "-I", str(generator), "--output", str(output)],
        cwd=repo_dir,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "generate.py failed")
    return output


def get_task_knowledge(task_name: str) -> TaskKnowledge | None:
    """Look up TaskKnowledge by task class name."""
    return _registry().get(task_name)


def list_all_task_knowledge() -> list[TaskKnowledge]:
    """Return all task knowledge entries."""
    return list(_registry().values())


def get_task_knowledge_repo_metadata() -> tuple[str | None, str | None]:
    """Return the configured knowledge repo URL and current commit if available."""
    repo_url = os.getenv("KNOWLEDGE_REPO_URL") or None
    repo_dir = _resolve_repo_dir()
    if repo_dir is None:
        return repo_url, None

    try:
        from git import Repo
        from git.exc import GitError, InvalidGitRepositoryError, NoSuchPathError

        repo = Repo(repo_dir)
        if repo_url is None and repo.remotes:
            repo_url = next((remote.url for remote in repo.remotes if remote.url), None)
        return repo_url, repo.head.commit.hexsha
    except (GitError, InvalidGitRepositoryError, NoSuchPathError, ValueError):
        return repo_url, None


# Category = the calibtasks package the task lives in → display name.
CATEGORY_DISPLAY_NAMES: dict[str, str] = {
    "box_setup": "Box Setup",
    "system": "System",
    "cw": "CW Characterization",
    "measurement": "Measurement",
    "one_qubit_coarse": "One-Qubit Coarse",
    "one_qubit_fine": "One-Qubit Fine",
    "two_qubit": "Two-Qubit",
    "benchmark": "Benchmark",
    "analysis": "Analysis",
}


def get_task_category_dir(task_name: str) -> str:
    """The calibtasks package a task's knowledge lives under, or ``"other"``."""
    entry = _registry().get(task_name)
    return entry.category if entry and entry.category else "other"
