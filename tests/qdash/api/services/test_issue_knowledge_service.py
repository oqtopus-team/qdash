"""Tests for IssueKnowledgeService."""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from qdash.api.schemas.issue_knowledge import (
    IssueKnowledgeResponse,
    ListIssueKnowledgeResponse,
)
from qdash.api.schemas.success import SuccessResponse
from qdash.api.services.issue_knowledge_service import IssueKnowledgeService
from starlette.exceptions import HTTPException

# Valid 24-character hex strings for ObjectId
VALID_OID = "6640a1b2c3d4e5f6a7b8c9d0"
VALID_OID_2 = "6640a1b2c3d4e5f6a7b8c9d1"
VALID_OID_3 = "6640a1b2c3d4e5f6a7b8c9d2"


def _make_system_info(
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
) -> MagicMock:
    """Build a mock SystemInfoModel."""
    info = MagicMock()
    info.created_at = created_at or datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    info.updated_at = updated_at or datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    return info


_SENTINEL = object()


def _make_doc(
    *,
    doc_id: str = VALID_OID,
    project_id: str = "proj-1",
    issue_id: str = "issue-1",
    task_id: str = "task-1",
    task_name: str = "CheckT1",
    status: str = "draft",
    title: str = "T1 degradation on Q0",
    date: str = "2025-06-01",
    severity: str = "warning",
    chip_id: str = "chip-A",
    qid: str = "Q0",
    resolution_status: str = "resolved",
    symptom: str = "T1 dropped below threshold",
    root_cause: str = "Cosmic ray event",
    resolution: str = "Recalibrated qubit",
    lesson_learned: list[str] | object = _SENTINEL,
    figure_paths: list[str] | object = _SENTINEL,
    thread_image_urls: list[str] | object = _SENTINEL,
    reviewed_by: str | None = None,
    pr_url: str | None = None,
    system_info: MagicMock | None = None,
) -> MagicMock:
    """Build a mock IssueKnowledgeDocument."""
    doc = MagicMock()
    doc.id = doc_id
    doc.project_id = project_id
    doc.issue_id = issue_id
    doc.task_id = task_id
    doc.task_name = task_name
    doc.status = status
    doc.title = title
    doc.date = date
    doc.severity = severity
    doc.chip_id = chip_id
    doc.qid = qid
    doc.resolution_status = resolution_status
    doc.symptom = symptom
    doc.root_cause = root_cause
    doc.resolution = resolution
    doc.lesson_learned = (
        ["Always check T1 after cooldown"] if lesson_learned is _SENTINEL else lesson_learned
    )
    doc.figure_paths = [] if figure_paths is _SENTINEL else figure_paths
    doc.thread_image_urls = [] if thread_image_urls is _SENTINEL else thread_image_urls
    doc.reviewed_by = reviewed_by
    doc.pr_url = pr_url
    doc.system_info = system_info or _make_system_info()
    return doc


class TestToResponse:
    """Tests for IssueKnowledgeService._to_response."""

    def test_converts_all_fields(self):
        """_to_response maps every document field to the response schema."""
        doc = _make_doc(
            doc_id="id-1",
            issue_id="iss-42",
            task_id="tid-7",
            task_name="CheckRabi",
            status="approved",
            title="Rabi oscillation failure",
            date="2025-07-01",
            severity="critical",
            chip_id="chip-B",
            qid="Q3",
            resolution_status="workaround",
            symptom="No Rabi signal",
            root_cause="Drive amplitude misconfigured",
            resolution="Set amplitude to 0.5",
            lesson_learned=["Verify amplitude before run"],
            figure_paths=["/data/fig1.png"],
            thread_image_urls=["https://img.example.com/1.png"],
            reviewed_by="alice",
            pr_url="https://github.com/org/repo/pull/1",
        )

        resp = IssueKnowledgeService._to_response(doc)

        assert isinstance(resp, IssueKnowledgeResponse)
        assert resp.id == "id-1"
        assert resp.issue_id == "iss-42"
        assert resp.task_id == "tid-7"
        assert resp.task_name == "CheckRabi"
        assert resp.status == "approved"
        assert resp.title == "Rabi oscillation failure"
        assert resp.date == "2025-07-01"
        assert resp.severity == "critical"
        assert resp.chip_id == "chip-B"
        assert resp.qid == "Q3"
        assert resp.resolution_status == "workaround"
        assert resp.symptom == "No Rabi signal"
        assert resp.root_cause == "Drive amplitude misconfigured"
        assert resp.resolution == "Set amplitude to 0.5"
        assert resp.lesson_learned == ["Verify amplitude before run"]
        assert resp.figure_paths == ["/data/fig1.png"]
        assert resp.thread_image_urls == ["https://img.example.com/1.png"]
        assert resp.reviewed_by == "alice"
        assert resp.pr_url == "https://github.com/org/repo/pull/1"
        assert resp.created_at == doc.system_info.created_at
        assert resp.updated_at == doc.system_info.updated_at

    def test_handles_empty_optional_fields(self):
        """_to_response works when optional fields are None/empty."""
        doc = _make_doc(
            reviewed_by=None,
            pr_url=None,
            figure_paths=[],
            thread_image_urls=[],
            lesson_learned=[],
        )
        resp = IssueKnowledgeService._to_response(doc)

        assert resp.reviewed_by is None
        assert resp.pr_url is None
        assert resp.figure_paths == []
        assert resp.thread_image_urls == []
        assert resp.lesson_learned == []


