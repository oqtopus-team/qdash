#!/usr/bin/env python3
"""Generate task-knowledge.json from docs/reference/task-knowledge/*.md.

Parses all Markdown knowledge files and produces a single JSON registry
that the application loads at runtime.  Run via ``task knowledge`` or
directly with ``uv run scripts/generate_task_knowledge.py``.

Usage:
    uv run scripts/generate_task_knowledge.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
MD_DIR = REPO_ROOT / "docs" / "reference" / "task-knowledge"
OUTPUT_FILE = REPO_ROOT / "config" / "task-knowledge.json"

# ---------------------------------------------------------------------------
# Markdown parser (standalone – no project imports required)
# ---------------------------------------------------------------------------

# H2 heading (lowercase) → field name
_SECTION_MAP: dict[str, str] = {
    "what it measures": "what_it_measures",
    "physical principle": "physical_principle",
    "expected curve": "expected_curve",
    "expected graph": "expected_curve",
    "evaluation criteria": "good_threshold",
    "common failure patterns": "failure_modes",
    "common failure modes": "failure_modes",
    "tips for improvement": "tips",
    "tips": "tips",
    "related context": "related_context",
}

_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
_RELATED_CONTEXT_RE = re.compile(r"-\s+(history|neighbor_qubits|coupling)\(([^)]*)\)")


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
            images.append(
                {
                    "alt_text": m.group(1),
                    "relative_path": m.group(2),
                    "section": heading,
                }
            )

    # --- map sections to fields ---
    fields: dict[str, str | list[str] | list[dict]] = {}
    for heading, body in sections.items():
        field_name = _SECTION_MAP.get(heading)
        if field_name is None:
            continue
        if field_name == "related_context":
            fields[field_name] = _parse_related_context(body)
        elif field_name in ("failure_modes", "tips"):
            fields[field_name] = _parse_list_items(body)
        else:
            clean = "\n".join(
                ln for ln in body.splitlines() if not ln.strip().startswith("![")
            ).strip()
            fields[field_name] = clean

    return {
        "name": name,
        "summary": summary,
        "what_it_measures": fields.get("what_it_measures", ""),
        "physical_principle": fields.get("physical_principle", ""),
        "expected_curve": fields.get("expected_curve", ""),
        "good_threshold": fields.get("good_threshold", ""),
        "failure_modes": fields.get("failure_modes", []),
        "tips": fields.get("tips", []),
        "raw_markdown": raw,
        "images": images,
        "related_context": fields.get("related_context", []),
    }


# ---------------------------------------------------------------------------
# Index page generator
# ---------------------------------------------------------------------------

# Categories for organising the index page.  Tasks not listed here go into
# "Other".
_CATEGORIES: list[tuple[str, list[str]]] = [
    (
        "One-Qubit Calibration",
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
        ],
    ),
    (
        "Gate Calibration",
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
        "Two-Qubit Calibration",
        [
            "CheckCrossResonance",
            "ChevronPattern",
            "CheckZX90",
            "CreateZX90",
            "CheckBellState",
            "CheckBellStateTomography",
        ],
    ),
    (
        "Benchmarking",
        [
            "RandomizedBenchmarking",
            "X90InterleavedRandomizedBenchmarking",
            "X180InterleavedRandomizedBenchmarking",
            "ZX90InterleavedRandomizedBenchmarking",
        ],
    ),
]


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

    for cat_name, cat_tasks in _CATEGORIES:
        lines.append(f"## {cat_name}")
        lines.append("")
        lines.append("| Task | Description |")
        lines.append("|------|-------------|")
        for task_name in cat_tasks:
            entry = registry.get(task_name)
            desc = entry["summary"].split("\n")[0] if entry else ""
            lines.append(f"| [{task_name}](./{task_name}) | {desc} |")
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
            lines.append(f"| [{task_name}](./{task_name}) | {desc} |")
        lines.append("")

    index_path = MD_DIR / "index.md"
    index_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Generated {index_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    if not MD_DIR.is_dir():
        print(f"ERROR: Markdown directory not found: {MD_DIR}", file=sys.stderr)
        return 1

    md_files = sorted(p for p in MD_DIR.glob("*.md") if p.name != "index.md")
    if not md_files:
        print(f"ERROR: No .md files found in {MD_DIR}", file=sys.stderr)
        return 1

    registry: dict[str, dict] = {}
    errors: list[str] = []

    for md_path in md_files:
        entry = _parse_markdown_file(md_path)
        if entry is None:
            errors.append(f"  SKIP {md_path.name}: no H1 heading found")
            continue

        missing = [
            f
            for f in (
                "summary",
                "what_it_measures",
                "physical_principle",
                "expected_curve",
                "good_threshold",
            )
            if not entry.get(f)
        ]
        if missing:
            errors.append(f"  WARN {md_path.name}: missing sections: {', '.join(missing)}")

        registry[entry["name"]] = entry
        print(f"  OK   {md_path.name} -> {entry['name']}")

    if errors:
        print("\nWarnings:")
        for e in errors:
            print(e)

    OUTPUT_FILE.write_text(
        json.dumps(registry, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"\nGenerated {OUTPUT_FILE} ({len(registry)} entries)")

    _generate_index(registry)
    return 0


if __name__ == "__main__":
    sys.exit(main())
