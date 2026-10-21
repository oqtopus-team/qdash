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
import re
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, model_validator

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)
TASK_KNOWLEDGE_SCHEMA_VERSION = 1

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
    status: str = Field(
        default="",
        description="The task's status code the example demonstrates (QCalEval Q6), e.g. SUCCESS",
    )
    suggested_range: str = Field(
        default="", description="The corrective range the example's status calls for, as text"
    )
    parameters: str = Field(
        default="", description="JSON of the values read from the example's plot (QCalEval Q5)"
    )
    figures: list[KnowledgeFigure] = Field(default_factory=list)
    diagnosis: str = Field(default="", description="The diagnosis the way the model should answer")

    def label(self) -> str:
        """The demonstration label shown after the example's figure."""
        parts = [f"Outcome: {self.outcome}"]
        if self.fit_quality:
            parts.append(f"Fit quality: {self.fit_quality}")
        if self.verdict:
            parts.append(f"Verdict: {self.verdict}")
        if self.status:
            parts.append(f"Status: {self.status}")
        return "\n".join([*parts, self.diagnosis]).strip()


class TaskReference(BaseModel):
    """The task's background the way QCalEval gives it before a plot, with the
    family-specific parts of its question templates.

    Derived from ``index.md``: the background from the intro and the expected
    plot, the status criteria from the expected plot and the common failures,
    the extraction schema from the parameters to extract.
    """

    background: str = Field(
        default="", description="Two to four sentences: what the experiment does, what success is"
    )
    guidance: list[str] = Field(
        default_factory=list, description="Points the significance question asks to explain"
    )
    parameters: dict[str, str] = Field(
        default_factory=dict, description="Extraction schema: parameter name -> JSON type"
    )
    statuses: dict[str, str] = Field(
        default_factory=dict,
        description="Decision criteria: status code -> criterion, SUCCESS first",
    )
    range_format: str | None = Field(
        default=None, description="How a suggested corrective range is written"
    )


_HEADING_RE = re.compile(r"^##\s+(.+?)\s*$")
_BULLET_RE = re.compile(r"^\s*[-*]\s+(.*)$")
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z\[(])")


def _sections(background: str) -> tuple[str, dict[str, str]]:
    """The intro before the first ``##`` heading, and each section's text by lowercased heading."""
    intro: list[str] = []
    sections: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in background.splitlines():
        match = _HEADING_RE.match(line)
        if match:
            current = sections.setdefault(match.group(1).strip().lower(), [])
            continue
        (intro if current is None else current).append(line)
    return "\n".join(intro).strip(), {k: "\n".join(v).strip() for k, v in sections.items()}


def _paragraphs(text: str) -> list[str]:
    """Prose paragraphs of a section: bullet lists and blank lines left out."""
    paragraphs: list[str] = []
    for block in re.split(r"\n\s*\n", text):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines or _BULLET_RE.match(lines[0]):
            continue
        paragraphs.append(" ".join(lines))
    return paragraphs


def _bullets(text: str) -> list[str]:
    """List items of a section, continuation lines joined."""
    items: list[str] = []
    for line in text.splitlines():
        match = _BULLET_RE.match(line)
        if match:
            items.append(match.group(1).strip())
        elif items and line.strip():
            items[-1] = f"{items[-1]} {line.strip()}"
    return items


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_RE.split(text) if s.strip()]


def _status_code(title: str) -> str:
    """``Low contrast (<70%)`` -> ``LOW_CONTRAST``."""
    bare = re.sub(r"\([^)]*\)", "", title)
    code = re.sub(r"[^A-Za-z0-9]+", "_", bare).strip("_").upper()
    return code or "FAILURE"


def _split_failure(item: str) -> tuple[str, str]:
    """A common-failure bullet as (title, criterion).

    ``Low contrast (<70%) — small amplitude; next: check readout`` and
    ``Short T1 (<20 μs): the curve flattens early; check TLS`` both split at
    their first separator; the criterion stops at the first ``;``.
    """
    for separator in (" \u2014 ", " \u2013 ", ": "):  # em dash, en dash, colon
        if separator in item:
            title, rest = item.split(separator, 1)
            break
    else:
        words = item.split()
        title, rest = " ".join(words[:4]), item
    criterion = rest.split(";", 1)[0].strip().rstrip(".")
    return title.strip(), criterion


def _parameter_type(description: str) -> str:
    lowered = description.lower()
    if "bool" in lowered:
        return "true | false"
    if re.search(r"\b(int|integer|count|number of)\b", lowered):
        return "int"
    return "float"