class TestBuildThreadText:
    """Tests for IssueKnowledgeService._build_thread_text."""

    def test_original_only(self):
        """Returns formatted original when there are no replies."""
        result = IssueKnowledgeService._build_thread_text("Problem description", [])
        assert result == "[Original] Problem description"

    def test_with_user_and_ai_replies(self):
        """Formats user and AI replies with correct labels."""
        replies = [
            {"content": "Can you elaborate?", "is_ai": False},
            {"content": "Here is my analysis.", "is_ai": True},
        ]
        result = IssueKnowledgeService._build_thread_text("Initial report", replies)

        assert "[Original] Initial report" in result
        assert "[User] Can you elaborate?" in result
        assert "[AI] Here is my analysis." in result

    def test_multiple_replies_separated_by_double_newlines(self):
        """Parts are separated by double newlines."""
        replies = [
            {"content": "Reply 1", "is_ai": False},
            {"content": "Reply 2", "is_ai": True},
        ]
        result = IssueKnowledgeService._build_thread_text("Root", replies)
        parts = result.split("\n\n")
        assert len(parts) == 3

    def test_is_ai_missing_defaults_to_user(self):
        """When is_ai key is absent, role defaults to User."""
        replies = [{"content": "No is_ai key"}]
        result = IssueKnowledgeService._build_thread_text("Root", replies)
        assert "[User] No is_ai key" in result


class TestListKnowledge:
    """Tests for IssueKnowledgeService.list_knowledge."""

    @pytest.fixture
    def service(self):
        return IssueKnowledgeService()

    def _mock_find_chain(self, mock_doc_cls, docs, total):
        """Wire up a mock find chain returning the given docs and total."""
        chain = MagicMock()
        chain.count.return_value = total
        chain.sort.return_value = chain
        chain.skip.return_value = chain
        chain.limit.return_value = chain
        chain.to_list.return_value = docs
        mock_doc_cls.find.return_value = chain
        return chain

    @patch("qdash.api.services.issue_knowledge_service.IssueKnowledgeDocument")
    def test_returns_paginated_response(self, mock_doc_cls, service):
        """list_knowledge returns ListIssueKnowledgeResponse with items, total, skip, limit."""
        docs = [_make_doc(doc_id=f"id-{i}") for i in range(3)]
        self._mock_find_chain(mock_doc_cls, docs, 3)

        result = service.list_knowledge("proj-1", skip=0, limit=10)

        assert isinstance(result, ListIssueKnowledgeResponse)
        assert result.total == 3
        assert result.skip == 0
        assert result.limit == 10
        assert len(result.items) == 3

    @patch("qdash.api.services.issue_knowledge_service.IssueKnowledgeDocument")
    def test_filters_by_status(self, mock_doc_cls, service):
        """list_knowledge includes status in query when provided."""
        self._mock_find_chain(mock_doc_cls, [], 0)

        service.list_knowledge("proj-1", status="draft")

        call_args = mock_doc_cls.find.call_args_list[0][0][0]
        assert call_args["status"] == "draft"

    @patch("qdash.api.services.issue_knowledge_service.IssueKnowledgeDocument")
    def test_filters_by_task_name(self, mock_doc_cls, service):
        """list_knowledge includes task_name in query when provided."""
        self._mock_find_chain(mock_doc_cls, [], 0)

        service.list_knowledge("proj-1", task_name="CheckT1")

        call_args = mock_doc_cls.find.call_args_list[0][0][0]
        assert call_args["task_name"] == "CheckT1"

    @patch("qdash.api.services.issue_knowledge_service.IssueKnowledgeDocument")
    def test_no_filters_queries_only_project(self, mock_doc_cls, service):
        """list_knowledge queries only project_id when no filters given."""
        self._mock_find_chain(mock_doc_cls, [], 0)

        service.list_knowledge("proj-1")

        call_args = mock_doc_cls.find.call_args_list[0][0][0]
        assert call_args == {"project_id": "proj-1"}

    @patch("qdash.api.services.issue_knowledge_service.IssueKnowledgeDocument")
    def test_empty_result(self, mock_doc_cls, service):
        """list_knowledge returns empty items when no documents match."""
        self._mock_find_chain(mock_doc_cls, [], 0)

        result = service.list_knowledge("proj-1")

        assert result.items == []
        assert result.total == 0

    @patch("qdash.api.services.issue_knowledge_service.IssueKnowledgeDocument")
    def test_passes_skip_and_limit(self, mock_doc_cls, service):
        """list_knowledge passes skip and limit to the query chain."""
        chain = self._mock_find_chain(mock_doc_cls, [], 0)

        service.list_knowledge("proj-1", skip=10, limit=25)

        chain.skip.assert_called_once_with(10)
        chain.limit.assert_called_once_with(25)


