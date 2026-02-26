#!/usr/bin/env python3
"""Generate task-knowledge.json from docs/task-knowledge/<category>/<Task>/index.md.

Parses all Markdown knowledge files and produces a single JSON registry
that the application loads at runtime.  Run via ``task knowledge`` or
directly with ``uv run scripts/generate_task_knowledge.py``.

Usage:
    uv run scripts/generate_task_knowledge.py
"""

from __future__ import annotations

import base64
import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
MD_DIR = REPO_ROOT / "docs" / "task-knowledge"
OUTPUT_FILE = REPO_ROOT / "config" / "task-knowledge.json"
SIDEBAR_FILE = REPO_ROOT / "docs" / ".vitepress" / "task-knowledge-sidebar.json"

# ---------------------------------------------------------------------------
# Markdown parser (standalone – no project imports required)
# ---------------------------------------------------------------------------

# H2 heading (lowercase) → field name
_SECTION_MAP: dict[str, str] = {
    "what it measures": "what_it_measures",
    "physical principle": "physical_principle",
    "expected result": "expected_result",
    "expected curve": "expected_result",  # backward compat
    "expected graph": "expected_result",  # backward compat
    "evaluation criteria": "evaluation_criteria",
    "output parameters": "output_parameters",
    "common failure patterns": "failure_modes",
    "common failure modes": "failure_modes",
    "tips for improvement": "tips",
    "tips": "tips",
    "analysis guide": "analysis_guide",
    "related context": "related_context",
}

MAX_IMAGE_SIZE = 1 * 1024 * 1024  # 1MB

_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
_RELATED_CONTEXT_RE = re.compile(r"-\s+(history|neighbor_qubits|coupling)\(([^)]*)\)")

# Failure mode severity tag: - [critical] ..., - [warning] ..., - [info] ...
_FAILURE_SEVERITY_RE = re.compile(r"^\[(\w+)\]\s*(.+)")

# Metadata lines in expected result: - key: value
_METADATA_RE = re.compile(r"^-\s+(\w[\w_]*):\s*(.+)")

# Check question lines
_CHECK_QUESTION_RE = re.compile(r'^-\s+"(.+?)"$')


def _detect_image_type(data: bytes) -> str | None:
    """Detect image format from magic bytes.

    Returns the MIME subtype (e.g. "png", "jpeg") or None if unrecognised.
    """
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:2] == b"\xff\xd8":
        return "jpeg"
    if data[:4] == b"GIF8":
        return "gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def _parse_list_items(text: str) -> list[str]:
    """Extract list items (lines starting with ``- ``)."""
    return [line.strip()[2:] for line in text.strip().splitlines() if line.strip().startswith("- ")]


def _parse_related_context(text: str) -> list[dict]:
    """Parse ``## Related context`` list items into structured dicts.

    Examples::

        - history(last_n=5)
        - neighbor_qubits(frequency, t1)
        - coupling(zx_rate, coupling_strength)
    """
    items: list[dict] = []
    for m in _RELATED_CONTEXT_RE.finditer(text):
        ctx_type = m.group(1)
        args_str = m.group(2).strip()
        item: dict = {"type": ctx_type, "params": [], "last_n": 5}
        if ctx_type == "history":
            # Parse last_n=N
            kv = re.search(r"last_n\s*=\s*(\d+)", args_str)
            if kv:
                item["last_n"] = int(kv.group(1))
        else:
            # Parse comma-separated parameter names
            if args_str:
                item["params"] = [p.strip() for p in args_str.split(",") if p.strip()]
        items.append(item)
    return items


