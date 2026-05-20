#!/usr/bin/env python3
"""Move legacy AI review markdown out of task-result user notes.

Older QDash builds stored AI review markdown at the start of
``task_result_history.user_note.content``. Current builds store it in
``ai_review_note`` so user notes remain user-authored. This script removes the
legacy AI-generated section from ``user_note`` and, when ``ai_review_note`` is
empty, copies that section into ``ai_review_note``.

Usage:
    uv run scripts/cleanup_legacy_ai_review_user_notes.py --dry-run
    uv run scripts/cleanup_legacy_ai_review_user_notes.py --apply
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from pymongo import MongoClient

if TYPE_CHECKING:
    from pymongo.collection import Collection

AI_REVIEW_ACTOR = "qdash-ai"

_AI_GENERATED_NOTE_RE = re.compile(
    r"^\s*(?:(?:#{1,6}\s*)?AI\s+(?:review|triage)|\*\*AI\s+(?:review|triage)\*\*)"
    r"\b[\s\S]*?(?:\r?\n\r?\n---\r?\n\r?\n|$)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CleanupPlan:
    task_id: str
    project_id: str | None
    legacy_ai_review_content: str
    user_note_content: str
    set_ai_review_note: bool


def split_legacy_ai_generated_note(content: str) -> tuple[str, str]:
    """Return ``(user_content, ai_review_content)`` for legacy mixed notes."""
    match = _AI_GENERATED_NOTE_RE.search(content or "")
    if match is None:
        return content.strip(), ""
    return content[match.end() :].strip(), match.group(0).strip()


def build_cleanup_plan(doc: dict[str, Any]) -> CleanupPlan | None:
    """Build a mutation plan for one task_result_history document."""
    user_note = doc.get("user_note") or {}
    user_note_content = str(user_note.get("content") or "")
    clean_user_content, legacy_ai_review_content = split_legacy_ai_generated_note(
        user_note_content
    )
    if not legacy_ai_review_content:
        return None

    ai_review_note = doc.get("ai_review_note") or {}
    set_ai_review_note = not bool(str(ai_review_note.get("content") or "").strip())
    return CleanupPlan(
        task_id=str(doc.get("task_id") or ""),
        project_id=doc.get("project_id"),
        legacy_ai_review_content=legacy_ai_review_content,
        user_note_content=clean_user_content,
        set_ai_review_note=set_ai_review_note,
    )


def _empty_note() -> dict[str, Any]:
    return {"content": "", "updated_by": "", "updated_at": None}


def _user_note_update(original_user_note: dict[str, Any], content: str) -> dict[str, Any]:
    if not content:
        return _empty_note()
    updated = dict(original_user_note)
    updated["content"] = content
    return updated


def _ai_review_note_update(original_user_note: dict[str, Any], content: str) -> dict[str, Any]:
    updated_by = str(original_user_note.get("updated_by") or "") or AI_REVIEW_ACTOR
    return {
        "content": content,
        "updated_by": updated_by,
        "updated_at": original_user_note.get("updated_at") or datetime.now(UTC),
    }


def apply_cleanup_plan(collection: Collection[dict[str, Any]], doc: dict[str, Any]) -> bool:
    """Apply the cleanup for one document. Returns True when a write occurred."""
    plan = build_cleanup_plan(doc)
    if plan is None:
        return False

    user_note = doc.get("user_note") or {}
    set_fields: dict[str, Any] = {
        "user_note": _user_note_update(user_note, plan.user_note_content),
    }
    if plan.set_ai_review_note:
        set_fields["ai_review_note"] = _ai_review_note_update(
            user_note,
            plan.legacy_ai_review_content,
        )

    result = collection.update_one({"_id": doc["_id"]}, {"$set": set_fields})
    return result.modified_count > 0


def _mongo_uri() -> str:
    if uri := os.getenv("MONGO_URI"):
        return uri
    user = os.getenv("MONGO_INITDB_ROOT_USERNAME")
    password = os.getenv("MONGO_INITDB_ROOT_PASSWORD")
    host = os.getenv("MONGO_HOST", "localhost")
    port = os.getenv("MONGO_PORT", "27017")
    if user and password:
        return f"mongodb://{user}:{password}@{host}:{port}/"
    return f"mongodb://{host}:{port}/"


def _query(args: argparse.Namespace) -> dict[str, Any]:
    query: dict[str, Any] = {
        "user_note.content": {
            "$regex": r"^\s*(?:(?:#{1,6}\s*)?AI\s+(?:review|triage)|\*\*AI\s+(?:review|triage)\*\*)",
            "$options": "i",
        }
    }
    if args.project_id:
        query["project_id"] = args.project_id
    if args.chip_id:
        query["chip_id"] = args.chip_id
    if args.task_id:
        query["task_id"] = args.task_id
    return query


def run(args: argparse.Namespace) -> int:
    client: MongoClient[Any] = MongoClient(_mongo_uri())
    db = client[os.getenv("MONGO_DB_NAME", "qdash")]
    collection = db["task_result_history"]

    scanned = 0
    matched = 0
    updated = 0
    copied_to_ai_review_note = 0
    examples: list[CleanupPlan] = []

    cursor = collection.find(_query(args)).sort("start_at", -1)
    if args.limit:
        cursor = cursor.limit(args.limit)

    for doc in cursor:
        scanned += 1
        plan = build_cleanup_plan(doc)
        if plan is None:
            continue
        matched += 1
        if plan.set_ai_review_note:
            copied_to_ai_review_note += 1
        if len(examples) < args.examples:
            examples.append(plan)
        if args.apply:
            updated += int(apply_cleanup_plan(collection, doc))

    mode = "APPLY" if args.apply else "DRY RUN"
    print(f"Mode: {mode}")
    print(f"Scanned candidate docs: {scanned}")
    print(f"Matched legacy AI review user notes: {matched}")
    print(f"Would copy to ai_review_note: {copied_to_ai_review_note}")
    if args.apply:
        print(f"Updated docs: {updated}")
    if examples:
        print("Examples:")
        for plan in examples:
            action = "copy+clean" if plan.set_ai_review_note else "clean-only"
            user_state = "empty user_note" if not plan.user_note_content else "preserve user text"
            print(f"  - {plan.task_id} ({plan.project_id or '-'}) {action}, {user_state}")

    client.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Remove legacy AI review markdown from task-result user notes."
    )
    parser.add_argument("--apply", action="store_true", help="Write changes to MongoDB")
    parser.add_argument("--dry-run", action="store_true", help="Preview only (default)")
    parser.add_argument("--project-id", help="Limit cleanup to one project")
    parser.add_argument("--chip-id", help="Limit cleanup to one chip")
    parser.add_argument("--task-id", help="Limit cleanup to one task result")
    parser.add_argument("--limit", type=int, default=0, help="Maximum number of candidates to scan")
    parser.add_argument("--examples", type=int, default=10, help="Number of example task IDs to print")
    args = parser.parse_args()

    if args.apply and args.dry_run:
        print("ERROR: --apply and --dry-run are mutually exclusive", file=sys.stderr)
        return 2
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