class TestGetKnowledge:
    """Tests for IssueKnowledgeService.get_knowledge."""

    @pytest.fixture
    def service(self):
        return IssueKnowledgeService()

    @patch("qdash.api.services.issue_knowledge_service.IssueKnowledgeDocument")
    def test_returns_response_when_found(self, mock_doc_cls, service):
        """get_knowledge returns IssueKnowledgeResponse for existing doc."""
        doc = _make_doc()
        mock_doc_cls.find_one.return_value.run.return_value = doc

        result = service.get_knowledge("proj-1", VALID_OID)

        assert isinstance(result, IssueKnowledgeResponse)
        assert result.id == VALID_OID

    @patch("qdash.api.services.issue_knowledge_service.IssueKnowledgeDocument")
    def test_raises_404_when_not_found(self, mock_doc_cls, service):
        """get_knowledge raises HTTPException 404 when doc is missing."""
        mock_doc_cls.find_one.return_value.run.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            service.get_knowledge("proj-1", VALID_OID)

        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail.lower()


class TestUpdateKnowledge:
    """Tests for IssueKnowledgeService.update_knowledge."""

    @pytest.fixture
    def service(self):
        return IssueKnowledgeService()

    @patch("qdash.api.services.issue_knowledge_service.IssueKnowledgeDocument")
    def test_updates_title(self, mock_doc_cls, service):
        """update_knowledge sets the title field."""
        doc = _make_doc(status="draft")
        mock_doc_cls.find_one.return_value.run.return_value = doc

        service.update_knowledge("proj-1", VALID_OID, title="New title")

        assert doc.title == "New title"
        doc.save.assert_called_once()

    @patch("qdash.api.services.issue_knowledge_service.IssueKnowledgeDocument")
    def test_updates_severity(self, mock_doc_cls, service):
        """update_knowledge sets the severity field."""
        doc = _make_doc(status="draft")
        mock_doc_cls.find_one.return_value.run.return_value = doc

        service.update_knowledge("proj-1", VALID_OID, severity="critical")

        assert doc.severity == "critical"

    @patch("qdash.api.services.issue_knowledge_service.IssueKnowledgeDocument")
    def test_updates_symptom(self, mock_doc_cls, service):
        """update_knowledge sets the symptom field."""
        doc = _make_doc(status="draft")
        mock_doc_cls.find_one.return_value.run.return_value = doc

        service.update_knowledge("proj-1", VALID_OID, symptom="New symptom text")

        assert doc.symptom == "New symptom text"

    @patch("qdash.api.services.issue_knowledge_service.IssueKnowledgeDocument")
    def test_updates_root_cause(self, mock_doc_cls, service):
        """update_knowledge sets the root_cause field."""
        doc = _make_doc(status="draft")
        mock_doc_cls.find_one.return_value.run.return_value = doc

        service.update_knowledge("proj-1", VALID_OID, root_cause="New root cause")

        assert doc.root_cause == "New root cause"

    @patch("qdash.api.services.issue_knowledge_service.IssueKnowledgeDocument")
    def test_updates_resolution(self, mock_doc_cls, service):
        """update_knowledge sets the resolution field."""
        doc = _make_doc(status="draft")
        mock_doc_cls.find_one.return_value.run.return_value = doc

        service.update_knowledge("proj-1", VALID_OID, resolution="New resolution")

        assert doc.resolution == "New resolution"

    @patch("qdash.api.services.issue_knowledge_service.IssueKnowledgeDocument")
    def test_updates_lesson_learned(self, mock_doc_cls, service):
        """update_knowledge sets the lesson_learned field."""
        doc = _make_doc(status="draft")
        mock_doc_cls.find_one.return_value.run.return_value = doc

        service.update_knowledge("proj-1", VALID_OID, lesson_learned=["Lesson A", "Lesson B"])

        assert doc.lesson_learned == ["Lesson A", "Lesson B"]

    @patch("qdash.api.services.issue_knowledge_service.IssueKnowledgeDocument")
    def test_updates_multiple_fields_at_once(self, mock_doc_cls, service):
        """update_knowledge can update several fields in one call."""
        doc = _make_doc(status="draft")
        mock_doc_cls.find_one.return_value.run.return_value = doc

        service.update_knowledge(
            "proj-1",
            VALID_OID,
            title="Updated title",
            severity="info",
            symptom="Updated symptom",
        )

        assert doc.title == "Updated title"
        assert doc.severity == "info"
        assert doc.symptom == "Updated symptom"

    @patch("qdash.api.services.issue_knowledge_service.IssueKnowledgeDocument")
    def test_skips_none_fields(self, mock_doc_cls, service):
        """update_knowledge does not overwrite fields that are None (unset)."""
        doc = _make_doc(status="draft", title="Original title")
        mock_doc_cls.find_one.return_value.run.return_value = doc

        service.update_knowledge("proj-1", VALID_OID, severity="critical")

        # title should remain unchanged because title=None was not passed
        assert doc.title == "Original title"

    @patch("qdash.api.services.issue_knowledge_service.IssueKnowledgeDocument")
    def test_calls_update_time_and_save(self, mock_doc_cls, service):
        """update_knowledge calls system_info.update_time() and doc.save()."""
        doc = _make_doc(status="draft")
        mock_doc_cls.find_one.return_value.run.return_value = doc

        service.update_knowledge("proj-1", VALID_OID, title="X")

        doc.system_info.update_time.assert_called_once()
        doc.save.assert_called_once()

    @patch("qdash.api.services.issue_knowledge_service.IssueKnowledgeDocument")
    def test_raises_404_when_not_found(self, mock_doc_cls, service):
        """update_knowledge raises HTTPException 404 when doc is missing."""
        mock_doc_cls.find_one.return_value.run.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            service.update_knowledge("proj-1", VALID_OID, title="X")

        assert exc_info.value.status_code == 404

    @patch("qdash.api.services.issue_knowledge_service.IssueKnowledgeDocument")
    def test_raises_400_when_not_draft(self, mock_doc_cls, service):
        """update_knowledge raises HTTPException 400 for non-draft docs."""
        doc = _make_doc(status="approved")
        mock_doc_cls.find_one.return_value.run.return_value = doc

        with pytest.raises(HTTPException) as exc_info:
            service.update_knowledge("proj-1", VALID_OID, title="X")

        assert exc_info.value.status_code == 400
        assert "draft" in exc_info.value.detail.lower()

    @patch("qdash.api.services.issue_knowledge_service.IssueKnowledgeDocument")
    def test_returns_response(self, mock_doc_cls, service):
        """update_knowledge returns IssueKnowledgeResponse."""
        doc = _make_doc(status="draft")
        mock_doc_cls.find_one.return_value.run.return_value = doc

        result = service.update_knowledge("proj-1", VALID_OID, title="X")

        assert isinstance(result, IssueKnowledgeResponse)


