"""Issue service for QDash API."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any
from uuid import uuid4

from qdash.api.lib.json_utils import sanitize_for_json
from qdash.api.schemas.issue import IssueResponse, ListIssuesResponse
from qdash.api.schemas.success import SuccessResponse
from qdash.common.paths import CALIB_DATA_BASE
from qdash.datamodel.project import ProjectRole
from qdash.dbmodel.issue import IssueDocument
from starlette.exceptions import HTTPException

logger = logging.getLogger(__name__)

ISSUES_IMAGE_DIR = CALIB_DATA_BASE / "issues"
ALLOWED_CONTENT_TYPES = {
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
}
CONTENT_TYPE_TO_EXT: dict[str, str] = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
}
MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5 MB
FILENAME_PATTERN = re.compile(r"^[0-9a-f\-]{36}\.(png|jpg|gif|webp)$")


class IssueService:
    """Service for issue CRUD operations."""

    @staticmethod
    def _to_response(doc: IssueDocument, reply_count: int = 0) -> IssueResponse:
        """Convert an IssueDocument to an IssueResponse schema."""
        return IssueResponse(
            id=str(doc.id),
            task_id=doc.task_id,
            username=doc.username,
            title=doc.title,
            content=doc.content,
            created_at=doc.system_info.created_at,
            updated_at=doc.system_info.updated_at,
            parent_id=doc.parent_id,
            reply_count=reply_count,
            is_closed=doc.is_closed,
            is_ai_reply=doc.is_ai_reply,
        )

    def list_issues(
        self,
        project_id: str,
        skip: int = 0,
        limit: int = 50,
        task_id: str | None = None,
        is_closed: bool | None = False,
    ) -> ListIssuesResponse:
        """List all root issues with reply counts."""
        query: dict[str, object] = {
            "project_id": project_id,
            "parent_id": None,
        }
        if task_id:
            query["task_id"] = task_id
        if is_closed is not None:
            query["is_closed"] = is_closed

        total = IssueDocument.find(query).count()

        docs = (
            IssueDocument.find(query)
            .sort("-system_info.created_at")
            .skip(skip)
            .limit(limit)
            .to_list()
        )

        # Collect root issue IDs to get reply counts
        root_ids = [str(doc.id) for doc in docs]

        # Aggregate reply counts for these root issues
        reply_counts: dict[str, int] = {}
        if root_ids:
            pipeline = [
                {
                    "$match": {
                        "project_id": project_id,
                        "parent_id": {"$in": root_ids},
                    }
                },
                {"$group": {"_id": "$parent_id", "count": {"$sum": 1}}},
            ]
            results = IssueDocument.aggregate(pipeline).to_list()
            for item in results:
                reply_counts[item["_id"]] = item["count"]

        issues = [
            self._to_response(doc, reply_count=reply_counts.get(str(doc.id), 0)) for doc in docs
        ]

        return ListIssuesResponse(
            issues=issues,
            total=total,
            skip=skip,
            limit=limit,
        )

    def get_issue(self, project_id: str, issue_id: str) -> IssueResponse:
        """Get a single issue by ID."""
        from bson import ObjectId

        doc = IssueDocument.find_one(
            {
                "_id": ObjectId(issue_id),
                "project_id": project_id,
            },
        ).run()

        if doc is None:
            raise HTTPException(status_code=404, detail="Issue not found")

        # Count replies if this is a root issue
        reply_count = 0
        if doc.parent_id is None:
            reply_count = IssueDocument.find(
                {
                    "project_id": project_id,
                    "parent_id": issue_id,
                },
            ).count()

        return self._to_response(doc, reply_count=reply_count)

    def get_issue_replies(self, project_id: str, issue_id: str) -> list[IssueResponse]:
        """List replies for an issue."""
        docs = (
            IssueDocument.find(
                {
                    "project_id": project_id,
                    "parent_id": issue_id,
                },
            )
            .sort("system_info.created_at")
            .to_list()
        )

        return [self._to_response(doc) for doc in docs]

    def create_issue(
        self,
        project_id: str,
        task_id: str,
        username: str,
        title: str | None,
        content: str,
        parent_id: str | None,
    ) -> IssueResponse:
        """Create a new issue."""
        # Validate: root issues must have a title
        if parent_id is None and not title:
            raise HTTPException(status_code=422, detail="Title is required for root issues")

        doc = IssueDocument(
            project_id=project_id,
            task_id=task_id,
            username=username,
            title=title if parent_id is None else None,
            content=content,
            parent_id=parent_id,
        )
        doc.insert()

        return self._to_response(doc)

    def update_issue(
        self,
        project_id: str,
        issue_id: str,
        username: str,
        title: str | None,
        content: str,
    ) -> IssueResponse:
        """Update an issue."""
        from bson import ObjectId

        doc = IssueDocument.find_one(
            {
                "_id": ObjectId(issue_id),
                "project_id": project_id,
            },
        ).run()

        if doc is None:
            raise HTTPException(status_code=404, detail="Issue not found")

        if doc.username != username:
            raise HTTPException(status_code=403, detail="You can only edit your own issues")

        # Only update title for root issues
        if doc.parent_id is None and title is not None:
            doc.title = title

        doc.content = content
        doc.system_info.update_time()
        doc.save()

        return self._to_response(doc)

    def delete_issue(self, project_id: str, issue_id: str, username: str) -> SuccessResponse:
        """Delete an issue."""
        from bson import ObjectId

        doc = IssueDocument.find_one(
            {
                "_id": ObjectId(issue_id),
                "project_id": project_id,
            },
        ).run()

        if doc is None:
            raise HTTPException(status_code=404, detail="Issue not found")

        if doc.username != username:
            raise HTTPException(status_code=403, detail="You can only delete your own issues")

        doc.delete()

        return SuccessResponse(message="Issue deleted")

    def close_issue(
        self,
        project_id: str,
        issue_id: str,
        username: str,
        role: ProjectRole | None,
    ) -> SuccessResponse:
        """Close an issue."""
        from bson import ObjectId

        doc = IssueDocument.find_one(
            {
                "_id": ObjectId(issue_id),
                "project_id": project_id,
                "parent_id": None,
            },
        ).run()

        if doc is None:
            raise HTTPException(status_code=404, detail="Issue not found")

        if doc.username != username and role != ProjectRole.OWNER:
            raise HTTPException(
                status_code=403, detail="Only the author or project owner can close this issue"
            )

        doc.is_closed = True
        doc.save()

        return SuccessResponse(message="Issue closed")

    def reopen_issue(
        self,
        project_id: str,
        issue_id: str,
        username: str,
        role: ProjectRole | None,
    ) -> SuccessResponse:
        """Reopen an issue."""
        from bson import ObjectId

        doc = IssueDocument.find_one(
            {
                "_id": ObjectId(issue_id),
                "project_id": project_id,
                "parent_id": None,
            },
        ).run()

        if doc is None:
            raise HTTPException(status_code=404, detail="Issue not found")

        if doc.username != username and role != ProjectRole.OWNER:
            raise HTTPException(
                status_code=403, detail="Only the author or project owner can reopen this issue"
            )

        doc.is_closed = False
        doc.save()

        return SuccessResponse(message="Issue reopened")

    def get_task_result_issues(self, project_id: str, task_id: str) -> list[IssueResponse]:
        """Get all issues for a task result."""
        docs = (
            IssueDocument.find(
                {
                    "project_id": project_id,
                    "task_id": task_id,
                },
            )
            .sort("system_info.created_at")
            .to_list()
        )

        return [self._to_response(doc) for doc in docs]

    def build_ai_reply_context(self, project_id: str, issue_id: str) -> dict[str, Any]:
        """Build context for AI reply (root issue, thread, task result info).

        Returns
        -------
        dict[str, Any]
            Dictionary with keys:
            - root_doc: The root IssueDocument (or None if not found)
            - actual_root_id: The root issue ID string
            - conversation_history: List of role/content dicts
            - chip_id: Chip identifier (or None)
            - qid: Qubit identifier (or None)
            - qubit_params: Qubit parameters dict
            - task_id: The task ID from the root document

        """
        from bson import ObjectId

        root_doc = IssueDocument.find_one(
            {"_id": ObjectId(issue_id), "project_id": project_id}
        ).run()

        if root_doc is None:
            return {"root_doc": None}

        # Get the root issue's parent_id to determine if this IS the root
        actual_root_id = issue_id if root_doc.parent_id is None else root_doc.parent_id

        reply_docs = (
            IssueDocument.find({"project_id": project_id, "parent_id": actual_root_id})
            .sort("system_info.created_at")
            .to_list()
        )

        conversation_history: list[dict[str, str]] = []
        # Add root issue content
        if root_doc.parent_id is None:
            conversation_history.append({"role": "user", "content": root_doc.content})
        # Add replies
        for reply_doc in reply_docs:
            role = "assistant" if reply_doc.is_ai_reply else "user"
            conversation_history.append({"role": role, "content": reply_doc.content})

        # Strip @qdash mentions from conversation history
        for entry in conversation_history:
            if entry["role"] == "user":
                entry["content"] = re.sub(r"@qdash\b\s*", "", entry["content"]).strip()

        # Resolve chip_id / qid from task result
        chip_id: str | None = None
        qid: str | None = None
        task_id = root_doc.task_id

        from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

        task_doc = TaskResultHistoryDocument.find_one({"task_id": task_id}).run()
        if task_doc:
            chip_id = task_doc.chip_id
            qid = task_doc.qid

        # Resolve default chip_id if not available from task result
        if not chip_id:
            from qdash.dbmodel.chip import ChipDocument

            chip_doc = ChipDocument.find_one({}, sort=[("installed_at", -1)]).run()
            if chip_doc:
                chip_id = str(chip_doc.chip_id)

        # Optionally load qubit params
        qubit_params: dict[str, Any] = {}
        if chip_id and qid:
            from qdash.dbmodel.qubit import QubitDocument

            qubit_doc = QubitDocument.find_one({"chip_id": chip_id, "qid": qid}).run()
            if qubit_doc:
                qubit_params = sanitize_for_json(dict(qubit_doc.data))

        return {
            "root_doc": root_doc,
            "actual_root_id": actual_root_id,
            "conversation_history": conversation_history,
            "chip_id": chip_id,
            "qid": qid,
            "qubit_params": qubit_params,
            "task_id": task_id,
        }

    def save_ai_reply(
        self,
        project_id: str,
        task_id: str,
        parent_id: str,
        content: str,
    ) -> IssueResponse:
        """Save an AI-generated reply."""
        ai_doc = IssueDocument(
            project_id=project_id,
            task_id=task_id,
            username="qdash-ai",
            title=None,
            content=content,
            parent_id=parent_id,
            is_ai_reply=True,
        )
        ai_doc.insert()

        return self._to_response(ai_doc)

    @staticmethod
    def upload_image(data: bytes, content_type: str) -> str:
        """Validate and save an uploaded image.

        Parameters
        ----------
        data : bytes
            Raw image bytes.
        content_type : str
            MIME type of the uploaded file.

        Returns
        -------
        str
            The URL path for the saved image.

        Raises
        ------
        HTTPException
            If the content type is not allowed or size exceeds the limit.

        """
        if content_type not in ALLOWED_CONTENT_TYPES:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Unsupported image type: {content_type}. " "Allowed: png, jpeg, gif, webp"
                ),
            )

        if len(data) > MAX_IMAGE_SIZE:
            raise HTTPException(
                status_code=400,
                detail="Image exceeds 5MB size limit",
            )

        ext = CONTENT_TYPE_TO_EXT[content_type]
        filename = f"{uuid4()}{ext}"
        dest = ISSUES_IMAGE_DIR / filename

        ISSUES_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)

        return f"/api/issues/images/{filename}"

    @staticmethod
    def get_image_path(filename: str) -> tuple[Path, str]:
        """Resolve and validate an image filename.

        Parameters
        ----------
        filename : str
            The image filename to look up.

        Returns
        -------
        tuple[Path, str]
            (filepath, media_type)

        Raises
        ------
        HTTPException
            If the filename is invalid or the file doesn't exist.

        """
        if not FILENAME_PATTERN.match(filename):
            raise HTTPException(status_code=400, detail="Invalid filename")

        filepath = ISSUES_IMAGE_DIR / filename
        if not filepath.is_file():
            raise HTTPException(status_code=404, detail="Image not found")

        ext = Path(filename).suffix.lstrip(".")
        media_types = {
            "png": "image/png",
            "jpg": "image/jpeg",
            "gif": "image/gif",
            "webp": "image/webp",
        }
        media_type = media_types.get(ext, "application/octet-stream")

        return filepath, media_type