def _parse_expected_result(text: str) -> dict:
    """Parse ``## Expected result`` section into structured dict.

    Extracts description text and metadata lines like:
        - result_type: decay_curve
        - x_axis: Delay (μs)
        - fit_model: exp(-t/T1)
        - good_visual: smooth monotonic decay ...
    """
    lines = text.strip().splitlines()
    description_lines: list[str] = []
    metadata: dict[str, str] = {}

    for line in lines:
        stripped = line.strip()
        m = _METADATA_RE.match(stripped)
        if m and m.group(1) in (
            "result_type", "x_axis", "y_axis", "z_axis",
            "fit_model", "typical_range", "good_visual",
        ):
            metadata[m.group(1)] = m.group(2).strip()
        elif not stripped.startswith("!["):
            description_lines.append(stripped)

    return {
        "description": "\n".join(description_lines).strip(),
        "result_type": metadata.get("result_type", ""),
        "x_axis": metadata.get("x_axis", ""),
        "y_axis": metadata.get("y_axis", ""),
        "z_axis": metadata.get("z_axis", ""),
        "fit_model": metadata.get("fit_model", ""),
        "typical_range": metadata.get("typical_range", ""),
        "good_visual": metadata.get("good_visual", ""),
    }


def _parse_failure_modes(text: str) -> list[dict]:
    """Parse ``## Common failure patterns`` with severity, cause, visual, next.

    Format:
        - [critical] Short T1 (<20 μs)
          - cause: TLS coupling or dielectric loss
          - visual: rapid decay, curve flattens early
          - next: check TLS, inspect packaging
        - [warning] Non-exponential decay
          - cause: multi-level leakage
          - visual: shoulder or kink in decay curve
          - next: check leakage to |2⟩
    """
    items: list[dict] = []
    lines = text.strip().splitlines()
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped.startswith("- "):
            content = stripped[2:]
            severity_match = _FAILURE_SEVERITY_RE.match(content)
            if severity_match:
                severity = severity_match.group(1)
                description = severity_match.group(2).strip()
            else:
                severity = "warning"
                description = content

            item: dict = {
                "severity": severity,
                "description": description,
                "cause": "",
                "visual": "",
                "next_action": "",
            }

            # Parse sub-items (indented lines starting with "- key: value")
            i += 1
            while i < len(lines):
                sub = lines[i].strip()
                if sub.startswith("- cause:"):
                    item["cause"] = sub[len("- cause:"):].strip()
                elif sub.startswith("- visual:"):
                    item["visual"] = sub[len("- visual:"):].strip()
                elif sub.startswith("- next:"):
                    item["next_action"] = sub[len("- next:"):].strip()
                elif sub.startswith("- ") and not sub.startswith("- cause:") and not sub.startswith("- visual:") and not sub.startswith("- next:"):
                    # New top-level item
                    break
                else:
                    if not sub:
                        i += 1
                        continue
                    break
                i += 1

            items.append(item)
        else:
            i += 1

    return items


def _parse_evaluation_criteria(text: str) -> tuple[str, list[str]]:
    """Parse ``## Evaluation criteria`` into qualitative text and check_questions.

    Returns (criteria_text, check_questions).
    """
    lines = text.strip().splitlines()
    criteria_lines: list[str] = []
    check_questions: list[str] = []
    in_check_questions = False

    for line in lines:
        stripped = line.strip()
        if stripped.lower().startswith("- check_questions:") or stripped.lower() == "check_questions:":
            in_check_questions = True
            continue
        if in_check_questions:
            m = _CHECK_QUESTION_RE.match(stripped)
            if m:
                check_questions.append(m.group(1))
            elif stripped.startswith('- "') and stripped.endswith('"'):
                check_questions.append(stripped[3:-1])
            elif stripped.startswith("- ") and not stripped.startswith("- check_questions:"):
                # No longer in check_questions block
                in_check_questions = False
                criteria_lines.append(stripped)
            continue
        criteria_lines.append(stripped)

    return "\n".join(criteria_lines).strip(), check_questions


def _parse_output_parameters(text: str) -> list[dict]:
    """Parse ``## Output parameters`` into list of {name, description}.

    Format:
        - param_name: description text
    """
    items: list[dict] = []
    for line in text.strip().splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            content = stripped[2:]
            if ":" in content:
                name, desc = content.split(":", 1)
                items.append({"name": name.strip(), "description": desc.strip()})
            else:
                items.append({"name": content.strip(), "description": ""})
    return items