class TestApproveKnowledge:
    """Tests for IssueKnowledgeService.approve_knowledge."""

    @pytest.fixture
    def service(self):
        return IssueKnowledgeService()

    @patch.dict("os.environ", {}, clear=True)
    @patch("qdash.api.services.issue_knowledge_service.IssueKnowledgeDocument")
    def test_approves_draft(self, mock_doc_cls, service):
        """approve_knowledge sets status to approved and records reviewer."""
        doc = _make_doc(status="draft")
        mock_doc_cls.find_one.return_value.run.return_value = doc

        result = service.approve_knowledge("proj-1", VALID_OID, "reviewer-bob")

        assert doc.status == "approved"
        assert doc.reviewed_by == "reviewer-bob"
        doc.save.assert_called_once()
        assert isinstance(result, IssueKnowledgeResponse)

    @patch.dict("os.environ", {}, clear=True)
    @patch("qdash.api.services.issue_knowledge_service.IssueKnowledgeDocument")
    def test_calls_update_time(self, mock_doc_cls, service):
        """approve_knowledge updates the timestamp."""
        doc = _make_doc(status="draft")
        mock_doc_cls.find_one.return_value.run.return_value = doc

        service.approve_knowledge("proj-1", VALID_OID, "bob")

        doc.system_info.update_time.assert_called_once()

    @patch("qdash.api.services.issue_knowledge_service.IssueKnowledgeDocument")
    def test_raises_404_when_not_found(self, mock_doc_cls, service):
        """approve_knowledge raises HTTPException 404 when doc is missing."""
        mock_doc_cls.find_one.return_value.run.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            service.approve_knowledge("proj-1", VALID_OID, "bob")

        assert exc_info.value.status_code == 404

    @patch("qdash.api.services.issue_knowledge_service.IssueKnowledgeDocument")
    def test_raises_400_when_already_approved(self, mock_doc_cls, service):
        """approve_knowledge raises HTTPException 400 for non-draft docs."""
        doc = _make_doc(status="approved")
        mock_doc_cls.find_one.return_value.run.return_value = doc

        with pytest.raises(HTTPException) as exc_info:
            service.approve_knowledge("proj-1", VALID_OID, "bob")

        assert exc_info.value.status_code == 400
        assert "draft" in exc_info.value.detail.lower()

    @patch("qdash.api.services.issue_knowledge_service.IssueKnowledgeDocument")
    def test_raises_400_when_rejected(self, mock_doc_cls, service):
        """approve_knowledge raises HTTPException 400 for rejected docs."""
        doc = _make_doc(status="rejected")
        mock_doc_cls.find_one.return_value.run.return_value = doc

        with pytest.raises(HTTPException) as exc_info:
            service.approve_knowledge("proj-1", VALID_OID, "bob")

        assert exc_info.value.status_code == 400

    @patch.dict(
        "os.environ",
        {
            "KNOWLEDGE_REPO_URL": "https://github.com/org/knowledge-repo",
            "GITHUB_USER": "bot",
            "GITHUB_TOKEN": "ghp_fake",
        },
    )
    @patch("qdash.api.services.issue_knowledge_service.IssueKnowledgeService._create_knowledge_pr")
    @patch("qdash.datamodel.task_knowledge.get_task_category_dir")
    @patch("qdash.api.services.issue_knowledge_service.IssueKnowledgeDocument")
    def test_creates_pr_when_repo_configured(
        self, mock_doc_cls, mock_get_cat, mock_create_pr, service
    ):
        """approve_knowledge creates a PR when KNOWLEDGE_REPO_URL is set."""
        doc = _make_doc(status="draft", task_name="CheckT1")
        mock_doc_cls.find_one.return_value.run.return_value = doc
        mock_get_cat.return_value = "qubit"
        mock_create_pr.return_value = "https://github.com/org/repo/pull/42"

        service.approve_knowledge("proj-1", VALID_OID, "alice")

        mock_create_pr.assert_called_once()
        assert doc.pr_url == "https://github.com/org/repo/pull/42"


