from __future__ import annotations

from datetime import UTC, datetime

from scripts.cleanup_legacy_ai_review_user_notes import (
    apply_cleanup_plan,
    build_cleanup_plan,
    split_legacy_ai_generated_note,
)


def _doc(content: str, *, ai_review_content: str = "") -> dict:
    return {
        "_id": "doc-1",
        "project_id": "proj-1",
        "task_id": "task-1",
        "user_note": {
            "content": content,
            "updated_by": "alice",
            "updated_at": datetime(2026, 5, 1, tzinfo=UTC),
        },
        "ai_review_note": {
            "content": ai_review_content,
            "updated_by": "",
            "updated_at": None,
        },
    }


class _Collection:
    def __init__(self) -> None:
        self.update_filter = None
        self.update_doc = None

    def update_one(self, update_filter, update_doc):
        self.update_filter = update_filter
        self.update_doc = update_doc

        class _Result:
            modified_count = 1

        return _Result()


def test_split_legacy_ai_generated_note_preserves_user_followup() -> None:
    user_content, ai_content = split_legacy_ai_generated_note(
        "## AI review\n\n- Decision: `PASS`\n\n---\n\noperator follow-up"
    )

    assert ai_content == "## AI review\n\n- Decision: `PASS`\n\n---"
    assert user_content == "operator follow-up"


def test_build_cleanup_plan_copies_when_ai_review_note_empty() -> None:
    plan = build_cleanup_plan(_doc("## AI review\n\n- Decision: `REVIEW`\n"))

    assert plan is not None
    assert plan.task_id == "task-1"
    assert plan.user_note_content == ""
    assert plan.set_ai_review_note is True


def test_build_cleanup_plan_cleans_only_when_ai_review_note_exists() -> None:
    plan = build_cleanup_plan(
        _doc(
            "## AI review\n\n- Decision: `REVIEW`\n\n---\n\noperator follow-up",
            ai_review_content="## AI review\n\n- Decision: `PASS`\n",
        )
    )

    assert plan is not None
    assert plan.user_note_content == "operator follow-up"
    assert plan.set_ai_review_note is False


def test_apply_cleanup_plan_resets_empty_user_note_and_sets_ai_review_note() -> None:
    collection = _Collection()
    wrote = apply_cleanup_plan(collection, _doc("## AI review\n\n- Decision: `FAIL`\n"))

    assert wrote is True
    assert collection.update_filter == {"_id": "doc-1"}
    set_fields = collection.update_doc["$set"]
    assert set_fields["user_note"] == {"content": "", "updated_by": "", "updated_at": None}
    assert set_fields["ai_review_note"]["content"] == "## AI review\n\n- Decision: `FAIL`"
    assert set_fields["ai_review_note"]["updated_by"] == "alice"


def test_apply_cleanup_plan_preserves_user_followup_metadata() -> None:
    collection = _Collection()
    apply_cleanup_plan(
        collection,
        _doc("## AI triage **Review triage**\n\n---\n\noperator follow-up"),
    )

    user_note = collection.update_doc["$set"]["user_note"]
    assert user_note["content"] == "operator follow-up"
    assert user_note["updated_by"] == "alice"