def _parse_analysis_guide(text: str) -> list[str]:
    """Parse ``## Analysis guide`` into ordered list of steps.

    Format:
        1. Step one
        2. Step two
    """
    steps: list[str] = []
    for line in text.strip().splitlines():
        stripped = line.strip()
        # Match numbered list items: "1. ...", "2. ...", etc.
        m = re.match(r"^\d+\.\s+(.+)", stripped)
        if m:
            steps.append(m.group(1))
        elif stripped.startswith("- "):
            steps.append(stripped[2:])
    return steps


# Case metadata keys in frontmatter-style lines: - key: value
_CASE_META_KEYS = {"date", "severity", "chip_id", "qid", "status"}

# Case H2 section heading → field name
_CASE_SECTION_MAP: dict[str, str] = {
    "symptom": "symptom",
    "root cause": "root_cause",
    "resolution": "resolution",
    "lesson learned": "lesson_learned",
}


def _parse_case_file(path: Path) -> dict | None:
    """Parse a case Markdown file into a dict.

    Expected format::

        # Title
        - date: 2026-02-15
        - severity: critical
        - chip_id: CHIP-01
        - qid: Q12
        - status: resolved

        ## Symptom
        ...
        ## Root cause
        ...
        ## Resolution
        ...
        ## Lesson learned
        - lesson 1
        - lesson 2

    Returns ``None`` if the file cannot be parsed.
    """
    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines()

    # --- H1 (title) ---
    title: str | None = None
    meta_start: int = 0
    for i, line in enumerate(lines):
        if line.startswith("# ") and not line.startswith("## "):
            title = line[2:].strip()
            meta_start = i + 1
            break

    if title is None:
        return None

    # --- Metadata lines (before first H2) ---
    h2_indices = [i for i, line in enumerate(lines) if line.startswith("## ")]
    meta_end = h2_indices[0] if h2_indices else len(lines)

    metadata: dict[str, str] = {}
    for line in lines[meta_start:meta_end]:
        stripped = line.strip()
        if stripped.startswith("- "):
            content = stripped[2:]
            if ":" in content:
                key, val = content.split(":", 1)
                key = key.strip().lower().replace(" ", "_")
                if key in _CASE_META_KEYS:
                    metadata[key] = val.strip()

    # --- H2 sections ---
    sections: dict[str, str] = {}
    for idx, h2_line_idx in enumerate(h2_indices):
        heading = lines[h2_line_idx][3:].strip().lower()
        body_start = h2_line_idx + 1
        body_end = h2_indices[idx + 1] if idx + 1 < len(h2_indices) else len(lines)
        sections[heading] = "\n".join(lines[body_start:body_end]).strip()

    # --- Map sections to fields ---
    fields: dict[str, object] = {}
    for heading, body in sections.items():
        field_name = _CASE_SECTION_MAP.get(heading)
        if field_name is None:
            continue
        if field_name == "lesson_learned":
            fields[field_name] = _parse_list_items(body)
        else:
            fields[field_name] = body

    return {
        "title": title,
        "date": metadata.get("date", ""),
        "severity": metadata.get("severity", "warning"),
        "chip_id": metadata.get("chip_id", ""),
        "qid": metadata.get("qid", ""),
        "status": metadata.get("status", "resolved"),
        "symptom": fields.get("symptom", ""),
        "root_cause": fields.get("root_cause", ""),
        "resolution": fields.get("resolution", ""),
        "lesson_learned": fields.get("lesson_learned", []),
    }


def _parse_cases_dir(task_dir: Path) -> list[dict]:
    """Parse all case Markdown files in ``<task_dir>/cases/``."""
    cases_dir = task_dir / "cases"
    if not cases_dir.is_dir():
        return []

    cases: list[dict] = []
    for case_path in sorted(cases_dir.glob("*.md")):
        case = _parse_case_file(case_path)
        if case is None:
            print(f"  SKIP case {case_path.name}: no H1 heading found")
            continue
        cases.append(case)
        print(f"  CASE {case_path.name} -> {case['title']}")

    return cases