class TestRejectKnowledge:
    """Tests for IssueKnowledgeService.reject_knowledge."""

    @pytest.fixture
    def service(self):
        return IssueKnowledgeService()

    @patch("qdash.api.services.issue_knowledge_service.IssueKnowledgeDocument")
    def test_rejects_draft(self, mock_doc_cls, service):
        """reject_knowledge sets status to rejected and records reviewer."""
        doc = _make_doc(status="draft")
        mock_doc_cls.find_one.return_value.run.return_value = doc

        result = service.reject_knowledge("proj-1", VALID_OID, "reviewer-carol")

        assert doc.status == "rejected"
        assert doc.reviewed_by == "reviewer-carol"
        doc.save.assert_called_once()
        assert isinstance(result, IssueKnowledgeResponse)

    @patch("qdash.api.services.issue_knowledge_service.IssueKnowledgeDocument")
    def test_calls_update_time(self, mock_doc_cls, service):
        """reject_knowledge updates the timestamp."""
        doc = _make_doc(status="draft")
        mock_doc_cls.find_one.return_value.run.return_value = doc

        service.reject_knowledge("proj-1", VALID_OID, "carol")

        doc.system_info.update_time.assert_called_once()

    @patch("qdash.api.services.issue_knowledge_service.IssueKnowledgeDocument")
    def test_raises_404_when_not_found(self, mock_doc_cls, service):
        """reject_knowledge raises HTTPException 404 when doc is missing."""
        mock_doc_cls.find_one.return_value.run.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            service.reject_knowledge("proj-1", VALID_OID, "carol")

        assert exc_info.value.status_code == 404

    @patch("qdash.api.services.issue_knowledge_service.IssueKnowledgeDocument")
    def test_raises_400_when_already_approved(self, mock_doc_cls, service):
        """reject_knowledge raises HTTPException 400 for approved docs."""
        doc = _make_doc(status="approved")
        mock_doc_cls.find_one.return_value.run.return_value = doc

        with pytest.raises(HTTPException) as exc_info:
            service.reject_knowledge("proj-1", VALID_OID, "carol")

        assert exc_info.value.status_code == 400
        assert "draft" in exc_info.value.detail.lower()


