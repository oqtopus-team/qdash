from qdash.dbmodel.forum import ForumLabelDocument, ForumPostDocument
from qdash.dbmodel.forum_label_db_migration import backfill_forum_labels


def _post(project_id: str, labels: list[str]) -> ForumPostDocument:
    """Insert a root forum post with the given labels."""
    return ForumPostDocument(
        project_id=project_id,
        category="qubit",
        username="owner",
        title="Thread",
        content="root",
        labels=labels,
    ).insert()


def _label(project_id: str, key: str) -> ForumLabelDocument | None:
    """Fetch a label definition by project and key."""
    return ForumLabelDocument.find_one({"project_id": project_id, "key": key}).run()


def test_backfill_forum_labels_dry_run_creates_nothing(init_db):
    """Dry-run reports stats without creating label definitions."""
    _post("project-a", ["review", "anomaly"])

    stats = backfill_forum_labels()

    assert stats["labels_found"] == 2
    assert stats["labels_to_create"] == 2
    assert stats["labels_created"] == 0
    assert stats["labels_existing"] == 0
    assert ForumLabelDocument.find({}).count() == 0


def test_backfill_forum_labels_creates_missing_keys_per_project(init_db):
    """Execute creates one neutral label per missing project and key pair."""
    _post("project-a", ["review"])
    _post("project-b", ["review", "anomaly"])

    stats = backfill_forum_labels(dry_run=False)

    assert stats["labels_created"] == 3
    assert ForumLabelDocument.find({}).count() == 3
    label = _label("project-b", "review")
    assert label is not None
    assert label.name == "review"
    assert label.description == ""
    assert label.color == "#6b7280"
    assert _label("project-a", "review") is not None
    assert _label("project-a", "anomaly") is None


def test_backfill_forum_labels_keeps_existing_definitions(init_db):
    """Existing label definitions keep their name and color."""
    ForumLabelDocument(
        project_id="project-a", key="review", name="Review", color="#3b82f6"
    ).insert()
    _post("project-a", ["review", "anomaly"])

    stats = backfill_forum_labels(dry_run=False)

    assert stats["labels_found"] == 2
    assert stats["labels_created"] == 1
    assert stats["labels_existing"] == 1
    review = _label("project-a", "review")
    assert review is not None
    assert review.name == "Review"
    assert review.color == "#3b82f6"


def test_backfill_forum_labels_is_idempotent(init_db):
    """A second run finds every label defined and creates nothing."""
    _post("project-a", ["review"])
    backfill_forum_labels(dry_run=False)

    stats = backfill_forum_labels(dry_run=False)

    assert stats["labels_to_create"] == 0
    assert stats["labels_created"] == 0
    assert stats["labels_existing"] == 1
    assert ForumLabelDocument.find({}).count() == 1