def _parse_markdown_file(path: Path) -> dict | None:
    """Parse a Markdown knowledge file into a dict.

    Returns ``None`` if the file cannot be parsed.
    """
    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines()

    # --- H1 (task name) ---
    name: str | None = None
    summary_start: int | None = None
    for i, line in enumerate(lines):
        if line.startswith("# ") and not line.startswith("## "):
            name = line[2:].strip()
            summary_start = i + 1
            break

    if name is None:
        return None

    # --- H2 sections ---
    h2_indices = [i for i, line in enumerate(lines) if line.startswith("## ")]
    summary_end = h2_indices[0] if h2_indices else len(lines)
    summary = "\n".join(lines[summary_start:summary_end]).strip()

    sections: dict[str, str] = {}
    for idx, h2_line_idx in enumerate(h2_indices):
        heading = lines[h2_line_idx][3:].strip().lower()
        body_start = h2_line_idx + 1
        body_end = h2_indices[idx + 1] if idx + 1 < len(h2_indices) else len(lines)
        sections[heading] = "\n".join(lines[body_start:body_end]).strip()

    # --- images ---
    images = []
    for heading, body in sections.items():
        for m in _IMAGE_RE.finditer(body):
            rel = m.group(2)
            # Resolve image path relative to the markdown file's directory
            img_path = (path.parent / rel).resolve()
            b64 = ""
            if img_path.is_file():
                try:
                    data = img_path.read_bytes()
                    if len(data) > MAX_IMAGE_SIZE:
                        print(f"  Warning: {img_path.name} ({len(data)} bytes) exceeds 1MB limit, skipping")
                    elif _detect_image_type(data) is None:
                        print(f"  Warning: {img_path.name} is not a valid image format, skipping")
                    else:
                        b64 = base64.b64encode(data).decode("ascii")
                        print(f"  Encoded {img_path.name} ({len(data)} bytes)")
                except (OSError, MemoryError) as e:
                    print(f"  Error encoding {img_path.name}: {e}")
            else:
                print(f"  Warning: Image not found: {rel}")
            images.append(
                {
                    "alt_text": m.group(1),
                    "relative_path": rel,
                    "section": heading,
                    "base64_data": b64,
                }
            )

    # --- map sections to fields ---
    fields: dict[str, object] = {}
    for heading, body in sections.items():
        field_name = _SECTION_MAP.get(heading)
        if field_name is None:
            continue
        if field_name == "related_context":
            fields[field_name] = _parse_related_context(body)
        elif field_name == "expected_result":
            fields[field_name] = _parse_expected_result(body)
        elif field_name == "failure_modes":
            fields[field_name] = _parse_failure_modes(body)
        elif field_name == "evaluation_criteria":
            criteria_text, check_questions = _parse_evaluation_criteria(body)
            fields["evaluation_criteria"] = criteria_text
            fields["check_questions"] = check_questions
        elif field_name == "output_parameters":
            fields["output_parameters_info"] = _parse_output_parameters(body)
        elif field_name == "analysis_guide":
            fields[field_name] = _parse_analysis_guide(body)
        elif field_name == "tips":
            fields[field_name] = _parse_list_items(body)
        else:
            clean = "\n".join(
                ln for ln in body.splitlines() if not ln.strip().startswith("![")
            ).strip()
            fields[field_name] = clean

    # --- cases ---
    cases = _parse_cases_dir(path.parent)

    # Derive category from directory path: <category>/<TaskName>/index.md
    category = path.parent.parent.name if path.parent.parent != path.parent else ""

    return {
        "name": name,
        "category": category,
        "summary": summary,
        "what_it_measures": fields.get("what_it_measures", ""),
        "physical_principle": fields.get("physical_principle", ""),
        "expected_result": fields.get("expected_result", {
            "description": "", "result_type": "", "x_axis": "", "y_axis": "",
            "z_axis": "", "fit_model": "", "typical_range": "", "good_visual": "",
        }),
        "evaluation_criteria": fields.get("evaluation_criteria", ""),
        "check_questions": fields.get("check_questions", []),
        "failure_modes": fields.get("failure_modes", []),
        "tips": fields.get("tips", []),
        "output_parameters_info": fields.get("output_parameters_info", []),
        "analysis_guide": fields.get("analysis_guide", []),
        "images": images,
        "related_context": fields.get("related_context", []),
        "cases": cases,
    }