class TestDeleteKnowledge:
    """Tests for IssueKnowledgeService.delete_knowledge."""

    @pytest.fixture
    def service(self):
        return IssueKnowledgeService()

    @patch("qdash.api.services.issue_knowledge_service.IssueKnowledgeDocument")
    def test_deletes_existing_doc(self, mock_doc_cls, service):
        """delete_knowledge calls doc.delete() and returns SuccessResponse."""
        doc = _make_doc()
        mock_doc_cls.find_one.return_value.run.return_value = doc

        result = service.delete_knowledge("proj-1", VALID_OID)

        doc.delete.assert_called_once()
        assert isinstance(result, SuccessResponse)
        assert "deleted" in result.message.lower()

    @patch("qdash.api.services.issue_knowledge_service.IssueKnowledgeDocument")
    def test_raises_404_when_not_found(self, mock_doc_cls, service):
        """delete_knowledge raises HTTPException 404 when doc is missing."""
        mock_doc_cls.find_one.return_value.run.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            service.delete_knowledge("proj-1", VALID_OID)

        assert exc_info.value.status_code == 404

    @patch("qdash.api.services.issue_knowledge_service.IssueKnowledgeDocument")
    def test_can_delete_any_status(self, mock_doc_cls, service):
        """delete_knowledge works regardless of document status."""
        for status in ("draft", "approved", "rejected"):
            doc = _make_doc(status=status)
            mock_doc_cls.find_one.return_value.run.return_value = doc

            result = service.delete_knowledge("proj-1", VALID_OID)

            doc.delete.assert_called_once()
            assert isinstance(result, SuccessResponse)


class TestSlugify:
    """Tests for IssueKnowledgeService._slugify."""

    def test_basic_title(self):
        """Converts a simple title to lowercase slug."""
        assert IssueKnowledgeService._slugify("Hello World") == "hello-world"

    def test_strips_special_characters(self):
        """Removes non-word characters except hyphens."""
        result = IssueKnowledgeService._slugify("T1 degradation (Q0) -- chip#A!")
        assert "(" not in result
        assert ")" not in result
        assert "#" not in result
        assert "!" not in result

    def test_collapses_multiple_hyphens(self):
        """Multiple hyphens are collapsed to one."""
        result = IssueKnowledgeService._slugify("foo---bar")
        assert "--" not in result
        assert result == "foo-bar"

    def test_collapses_multiple_spaces(self):
        """Multiple spaces become a single hyphen."""
        result = IssueKnowledgeService._slugify("foo   bar")
        assert result == "foo-bar"

    def test_truncates_to_80_chars(self):
        """Slug is truncated to at most 80 characters."""
        long_title = "a " * 100  # 200 chars
        result = IssueKnowledgeService._slugify(long_title)
        assert len(result) <= 80

    def test_strips_leading_and_trailing_hyphens(self):
        """Leading/trailing hyphens are removed."""
        result = IssueKnowledgeService._slugify("--hello--")
        assert not result.startswith("-")
        assert not result.endswith("-")

    def test_empty_string(self):
        """Empty input returns empty string."""
        assert IssueKnowledgeService._slugify("") == ""

    def test_underscores_replaced(self):
        """Underscores are treated as word separators."""
        result = IssueKnowledgeService._slugify("check_t1_value")
        assert result == "check-t1-value"