def derive_reference(name: str, background: str) -> TaskReference:
    """The QCalEval-style reference of a task from its ``index.md`` body."""
    intro, sections = _sections(background)
    expected = _paragraphs(sections.get("expected plot", ""))
    intro_paragraphs = _paragraphs(intro)
    pieces = [f"This is a {name} experiment:" if name else "This is a calibration experiment:"]
    if intro_paragraphs:
        pieces.append(intro_paragraphs[0])
    if expected:
        pieces.append(expected[0])
    text = " ".join(pieces).strip()
    if text.endswith(":"):
        text = text[:-1] + "."

    statuses: dict[str, str] = {}
    expected_sentences = _sentences(expected[0]) if expected else []
    success = next(
        (s for s in expected_sentences if re.match(r"a good result\b", s, re.IGNORECASE)), None
    )
    if success:
        success = re.sub(r"^a good result\s*[:\uff1a]?\s*", "", success, flags=re.IGNORECASE)
    elif expected_sentences:
        success = expected_sentences[0]
    statuses["SUCCESS"] = (success or "The result matches the expected plot").rstrip(".")
    for item in _bullets(sections.get("common failures", "")):
        title, criterion = _split_failure(item)
        code = _status_code(title)
        if code in statuses:
            continue
        statuses[code] = criterion or title

    parameters: dict[str, str] = {}
    for item in _bullets(sections.get("parameters to extract", "")):
        if ":" not in item:
            continue
        pname, description = item.split(":", 1)
        pname = pname.strip().strip("`")
        if pname and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", pname):
            parameters[pname] = _parameter_type(description)

    return TaskReference(background=text, statuses=statuses, parameters=parameters)


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

    # A draft's figures live in its own directory, not the shared repository.
    _task_dir: Any = PrivateAttr(default=None)

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

    def reference(self) -> TaskReference:
        """The background and question-template parts for the evaluation model."""
        return derive_reference(self.name, self.background)

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
        """The task's directory: a draft's own, else the cloned knowledge repository's."""
        if self._task_dir is not None:
            return self._task_dir if self._task_dir.is_dir() else None
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
    if not isinstance(raw, dict):
        raise ValueError("task-knowledge.json must contain an object")
    if "schema_version" in raw or "tasks" in raw:
        version = raw.get("schema_version")
        if version != TASK_KNOWLEDGE_SCHEMA_VERSION:
            raise ValueError(f"unsupported task-knowledge schema_version: {version!r}")
        raw = raw.get("tasks")
        if not isinstance(raw, dict):
            raise ValueError("task-knowledge.json tasks must contain an object")
    registry: dict[str, TaskKnowledge] = {}
    for name, data in raw.items():
        if not isinstance(data, dict):
            raise ValueError(f"task-knowledge entry {name!r} must contain an object")
        registry[name] = TaskKnowledge(**data)
    logger.info("Loaded %d task knowledge entries from %s", len(registry), json_path)
    return registry


# The registry follows the JSON file on disk: it is rebuilt whenever the file's
# identity (path, mtime, size) changes, so ``task knowledge-pull`` on the host
# reaches every API worker without a restart.
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


def parse_task_dir(task_dir: Path, *, category: str = "") -> tuple[TaskKnowledge | None, list[str]]:
    """Parse one task directory with the knowledge repository's own generator.

    The same parser builds ``task-knowledge.json``, so a draft reads exactly as
    the published entry would. Returns the entry, ``None`` when the generator
    rejects it, and the generator's warnings. Figures resolve inside
    ``task_dir``.
    """
    import importlib.util

    repo_dir = _resolve_repo_dir()
    generator = repo_dir / "generate.py" if repo_dir is not None else None
    if generator is None or not generator.is_file():
        raise RuntimeError("generate.py not found in the task-knowledge repository")
    spec = importlib.util.spec_from_file_location("_task_knowledge_generate", generator)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {generator}")
    # A fresh module per call: the generator collects warnings in a module-level list.
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if hasattr(module, "parse_task_dir"):
        result = module.parse_task_dir(task_dir, category)
        if isinstance(result, dict):
            version = result.get("schema_version")
            if version != TASK_KNOWLEDGE_SCHEMA_VERSION:
                raise RuntimeError(f"unsupported task-knowledge schema_version: {version!r}")
            entry = result.get("entry")
            raised = result.get("warnings", [])
        else:
            # Public parsers deployed before the versioned result returned a tuple.
            entry, raised = result
    else:
        # Checkouts from before the public entry point.
        entry = module._parse_task(task_dir, category)
        raised = getattr(module, "warnings", [])
    warnings = [str(warning) for warning in raised]
    if not entry:
        return None, warnings
    knowledge = TaskKnowledge(**entry)
    knowledge._task_dir = task_dir
    return knowledge, warnings


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