# ---------------------------------------------------------------------------
# Index page generator
# ---------------------------------------------------------------------------

# Categories for organising the index page.  Tasks not listed here go into
# "Other".
# (display_name, dir_slug, task_list)
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

# Reverse lookup: task_name -> category dir slug
_TASK_TO_CAT_DIR: dict[str, str] = {}
for _cat_name, _cat_dir, _cat_tasks in _CATEGORIES:
    for _t in _cat_tasks:
        _TASK_TO_CAT_DIR[_t] = _cat_dir

# ---------------------------------------------------------------------------
# Calibration Workflows
# ---------------------------------------------------------------------------
# Workflow definitions corresponding to task lists in
# src/qdash/workflow/service/tasks.py and templates in
# src/qdash/workflow/templates/templates.json.
# (name, description, task_list)

_WORKFLOWS: list[tuple[str, str, list[str]]] = [
    (
        "Bring-up",
        "MUX-level initial characterization. Identifies resonator and qubit frequencies.",
        [
            "CheckResonatorSpectroscopy",
            "CheckQubitSpectroscopy",
            "ChevronPattern",
        ],
    ),
    (
        "1Q Check",
        "Basic single-qubit characterization.",
        [
            "CheckRabi",
            "CheckRabi",
            "CreateHPIPulse",
            "CheckHPIPulse",
            "CheckT1Average",
            "CheckT2EchoAverage",
            "CheckRamsey",
        ],
    ),
    (
        "1Q Fine-tune",
        "Advanced single-qubit calibration including DRAG pulse optimization, "
        "readout classification, and randomized benchmarking.",
        [
            "CheckRabi",
            "CreateHPIPulse",
            "CheckHPIPulse",
            "CreatePIPulse",
            "CheckPIPulse",
            "CreateDRAGHPIPulse",
            "CheckDRAGHPIPulse",
            "CreateDRAGPIPulse",
            "CheckDRAGPIPulse",
            "ReadoutClassification",
            "RandomizedBenchmarking",
            "X90InterleavedRandomizedBenchmarking",
        ],
    ),
    (
        "2Q Calibration",
        "Two-qubit gate calibration from cross-resonance measurement "
        "through ZX90 gate creation to Bell state verification.",
        [
            "CheckCrossResonance",
            "CreateZX90",
            "CheckZX90",
            "CheckBellState",
            "CheckBellStateTomography",
            "ZX90InterleavedRandomizedBenchmarking",
        ],
    ),
]


def _enrich_workflow_context(registry: dict[str, dict]) -> None:
    """Add ``workflow_context`` to each registry entry.

    For every task that appears in a workflow, records which workflow(s) it
    belongs to, its position, the immediately preceding / following tasks,
    and **all** preceding tasks in the workflow (replaces hand-written
    prerequisites).
    """
    for entry in registry.values():
        entry.setdefault("workflow_context", [])

    for wf_name, _wf_desc, wf_tasks in _WORKFLOWS:
        for idx, task_name in enumerate(wf_tasks):
            prev_tasks = [wf_tasks[idx - 1]] if idx > 0 else []
            next_tasks = [wf_tasks[idx + 1]] if idx < len(wf_tasks) - 1 else []
            # Deduplicated, order-preserving list of all preceding tasks
            seen: set[str] = set()
            preceding: list[str] = []
            for t in wf_tasks[:idx]:
                if t not in seen:
                    seen.add(t)
                    preceding.append(t)
            ctx = {
                "workflow": wf_name,
                "step": idx + 1,
                "total_steps": len(wf_tasks),
                "previous": prev_tasks,
                "next": next_tasks,
                "preceding_tasks": preceding,
            }
            if task_name in registry:
                registry[task_name]["workflow_context"].append(ctx)