class TestDocToMarkdown:
    """Tests for IssueKnowledgeService._doc_to_markdown."""

    def test_contains_title_heading(self):
        """Markdown starts with the title as an h1 heading."""
        doc = _make_doc(title="My Knowledge Case")
        md = IssueKnowledgeService._doc_to_markdown(doc)
        assert md.startswith("# My Knowledge Case\n")

    def test_contains_metadata(self):
        """Markdown contains date, severity, chip_id, qid metadata."""
        doc = _make_doc(
            date="2025-06-15",
            severity="critical",
            chip_id="chip-X",
            qid="Q5",
            resolution_status="resolved",
            issue_id="iss-99",
        )
        md = IssueKnowledgeService._doc_to_markdown(doc)
        assert "- date: 2025-06-15" in md
        assert "- severity: critical" in md
        assert "- chip_id: chip-X" in md
        assert "- qid: Q5" in md
        assert "- status: resolved" in md
        assert "- issue_id: iss-99" in md

    def test_contains_symptom_section(self):
        """Markdown includes a Symptom section."""
        doc = _make_doc(symptom="The qubit frequency drifted")
        md = IssueKnowledgeService._doc_to_markdown(doc)
        assert "## Symptom" in md
        assert "The qubit frequency drifted" in md

    def test_contains_root_cause_section(self):
        """Markdown includes a Root cause section."""
        doc = _make_doc(root_cause="Thermal fluctuation")
        md = IssueKnowledgeService._doc_to_markdown(doc)
        assert "## Root cause" in md
        assert "Thermal fluctuation" in md

    def test_contains_resolution_section(self):
        """Markdown includes a Resolution section."""
        doc = _make_doc(resolution="Applied frequency correction")
        md = IssueKnowledgeService._doc_to_markdown(doc)
        assert "## Resolution" in md
        assert "Applied frequency correction" in md

    def test_contains_lesson_learned_section(self):
        """Markdown includes bulleted Lesson learned items."""
        doc = _make_doc(lesson_learned=["Lesson one", "Lesson two"])
        md = IssueKnowledgeService._doc_to_markdown(doc)
        assert "## Lesson learned" in md
        assert "- Lesson one" in md
        assert "- Lesson two" in md

    def test_figure_paths_rewritten(self):
        """Figure paths are rewritten to ./figures/<filename>."""
        doc = _make_doc(figure_paths=["/data/results/task-1/fig_t1.png"])
        md = IssueKnowledgeService._doc_to_markdown(doc)
        assert "## Figures" in md
        assert "![Figure 1](./figures/fig_t1.png)" in md

    def test_multiple_figures(self):
        """Multiple figures are numbered sequentially."""
        doc = _make_doc(figure_paths=["/data/fig1.png", "/data/fig2.png", "/data/fig3.png"])
        md = IssueKnowledgeService._doc_to_markdown(doc)
        assert "![Figure 1](./figures/fig1.png)" in md
        assert "![Figure 2](./figures/fig2.png)" in md
        assert "![Figure 3](./figures/fig3.png)" in md

    def test_thread_image_urls_external(self):
        """External thread image URLs are included as-is."""
        doc = _make_doc(
            thread_image_urls=["https://img.example.com/a.png", "https://img.example.com/b.png"]
        )
        md = IssueKnowledgeService._doc_to_markdown(doc)
        assert "## Thread images" in md
        assert "![Thread image 1](https://img.example.com/a.png)" in md
        assert "![Thread image 2](https://img.example.com/b.png)" in md

    def test_thread_image_urls_local_api(self):
        """Local API thread image URLs are rewritten to relative paths."""
        doc = _make_doc(
            thread_image_urls=[
                "/api/issues/images/81909b81-af30-40d8-85b3-379bb4d75909.png",
                "/api/issues/images/abcdef12-3456-7890-abcd-ef1234567890.jpg",
            ]
        )
        md = IssueKnowledgeService._doc_to_markdown(doc)
        assert "## Thread images" in md
        assert "![Thread image 1](./figures/81909b81-af30-40d8-85b3-379bb4d75909.png)" in md
        assert "![Thread image 2](./figures/abcdef12-3456-7890-abcd-ef1234567890.jpg)" in md

    def test_thread_image_urls_mixed(self):
        """Mixed local and external thread image URLs are handled correctly."""
        doc = _make_doc(
            thread_image_urls=[
                "/api/issues/images/abc123.png",
                "https://img.example.com/ext.png",
            ]
        )
        md = IssueKnowledgeService._doc_to_markdown(doc)
        assert "![Thread image 1](./figures/abc123.png)" in md
        assert "![Thread image 2](https://img.example.com/ext.png)" in md

    def test_omits_empty_sections(self):
        """Sections with empty content are omitted."""
        doc = _make_doc(
            symptom="",
            root_cause="",
            resolution="",
            lesson_learned=[],
            figure_paths=[],
            thread_image_urls=[],
        )
        md = IssueKnowledgeService._doc_to_markdown(doc)
        assert "## Symptom" not in md
        assert "## Root cause" not in md
        assert "## Resolution" not in md
        assert "## Lesson learned" not in md
        assert "## Figures" not in md
        assert "## Thread images" not in md


