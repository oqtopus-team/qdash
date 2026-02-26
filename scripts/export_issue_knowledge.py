#!/usr/bin/env python3
"""Export approved issue-knowledge cases to Markdown files.

Reads approved ``IssueKnowledgeDocument`` entries from MongoDB and writes
them as case Markdown files under ``docs/task-knowledge/<category>/<Task>/cases/``.

Usage:
    uv run scripts/export_issue_knowledge.py [--project-id PROJECT_ID]
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MD_DIR = REPO_ROOT / "docs" / "task-knowledge"

# Build reverse lookup: task_name -> category_dir/task_name path
# Reuse the category definitions from generate_task_knowledge.py
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from generate_task_knowledge import _TASK_TO_CAT_DIR  # noqa: E402


def _slugify(text: str) -> str:
    """Convert a title to a filename-safe slug."""
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug[:80].strip("-")


def _case_to_markdown(case: dict) -> str:
    """Convert a case dict to Markdown content."""
    lines = [f"# {case['title']}", ""]

    meta = []
    if case.get("date"):
        meta.append(f"- date: {case['date']}")
    if case.get("severity"):
        meta.append(f"- severity: {case['severity']}")
    if case.get("chip_id"):
        meta.append(f"- chip_id: {case['chip_id']}")
    if case.get("qid"):
        meta.append(f"- qid: {case['qid']}")
    if case.get("resolution_status"):
        meta.append(f"- status: {case['resolution_status']}")
    if case.get("issue_id"):
        meta.append(f"- issue_id: {case['issue_id']}")
    if meta:
        lines.extend(meta)
        lines.append("")

    if case.get("symptom"):
        lines.extend(["## Symptom", "", case["symptom"], ""])
    if case.get("root_cause"):
        lines.extend(["## Root cause", "", case["root_cause"], ""])
    if case.get("resolution"):
        lines.extend(["## Resolution", "", case["resolution"], ""])
    if case.get("lesson_learned"):
        lines.append("## Lesson learned")
        lines.append("")
        for lesson in case["lesson_learned"]:
            lines.append(f"- {lesson}")
        lines.append("")

    if case.get("figure_paths") or case.get("thread_image_urls"):
        lines.append("## Images")
        lines.append("")
        for fp in case.get("figure_paths", []):
            lines.append(f"![Task figure]({fp})")
        for url in case.get("thread_image_urls", []):
            lines.append(f"![Thread image]({url})")
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Export approved issue knowledge to Markdown")
    parser.add_argument("--project-id", default=None, help="Filter by project ID")
    args = parser.parse_args()

    # Initialize MongoDB connection
    from qdash.dbmodel.initialize import initialize

    initialize()
    from qdash.dbmodel.issue_knowledge import IssueKnowledgeDocument

    query: dict[str, object] = {"status": "approved"}
    if args.project_id:
        query["project_id"] = args.project_id

    docs = IssueKnowledgeDocument.find(query).sort("system_info.created_at").to_list()

    if not docs:
        print("No approved knowledge cases found.")
        return 0

    written = 0
    for doc in docs:
        task_name = doc.task_name
        if not task_name:
            print(f"  SKIP {doc.id}: no task_name")
            continue

        cat_dir = _TASK_TO_CAT_DIR.get(task_name)
        if cat_dir:
            task_dir = MD_DIR / cat_dir / task_name
        else:
            print(f"  WARN {doc.id}: task '{task_name}' not in known categories, using 'other'")
            task_dir = MD_DIR / "other" / task_name

        cases_dir = task_dir / "cases"
        cases_dir.mkdir(parents=True, exist_ok=True)

        date_prefix = doc.date or "unknown"
        slug = _slugify(doc.title)
        filename = f"{date_prefix}_{slug}.md"
        filepath = cases_dir / filename

        if filepath.exists():
            print(f"  EXISTS {filepath.relative_to(REPO_ROOT)}")
            continue

        case_data = {
            "title": doc.title,
            "date": doc.date,
            "severity": doc.severity,
            "chip_id": doc.chip_id,
            "qid": doc.qid,
            "resolution_status": doc.resolution_status,
            "issue_id": doc.issue_id,
            "symptom": doc.symptom,
            "root_cause": doc.root_cause,
            "resolution": doc.resolution,
            "lesson_learned": doc.lesson_learned,
            "figure_paths": doc.figure_paths,
            "thread_image_urls": doc.thread_image_urls,
        }

        content = _case_to_markdown(case_data)
        filepath.write_text(content, encoding="utf-8")
        print(f"  WROTE {filepath.relative_to(REPO_ROOT)}")
        written += 1

    print(f"\nExported {written} knowledge cases ({len(docs)} total approved)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