def _generate_index(registry: dict[str, dict]) -> None:
    """Generate ``index.md`` from the registry entries."""
    categorised: set[str] = set()
    lines: list[str] = [
        "# Task Knowledge",
        "",
        "Calibration task knowledge base for QDash copilot analysis. "
        "Each page describes what a task measures, its physical principle, "
        "expected results, evaluation criteria, common failure patterns, "
        "and tips for improvement.",
        "",
    ]

    for cat_name, cat_dir, cat_tasks in _CATEGORIES:
        lines.append(f"## {cat_name}")
        lines.append("")
        lines.append("| Task | Description |")
        lines.append("|------|-------------|")
        for task_name in cat_tasks:
            entry = registry.get(task_name)
            desc = entry["summary"].split("\n")[0] if entry else ""
            lines.append(f"| [{task_name}](./{cat_dir}/{task_name}) | {desc} |")
            categorised.add(task_name)
        lines.append("")

    # Any tasks not in the predefined categories
    remaining = sorted(set(registry.keys()) - categorised)
    if remaining:
        lines.append("## Other")
        lines.append("")
        lines.append("| Task | Description |")
        lines.append("|------|-------------|")
        for task_name in remaining:
            entry = registry[task_name]
            desc = entry["summary"].split("\n")[0]
            cat_dir = _TASK_TO_CAT_DIR.get(task_name, "")
            prefix = f"./{cat_dir}/" if cat_dir else "./"
            lines.append(f"| [{task_name}]({prefix}{task_name}) | {desc} |")
        lines.append("")

    # ----- Calibration Workflows section -----
    lines.append("## Calibration Workflows")
    lines.append("")
    lines.append(
        "Standard calibration workflows and their task composition. "
        "See [workflow task definitions](https://github.com/oqtopus-team/qdash/blob/"
        "develop/src/qdash/workflow/service/tasks.py) for the source of truth."
    )
    lines.append("")

    for wf_name, wf_desc, wf_tasks in _WORKFLOWS:
        lines.append(f"### {wf_name}")
        lines.append("")
        lines.append(wf_desc)
        lines.append("")

        # Per-workflow mermaid diagram
        lines.append("```mermaid")
        lines.append("flowchart LR")
        seen: dict[str, int] = {}
        for i, task_name in enumerate(wf_tasks):
            seen[task_name] = seen.get(task_name, 0) + 1
            label = task_name
            if wf_tasks.count(task_name) > 1:
                label = f"{task_name} #{seen[task_name]}"
            node_id = f"T{i}"
            lines.append(f"  {node_id}[{label}]")
        for i in range(len(wf_tasks) - 1):
            lines.append(f"  T{i} --> T{i + 1}")
        lines.append("```")
        lines.append("")

        # Numbered task list with links
        seen.clear()
        for idx, task_name in enumerate(wf_tasks, 1):
            seen[task_name] = seen.get(task_name, 0) + 1
            suffix = ""
            if wf_tasks.count(task_name) > 1:
                suffix = f" (#{seen[task_name]})"
            cat_dir = _TASK_TO_CAT_DIR.get(task_name)
            if cat_dir:
                lines.append(f"{idx}. [{task_name}](./{cat_dir}/{task_name}){suffix}")
            else:
                lines.append(f"{idx}. {task_name}{suffix}")
        lines.append("")

    # Full Calibration Pipeline overview with mermaid diagram
    lines.append("### Full Calibration Pipeline")
    lines.append("")
    lines.append(
        "End-to-end calibration runs in the following order: "
        "1Q Check, filter, 1Q Fine-tune, filter, CR schedule generation, "
        "then 2Q Calibration."
    )
    lines.append("")
    lines.append("```mermaid")
    lines.append("flowchart LR")
    lines.append("  A[Bring-up] --> B[1Q Check]")
    lines.append("  B --> C[Filter]")
    lines.append("  C --> D[1Q Fine-tune]")
    lines.append("  D --> E[Filter]")
    lines.append("  E --> F[CR Schedule]")
    lines.append("  F --> G[2Q Calibration]")
    lines.append("```")
    lines.append("")

    index_path = MD_DIR / "index.md"
    index_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Generated {index_path}")