class TestCallLlmExtract:
    """Tests for IssueKnowledgeService._call_llm_extract."""

    @pytest.fixture
    def mock_config(self):
        """Build a mock copilot config."""
        config = MagicMock()
        config.enabled = True
        config.model.name = "gpt-4o"
        return config

    @pytest.mark.asyncio
    async def test_returns_empty_when_copilot_disabled(self):
        """Returns empty dict when copilot is disabled."""
        config = MagicMock()
        config.enabled = False

        with patch("qdash.api.lib.copilot_config.load_copilot_config", return_value=config):
            result = await IssueKnowledgeService._call_llm_extract(
                "CheckT1", "chip-A", "Q0", "Title", "Thread text"
            )

        assert result == {}

    @pytest.mark.asyncio
    async def test_parses_valid_json_response(self, mock_config):
        """Parses a clean JSON response from the LLM."""
        expected = {
            "title": "T1 drop",
            "severity": "warning",
            "symptom": "Low T1",
            "root_cause": "Unknown",
            "resolution": "Recalibrate",
            "lesson_learned": ["Check T1"],
        }

        mock_response = MagicMock()
        mock_response.choices[0].message.content = json.dumps(expected)
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with (
            patch("qdash.api.lib.copilot_config.load_copilot_config", return_value=mock_config),
            patch("qdash.api.lib.copilot_agent._build_client", return_value=mock_client),
        ):
            result = await IssueKnowledgeService._call_llm_extract(
                "CheckT1", "chip-A", "Q0", "T1 issue", "Thread"
            )

        assert result == expected

    @pytest.mark.asyncio
    async def test_strips_markdown_code_fences(self, mock_config):
        """Strips ```json ... ``` fences from LLM response."""
        payload = '{"title": "Fenced response", "severity": "info"}'
        raw_response = f"```json\n{payload}\n```"

        mock_response = MagicMock()
        mock_response.choices[0].message.content = raw_response
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with (
            patch("qdash.api.lib.copilot_config.load_copilot_config", return_value=mock_config),
            patch("qdash.api.lib.copilot_agent._build_client", return_value=mock_client),
        ):
            result = await IssueKnowledgeService._call_llm_extract(
                "CheckT1", "chip-A", "Q0", "Title", "Thread"
            )

        assert result["title"] == "Fenced response"
        assert result["severity"] == "info"

    @pytest.mark.asyncio
    async def test_returns_empty_on_invalid_json(self, mock_config):
        """Returns empty dict when LLM returns invalid JSON."""
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "This is not valid JSON at all"
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with (
            patch("qdash.api.lib.copilot_config.load_copilot_config", return_value=mock_config),
            patch("qdash.api.lib.copilot_agent._build_client", return_value=mock_client),
        ):
            result = await IssueKnowledgeService._call_llm_extract(
                "CheckT1", "chip-A", "Q0", "Title", "Thread"
            )

        assert result == {}

    @pytest.mark.asyncio
    async def test_returns_empty_on_api_error(self, mock_config):
        """Returns empty dict when the LLM API raises an exception."""
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=RuntimeError("API unreachable"))

        with (
            patch("qdash.api.lib.copilot_config.load_copilot_config", return_value=mock_config),
            patch("qdash.api.lib.copilot_agent._build_client", return_value=mock_client),
        ):
            result = await IssueKnowledgeService._call_llm_extract(
                "CheckT1", "chip-A", "Q0", "Title", "Thread"
            )

        assert result == {}

    @pytest.mark.asyncio
    async def test_returns_empty_on_empty_response(self, mock_config):
        """Returns empty dict when the LLM returns empty content."""
        mock_response = MagicMock()
        mock_response.choices[0].message.content = ""
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with (
            patch("qdash.api.lib.copilot_config.load_copilot_config", return_value=mock_config),
            patch("qdash.api.lib.copilot_agent._build_client", return_value=mock_client),
        ):
            result = await IssueKnowledgeService._call_llm_extract(
                "CheckT1", "chip-A", "Q0", "Title", "Thread"
            )

        assert result == {}

    @pytest.mark.asyncio
    async def test_strips_triple_backtick_only_fences(self, mock_config):
        """Strips ``` fences without json language tag."""
        payload = '{"title": "Plain fences"}'
        raw_response = f"```\n{payload}\n```"

        mock_response = MagicMock()
        mock_response.choices[0].message.content = raw_response
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with (
            patch("qdash.api.lib.copilot_config.load_copilot_config", return_value=mock_config),
            patch("qdash.api.lib.copilot_agent._build_client", return_value=mock_client),
        ):
            result = await IssueKnowledgeService._call_llm_extract(
                "CheckT1", "chip-A", "Q0", "Title", "Thread"
            )

        assert result["title"] == "Plain fences"

    @pytest.mark.asyncio
    async def test_returns_empty_on_none_content(self, mock_config):
        """Returns empty dict when the LLM message content is None."""
        mock_response = MagicMock()
        mock_response.choices[0].message.content = None
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with (
            patch("qdash.api.lib.copilot_config.load_copilot_config", return_value=mock_config),
            patch("qdash.api.lib.copilot_agent._build_client", return_value=mock_client),
        ):
            result = await IssueKnowledgeService._call_llm_extract(
                "CheckT1", "chip-A", "Q0", "Title", "Thread"
            )

        assert result == {}