def _generate_sidebar(registry: dict[str, dict]) -> None:
    """Generate ``task-knowledge-sidebar.json`` for VitePress sidebar config."""
    categorised: set[str] = set()
    items: list[dict] = []

    for cat_name, cat_dir, cat_tasks in _CATEGORIES:
        present = [t for t in cat_tasks if t in registry]
        if not present:
            continue
        group: dict = {
            "text": cat_name,
            "collapsed": True,
            "items": [
                {"text": t, "link": f"/task-knowledge/{cat_dir}/{t}"}
                for t in present
            ],
        }
        items.append(group)
        categorised.update(present)

    remaining = sorted(set(registry.keys()) - categorised)
    if remaining:
        items.append({
            "text": "Other",
            "collapsed": True,
            "items": [
                {"text": t, "link": f"/task-knowledge/{_TASK_TO_CAT_DIR.get(t, 'other')}/{t}"}
                for t in remaining
            ],
        })

    SIDEBAR_FILE.write_text(
        json.dumps(items, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Generated {SIDEBAR_FILE}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _scan_and_build(md_dir: Path) -> tuple[dict[str, dict], list[str]]:
    """Scan a directory for ``*/*/index.md`` and build a registry."""
    md_files = sorted(md_dir.glob("*/*/index.md"))
    registry: dict[str, dict] = {}
    errors: list[str] = []

    for md_path in md_files:
        entry = _parse_markdown_file(md_path)
        if entry is None:
            errors.append(f"  SKIP {md_path.parent.name}: no H1 heading found")
            continue

        missing = [
            f
            for f in (
                "summary",
                "what_it_measures",
                "physical_principle",
            )
            if not entry.get(f)
        ]
        er = entry.get("expected_result", {})
        if isinstance(er, dict) and not er.get("description"):
            missing.append("expected_result")
        if not entry.get("evaluation_criteria"):
            missing.append("evaluation_criteria")

        if missing:
            errors.append(f"  WARN {md_path.parent.name}: missing sections: {', '.join(missing)}")

        registry[entry["name"]] = entry
        print(f"  OK   {md_path.parent.name}/index.md -> {entry['name']}")

    return registry, errors


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Generate task-knowledge.json")
    parser.add_argument(
        "--knowledge-dir",
        type=Path,
        default=None,
        help=(
            "Path to an external knowledge repo (e.g. qdash-task-knowledge clone). "
            "If provided, entries from this directory are merged with (and override) "
            "the built-in docs/task-knowledge/ entries."
        ),
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=OUTPUT_FILE,
        help="Output JSON file path",
    )
    args = parser.parse_args()

    # --- Built-in knowledge ---
    registry: dict[str, dict] = {}
    all_errors: list[str] = []

    if MD_DIR.is_dir():
        built_in, errors = _scan_and_build(MD_DIR)
        registry.update(built_in)
        all_errors.extend(errors)
        print(f"Loaded {len(built_in)} entries from {MD_DIR}")
    else:
        print(f"Note: built-in directory not found: {MD_DIR}")

    # --- External knowledge repo (overrides/supplements built-in) ---
    if args.knowledge_dir:
        ext_dir = args.knowledge_dir.resolve()
        if ext_dir.is_dir():
            external, ext_errors = _scan_and_build(ext_dir)
            # Merge: external entries override built-in, but preserve
            # built-in entries for tasks not in external repo.
            # Cases from external repo supplement built-in cases.
            for name, ext_entry in external.items():
                if name in registry:
                    # Merge cases: external cases supplement existing
                    existing_cases = registry[name].get("cases", [])
                    ext_cases = ext_entry.get("cases", [])
                    ext_entry["cases"] = existing_cases + ext_cases
                registry[name] = ext_entry
            all_errors.extend(ext_errors)
            print(f"Merged {len(external)} entries from {ext_dir}")
        else:
            print(f"WARNING: --knowledge-dir not found: {ext_dir}", file=sys.stderr)

    if not registry:
        print("ERROR: No knowledge entries found", file=sys.stderr)
        return 1

    if all_errors:
        print("\nWarnings:")
        for e in all_errors:
            print(e)

    _enrich_workflow_context(registry)

    output_file: Path = args.output
    output_file.write_text(
        json.dumps(registry, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"\nGenerated {output_file} ({len(registry)} entries)")

    _generate_index(registry)
    _generate_sidebar(registry)
    return 0


if __name__ == "__main__":
    sys.exit(main())
