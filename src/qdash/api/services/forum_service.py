"""Forum service for QDash API."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from bson import ObjectId
from bunnet import SortDirection
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError
from starlette.exceptions import HTTPException

from qdash.api.schemas.forum import (
    ForumCategoryResponse,
    ForumPostResponse,
    ForumThreadStatus,
    ListForumCategoriesResponse,
    ListForumPostsResponse,
)
from qdash.api.schemas.success import SuccessResponse
from qdash.common.config.paths import CALIB_DATA_BASE
from qdash.common.utils.datetime import now
from qdash.datamodel.project import ProjectRole
from qdash.dbmodel.forum import (
    FORUM_THREAD_STATUSES,
    ForumCategoryDocument,
    ForumCounterDocument,
    ForumPostDocument,
)
from qdash.dbmodel.project_membership import ProjectMembershipDocument
from qdash.dbmodel.user import UserDocument

if TYPE_CHECKING:
    from fastapi import BackgroundTasks

    from qdash.api.services.notification_service import NotificationService
    from qdash.api.services.slack_notification_service import SlackNotificationService

DEFAULT_FORUM_CATEGORIES = [
    {
        "key": "qubit",
        "name": "Qubit Health",
        "description": "T1, T2, readout fidelity",
        "color": "success",
        "icon": "activity",
        "sort_order": 10,
    },
    {
        "key": "coupling",
        "name": "Coupling & CR",
        "description": "Cross-resonance and pair behavior",
        "color": "info",
        "icon": "network",
        "sort_order": 20,
    },
    {
        "key": "control",
        "name": "Control Stack",
        "description": "Control devices, wiring, IMPA",
        "color": "warning",
        "icon": "circuit-board",
        "sort_order": 30,
    },
    {
        "key": "system",
        "name": "System & Policy",
        "description": "Fridge, chip, software, calibration rules",
        "color": "primary",
        "icon": "settings",
        "sort_order": 40,
    },
    {
        "key": "other",
        "name": "Other",
        "description": "General project discussions",
        "color": "secondary",
        "icon": "message-square",
        "sort_order": 50,
    },
]

CATEGORY_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
ALLOWED_FORUM_LABELS = {"review", "anomaly"}
LEGACY_FORUM_LABEL_ALIASES = {"discussion": "review", "info": "review", "mtg": "review"}
FORUM_IMAGE_DIR = CALIB_DATA_BASE / "forum"


def _normalize_forum_target(
    *,
    chip_id: str | None,
    target_type: str | None,
    target_id: str | None,
) -> tuple[str | None, str | None, str | None]:
    chip = chip_id.strip() if isinstance(chip_id, str) and chip_id.strip() else None
    kind = (
        target_type.strip().lower()
        if isinstance(target_type, str) and target_type.strip()
        else None
    )
    target = target_id.strip() if isinstance(target_id, str) and target_id.strip() else None
    if kind not in {"qubit", "coupling", None}:
        kind = None
    if not (chip and kind and target):
        return None, None, None
    return chip[:128], kind, target[:128]


def _normalize_forum_cooldown(cooldown_id: str | None) -> str | None:
    value = cooldown_id.strip() if isinstance(cooldown_id, str) and cooldown_id.strip() else None
    return value[:128] if value else None


def _normalize_forum_assignee(assignee_username: str | None) -> str | None:
    value = (
        assignee_username.strip()
        if isinstance(assignee_username, str) and assignee_username.strip()
        else None
    )
    return value[:64] if value else None


def _normalize_forum_labels(labels: list[str] | None) -> list[str]:
    """Normalize user-provided labels and keep at most one semantic label per thread."""
    for label in labels or []:
        value = re.sub(r"[^a-z0-9_-]+", "-", label.strip().lower()).strip("-_")[:32]
        if not value:
            continue
        if value == "resolved":
            raise HTTPException(
                status_code=422, detail="Use thread status instead of resolved label"
            )
        value = LEGACY_FORUM_LABEL_ALIASES.get(value, value)
        if value not in ALLOWED_FORUM_LABELS:
            raise HTTPException(status_code=422, detail="Unknown forum label")
        return [value]
    return []


def _normalize_forum_status(
    status: str | None, *, default: ForumThreadStatus = "open"
) -> ForumThreadStatus:
    value = status.strip().lower() if isinstance(status, str) and status.strip() else default
    if value not in FORUM_THREAD_STATUSES:
        raise HTTPException(status_code=422, detail="Unknown forum status")
    return value  # type: ignore[return-value]


def _forum_thread_accepts_replies(status: str | None) -> bool:
    return (status or "open") != "resolved"


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
MAX_IMAGE_SIZE = 5 * 1024 * 1024
FILENAME_PATTERN = re.compile(r"^[0-9a-f\-]{36}\.(png|jpg|gif|webp)$")
logger = logging.getLogger(__name__)


class ForumService:
    """Service for project forum CRUD operations."""

    def __init__(
        self,
        notification_service: NotificationService | None = None,
        slack_notification_service: SlackNotificationService | None = None,
    ) -> None:
        """Initialize the service with an optional notification dependency."""
        self._notifications = notification_service
        self._slack_notifications = slack_notification_service

    @staticmethod
    def _user_id_for_username(username: str) -> str | None:
        """Return the user ID for *username*, or None when the user is unknown."""
        user = UserDocument.find_one({"username": username}).run()
        return user.user_id if user else None

    @staticmethod
    def _is_author(doc: ForumPostDocument, *, user_id: str | None) -> bool:
        """Return whether *user_id* is the author of *doc*."""
        return bool(user_id and doc.user_id == user_id)

    @staticmethod
    def _ensure_project_assignee(project_id: str, assignee_username: str | None) -> str | None:
        """Return a normalized assignee username or raise when it is not assignable."""
        assignee = _normalize_forum_assignee(assignee_username)
        if assignee is None:
            return None
        membership = ProjectMembershipDocument.find_one(
            {"project_id": project_id, "username": assignee, "status": "active"}
        ).run()
        if membership is None:
            raise HTTPException(status_code=422, detail="Assignee must be an active project member")
        return assignee

    @staticmethod
    def _thread_number_seed(project_id: str) -> int:
        """Return a safe current counter value for an existing project."""
        root_filter = {"project_id": project_id, "parent_id": None}
        root_count = ForumPostDocument.get_motor_collection().count_documents(root_filter)
        max_docs = list(
            ForumPostDocument.get_motor_collection().aggregate(
                [
                    {"$match": {**root_filter, "number": {"$type": "int"}}},
                    {"$group": {"_id": None, "max_number": {"$max": "$number"}}},
                ]
            )
        )
        max_number = int(max_docs[0].get("max_number") or 0) if max_docs else 0
        return max(max_number, root_count)

    @classmethod
    def _next_thread_number(cls, project_id: str) -> int:
        """Allocate the next project-scoped forum thread number atomically."""
        import time

        for attempt in range(5):
            counter = ForumCounterDocument.find_one({"project_id": project_id}).run()
            if counter is None:
                try:
                    ForumCounterDocument(
                        project_id=project_id,
                        value=cls._thread_number_seed(project_id),
                    ).insert()
                except DuplicateKeyError:
                    time.sleep(0.01 * (attempt + 1))
                    continue

            result = ForumCounterDocument.get_motor_collection().find_one_and_update(
                {"project_id": project_id},
                {"$inc": {"value": 1}},
                return_document=ReturnDocument.AFTER,
            )
            if result is not None:
                return int(result["value"])
            time.sleep(0.01 * (attempt + 1))

        raise RuntimeError("Failed to allocate forum thread number")

    @classmethod
    def _ensure_root_thread_number(cls, doc: ForumPostDocument) -> int:
        """Ensure a root thread has a project-scoped display number."""
        if doc.number is not None:
            return doc.number

        new_number = cls._next_thread_number(doc.project_id)
        result = ForumPostDocument.get_motor_collection().find_one_and_update(
            {
                "_id": doc.id,
                "project_id": doc.project_id,
                "parent_id": None,
                "$or": [{"number": {"$exists": False}}, {"number": None}],
            },
            {"$set": {"number": new_number, "system_info.updated_at": now()}},
            return_document=ReturnDocument.AFTER,
        )
        if result is not None:
            doc.number = int(result["number"])
            return doc.number

        existing = ForumPostDocument.find_one(
            {"_id": doc.id, "project_id": doc.project_id, "parent_id": None}
        ).run()
        if existing is not None and existing.number is not None:
            doc.number = existing.number
            return existing.number
        raise RuntimeError("Failed to persist forum thread number")

    @staticmethod
    def _category_to_response(doc: ForumCategoryDocument) -> ForumCategoryResponse:
        """Convert a category document to an API response."""
        return ForumCategoryResponse(
            id=str(doc.id),
            project_id=doc.project_id,
            key=doc.key,
            name=doc.name,
            description=doc.description,
            color=doc.color,
            icon=doc.icon,
            sort_order=doc.sort_order,
            is_archived=doc.is_archived,
        )

    @staticmethod
    def _to_response(doc: ForumPostDocument, reply_count: int = 0) -> ForumPostResponse:
        """Convert a document to an API response."""
        user = UserDocument.find_one({"user_id": doc.user_id}).run() if doc.user_id else None
        return ForumPostResponse(
            id=str(doc.id),
            project_id=doc.project_id,
            number=getattr(doc, "number", None),
            category=doc.category,
            user_id=doc.user_id,
            username=doc.username,
            avatar_key=user.avatar_key if user else None,
            title=doc.title,
            content=doc.content,
            content_blocks=list(doc.content_blocks),
            parent_id=doc.parent_id,
            labels=list(getattr(doc, "labels", [])),
            assignee_username=getattr(doc, "assignee_username", None),
            chip_id=getattr(doc, "chip_id", None),
            target_type=getattr(doc, "target_type", None),
            target_id=getattr(doc, "target_id", None),
            cooldown_id=getattr(doc, "cooldown_id", None),
            reply_count=reply_count,
            status=_normalize_forum_status(getattr(doc, "status", None)),
            is_deleted=doc.is_deleted,
            is_ai_reply=doc.is_ai_reply,
            created_at=doc.system_info.created_at,
            updated_at=doc.system_info.updated_at,
        )

    @staticmethod
    def strip_mention(text: str) -> str:
        """Remove ``@qdash`` mention from text."""
        return re.sub(r"@qdash\b\s*", "", text).strip()

    @staticmethod
    def deduplicate_last_message(
        history: list[dict[str, str]],
        user_message: str,
    ) -> list[dict[str, str]]:
        """Remove the last history entry if it duplicates *user_message*."""
        if history and history[-1]["role"] == "user" and history[-1]["content"] == user_message:
            return history[:-1]
        return history

    @staticmethod
    def format_ai_response_as_markdown(result: dict[str, Any]) -> str | None:
        """Convert an AI response dict to Markdown."""
        from qdash.api.services.issue_service import IssueService

        return IssueService.format_ai_response_as_markdown(result)

    @staticmethod
    def _make_category_key(name: str) -> str:
        """Create a stable category key from a display name."""
        key = re.sub(r"[^a-z0-9_-]+", "-", name.strip().lower())
        key = re.sub(r"-+", "-", key).strip("-_")
        if not key:
            raise HTTPException(status_code=422, detail="Category key is required")
        return key[:64]

    def _ensure_default_categories(self, project_id: str) -> None:
        """Create the default categories for a project when none exist."""
        if ForumCategoryDocument.find({"project_id": project_id}).count() > 0:
            return

        for item in DEFAULT_FORUM_CATEGORIES:
            try:
                if ForumCategoryDocument.find_one(
                    {"project_id": project_id, "key": item["key"]}
                ).run():
                    continue
                ForumCategoryDocument(project_id=project_id, **item).insert()
            except DuplicateKeyError:
                continue

    def _ensure_active_category(self, project_id: str, category: str) -> None:
        """Raise HTTP 422 unless *category* exists and is active for the project."""
        self._ensure_default_categories(project_id)
        doc = ForumCategoryDocument.find_one(
            {"project_id": project_id, "key": category, "is_archived": False}
        ).run()
        if doc is None:
            raise HTTPException(status_code=422, detail="Forum category is not active")

    def list_categories(
        self, *, project_id: str, include_archived: bool = False
    ) -> ListForumCategoriesResponse:
        """List forum categories for a project."""
        self._ensure_default_categories(project_id)
        query: dict[str, object] = {"project_id": project_id}
        if not include_archived:
            query["is_archived"] = False

        docs = (
            ForumCategoryDocument.find(query)
            .sort(
                [
                    ("sort_order", SortDirection.ASCENDING),
                    ("system_info.created_at", SortDirection.ASCENDING),
                ]
            )
            .to_list()
        )
        return ListForumCategoriesResponse(
            categories=[self._category_to_response(doc) for doc in docs]
        )

    def create_category(
        self,
        *,
        project_id: str,
        key: str | None,
        name: str,
        description: str,
        color: str,
        icon: str,
        sort_order: int | None,
    ) -> ForumCategoryResponse:
        """Create a forum category."""
        self._ensure_default_categories(project_id)
        category_key = key or self._make_category_key(name)
        if not CATEGORY_KEY_RE.match(category_key):
            raise HTTPException(status_code=422, detail="Invalid category key")

        if sort_order is None:
            max_docs = (
                ForumCategoryDocument.find({"project_id": project_id})
                .sort("-sort_order")
                .limit(1)
                .to_list()
            )
            max_doc = max_docs[0] if max_docs else None
            sort_order = (max_doc.sort_order + 10) if max_doc else 10

        doc = ForumCategoryDocument(
            project_id=project_id,
            key=category_key,
            name=name,
            description=description,
            color=color,
            icon=icon,
            sort_order=sort_order,
        )
        try:
            doc.insert()
        except DuplicateKeyError as e:
            raise HTTPException(status_code=409, detail="Forum category already exists") from e
        return self._category_to_response(doc)

    def update_category(
        self,
        *,
        project_id: str,
        key: str,
        name: str | None,
        description: str | None,
        color: str | None,
        icon: str | None,
        sort_order: int | None,
        is_archived: bool | None,
    ) -> ForumCategoryResponse:
        """Update a forum category."""
        self._ensure_default_categories(project_id)
        doc = ForumCategoryDocument.find_one({"project_id": project_id, "key": key}).run()
        if doc is None:
            raise HTTPException(status_code=404, detail="Forum category not found")

        if name is not None:
            doc.name = name
        if description is not None:
            doc.description = description
        if color is not None:
            doc.color = color
        if icon is not None:
            doc.icon = icon
        if sort_order is not None:
            doc.sort_order = sort_order
        if is_archived is not None:
            doc.is_archived = is_archived
        doc.system_info.update_time()
        doc.save()
        return self._category_to_response(doc)

    def delete_category(self, *, project_id: str, key: str) -> SuccessResponse:
        """Archive a forum category without breaking existing posts."""
        self._ensure_default_categories(project_id)
        doc = ForumCategoryDocument.find_one({"project_id": project_id, "key": key}).run()
        if doc is None:
            raise HTTPException(status_code=404, detail="Forum category not found")
        if not doc.is_archived:
            active_count = ForumCategoryDocument.find(
                {"project_id": project_id, "is_archived": False}
            ).count()
            if active_count <= 1:
                raise HTTPException(
                    status_code=409, detail="Cannot archive the last active forum category"
                )
        doc.is_archived = True
        doc.system_info.update_time()
        doc.save()
        return SuccessResponse(message="Forum category archived")

    def list_posts(
        self,
        *,
        project_id: str,
        skip: int = 0,
        limit: int = 50,
        category: str | None = None,
        label: str | None = None,
        chip_id: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        cooldown_id: str | None = None,
        number: int | None = None,
        status: str | None = "open",
        q: str | None = None,
    ) -> ListForumPostsResponse:
        """List root forum threads with reply counts."""
        query: dict[str, object] = {
            "project_id": project_id,
            "parent_id": None,
            "is_deleted": False,
        }
        if category:
            query["category"] = category
        if label:
            normalized_label = _normalize_forum_labels([label])
            query["labels"] = normalized_label[0] if normalized_label else label
        if chip_id:
            query["chip_id"] = chip_id
        if target_type:
            query["target_type"] = target_type
        if target_id:
            query["target_id"] = target_id
        if cooldown_id:
            query["cooldown_id"] = cooldown_id
        if number is not None:
            query["number"] = number
        if status is not None:
            normalized_status = status.strip().lower() if isinstance(status, str) else ""
            query["status"] = _normalize_forum_status(normalized_status)
        if q and q.strip():
            term = q.strip()[:128]
            regex = {"$regex": re.escape(term.lstrip("#")), "$options": "i"}
            search_clauses: list[dict[str, object]] = [
                {"title": regex},
                {"content": regex},
                {"chip_id": regex},
                {"target_id": regex},
                {"cooldown_id": regex},
                {"assignee_username": regex},
                {"status": regex},
                {"category": regex},
                {"labels": regex},
            ]
            number_text = term[1:] if term.startswith("#") else term
            if number_text.isdigit():
                search_clauses.append({"number": int(number_text)})
            query["$or"] = search_clauses

        total = ForumPostDocument.find(query).count()
        docs = (
            ForumPostDocument.find(query)
            .sort("-system_info.created_at")
            .skip(skip)
            .limit(limit)
            .to_list()
        )

        root_ids = [str(doc.id) for doc in docs]
        reply_counts: dict[str, int] = {}
        if root_ids:
            pipeline = [
                {
                    "$match": {
                        "project_id": project_id,
                        "parent_id": {"$in": root_ids},
                        "is_deleted": False,
                    }
                },
                {"$group": {"_id": "$parent_id", "count": {"$sum": 1}}},
            ]
            results = ForumPostDocument.aggregate(pipeline).to_list()
            for item in results:
                reply_counts[item["_id"]] = item["count"]

        return ListForumPostsResponse(
            posts=[
                self._to_response(doc, reply_count=reply_counts.get(str(doc.id), 0)) for doc in docs
            ],
            total=total,
            skip=skip,
            limit=limit,
        )

    def get_post(self, *, project_id: str, post_id: str) -> ForumPostResponse:
        """Get a forum post by ID."""
        doc = ForumPostDocument.find_one(
            {"_id": ObjectId(post_id), "project_id": project_id, "is_deleted": False}
        ).run()
        if doc is None:
            raise HTTPException(status_code=404, detail="Forum post not found")

        reply_count = 0
        if doc.parent_id is None:
            reply_count = ForumPostDocument.find(
                {"project_id": project_id, "parent_id": post_id, "is_deleted": False}
            ).count()

        return self._to_response(doc, reply_count=reply_count)

    def get_replies(
        self, *, project_id: str, post_id: str, skip: int = 0, limit: int = 100
    ) -> list[ForumPostResponse]:
        """List replies for a forum thread."""
        root_doc = ForumPostDocument.find_one(
            {
                "_id": ObjectId(post_id),
                "project_id": project_id,
                "parent_id": None,
                "is_deleted": False,
            }
        ).run()
        if root_doc is None:
            return []

        docs = (
            ForumPostDocument.find(
                {"project_id": project_id, "parent_id": post_id, "is_deleted": False}
            )
            .sort("system_info.created_at")
            .skip(skip)
            .limit(limit)
            .to_list()
        )
        return [self._to_response(doc) for doc in docs]

    def create_post(
        self,
        *,
        project_id: str,
        username: str,
        category: str,
        title: str | None,
        content: str,
        parent_id: str | None,
        content_blocks: list[dict[str, Any]] | None = None,
        labels: list[str] | None = None,
        chip_id: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        cooldown_id: str | None = None,
        assignee_username: str | None = None,
        status: str | None = "open",
        background_tasks: BackgroundTasks | None = None,
    ) -> ForumPostResponse:
        """Create a new forum thread or reply."""
        if parent_id is None and not title:
            raise HTTPException(status_code=422, detail="Title is required for forum threads")

        root_doc: ForumPostDocument | None = None
        if parent_id is not None:
            root_doc = ForumPostDocument.find_one(
                {"_id": ObjectId(parent_id), "project_id": project_id, "is_deleted": False}
            ).run()
            if root_doc is None:
                raise HTTPException(status_code=404, detail="Parent forum thread not found")
            if root_doc.parent_id is not None:
                raise HTTPException(status_code=422, detail="Replies must target a root thread")
            if not _forum_thread_accepts_replies(getattr(root_doc, "status", None)):
                raise HTTPException(status_code=409, detail="Forum thread is closed")
            category = root_doc.category
        else:
            self._ensure_active_category(project_id, category)

        normalized_chip_id, normalized_target_type, normalized_target_id = (
            (root_doc.chip_id, root_doc.target_type, root_doc.target_id)
            if root_doc
            else _normalize_forum_target(
                chip_id=chip_id,
                target_type=target_type,
                target_id=target_id,
            )
        )
        thread_number = (
            self._ensure_root_thread_number(root_doc)
            if root_doc
            else self._next_thread_number(project_id)
        )
        doc = ForumPostDocument(
            project_id=project_id,
            number=thread_number,
            category=category,
            user_id=self._user_id_for_username(username),
            username=username,
            title=title if parent_id is None else None,
            content=content,
            content_blocks=content_blocks or [],
            labels=list(root_doc.labels) if root_doc else _normalize_forum_labels(labels),
            status=_normalize_forum_status(root_doc.status if root_doc else status),
            chip_id=normalized_chip_id,
            target_type=normalized_target_type,
            target_id=normalized_target_id,
            cooldown_id=root_doc.cooldown_id
            if root_doc
            else _normalize_forum_cooldown(cooldown_id),
            assignee_username=root_doc.assignee_username
            if root_doc
            else self._ensure_project_assignee(project_id, assignee_username),
            parent_id=parent_id,
        )
        doc.insert()

        if self._notifications:
            root_post = root_doc or doc
            parent_author = root_doc.username if root_doc else None
            try:
                self._notifications.notify_forum_event(
                    project_id=project_id,
                    post_id=str(doc.id),
                    root_post_id=str(root_post.id),
                    actor_username=username,
                    content=content,
                    title=root_post.title or "Forum thread",
                    parent_author=parent_author,
                )
            except Exception:
                logger.exception("Failed to create forum notifications for post %s", doc.id)

        if self._slack_notifications and parent_id is None:
            if background_tasks is not None:
                background_tasks.add_task(
                    self._slack_notifications.notify_forum_post,
                    post=doc,
                    actor_username=username,
                )
            else:
                self._slack_notifications.notify_forum_post(
                    post=doc,
                    actor_username=username,
                )

        return self._to_response(doc)

    def build_ai_reply_context(self, *, project_id: str, post_id: str) -> dict[str, Any]:
        """Build conversation context for a forum AI reply."""
        root_doc = ForumPostDocument.find_one(
            {"_id": ObjectId(post_id), "project_id": project_id, "is_deleted": False}
        ).run()

        if root_doc is None:
            return {"root_doc": None}

        actual_root_id = post_id if root_doc.parent_id is None else root_doc.parent_id
        if root_doc.parent_id is not None:
            root_doc = ForumPostDocument.find_one(
                {
                    "_id": ObjectId(actual_root_id),
                    "project_id": project_id,
                    "is_deleted": False,
                }
            ).run()
            if root_doc is None:
                return {"root_doc": None}

        reply_docs = (
            ForumPostDocument.find(
                {"project_id": project_id, "parent_id": actual_root_id, "is_deleted": False}
            )
            .sort("system_info.created_at")
            .to_list()
        )

        category = ForumCategoryDocument.find_one(
            {"project_id": project_id, "key": root_doc.category}
        ).run()
        category_name = category.name if category else root_doc.category
        title = root_doc.title or "Forum thread"

        conversation_history: list[dict[str, str]] = [
            {
                "role": "user",
                "content": (
                    f"Forum category: {category_name}\n"
                    f"Thread title: {title}\n\n"
                    f"{self.strip_mention(root_doc.content)}"
                ),
            }
        ]

        for reply_doc in reply_docs:
            role = "assistant" if reply_doc.is_ai_reply else "user"
            content = reply_doc.content
            if role == "user":
                content = self.strip_mention(content)
            conversation_history.append({"role": role, "content": content})

        return {
            "root_doc": root_doc,
            "actual_root_id": actual_root_id,
            "conversation_history": conversation_history,
            "title": title,
            "category_name": category_name,
        }

    def save_ai_reply(
        self,
        *,
        project_id: str,
        parent_id: str,
        content: str,
    ) -> ForumPostResponse:
        """Save an AI-generated forum reply."""
        root_doc = ForumPostDocument.find_one(
            {"_id": ObjectId(parent_id), "project_id": project_id, "is_deleted": False}
        ).run()
        if root_doc is None:
            raise HTTPException(status_code=404, detail="Forum post not found")

        ai_doc = ForumPostDocument(
            project_id=project_id,
            number=self._ensure_root_thread_number(root_doc),
            category=root_doc.category,
            username="qdash",
            title=None,
            content=content,
            labels=list(root_doc.labels),
            assignee_username=root_doc.assignee_username,
            status=root_doc.status,
            chip_id=root_doc.chip_id,
            target_type=root_doc.target_type,
            target_id=root_doc.target_id,
            cooldown_id=root_doc.cooldown_id,
            parent_id=parent_id,
            is_ai_reply=True,
        )
        ai_doc.insert()
        return self._to_response(ai_doc)

    @staticmethod
    def upload_image(data: bytes, content_type: str) -> str:
        """Validate and save an uploaded forum image."""
        if content_type not in ALLOWED_CONTENT_TYPES:
            raise HTTPException(
                status_code=400,
                detail=(f"Unsupported image type: {content_type}. Allowed: png, jpeg, gif, webp"),
            )

        if len(data) > MAX_IMAGE_SIZE:
            raise HTTPException(status_code=400, detail="Image exceeds 5MB size limit")

        ext = CONTENT_TYPE_TO_EXT[content_type]
        filename = f"{uuid4()}{ext}"
        dest = FORUM_IMAGE_DIR / filename

        FORUM_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)

        return f"/api/forum/images/{filename}"

    @staticmethod
    def get_image_path(filename: str) -> tuple[Path, str]:
        """Resolve and validate a forum image filename."""
        if not FILENAME_PATTERN.match(filename):
            raise HTTPException(status_code=400, detail="Invalid filename")

        filepath = FORUM_IMAGE_DIR / filename
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

    def update_post(
        self,
        *,
        project_id: str,
        post_id: str,
        username: str,
        category: str | None,
        title: str | None,
        content: str,
        content_blocks: list[dict[str, Any]] | None = None,
        labels: list[str] | None = None,
        chip_id: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        cooldown_id: str | None = None,
        assignee_username: str | None = None,
        status: str | None = None,
        update_cooldown_context: bool = False,
        update_target_context: bool = False,
        update_assignee_context: bool = False,
        update_status_context: bool = False,
        role: ProjectRole | None = None,
    ) -> ForumPostResponse:
        """Update a forum post."""
        doc = ForumPostDocument.find_one(
            {"_id": ObjectId(post_id), "project_id": project_id, "is_deleted": False}
        ).run()
        if doc is None:
            raise HTTPException(status_code=404, detail="Forum post not found")
        user_id = self._user_id_for_username(username)
        if not self._is_author(doc, user_id=user_id) and role != ProjectRole.OWNER:
            raise HTTPException(
                status_code=403, detail="Only the author or project owner can edit this post"
            )

        if doc.parent_id is None:
            if title is not None:
                doc.title = title
            if category is not None and category != doc.category:
                self._ensure_active_category(project_id, category)
                doc.category = category
            if labels is not None:
                doc.labels = _normalize_forum_labels(labels)
            if update_target_context:
                normalized_chip_id, normalized_target_type, normalized_target_id = (
                    _normalize_forum_target(
                        chip_id=chip_id if chip_id is not None else doc.chip_id,
                        target_type=target_type if target_type is not None else doc.target_type,
                        target_id=target_id if target_id is not None else doc.target_id,
                    )
                )
                doc.chip_id = normalized_chip_id
                doc.target_type = normalized_target_type
                doc.target_id = normalized_target_id
            if update_cooldown_context:
                doc.cooldown_id = _normalize_forum_cooldown(cooldown_id)
            if update_assignee_context:
                doc.assignee_username = self._ensure_project_assignee(project_id, assignee_username)
            if update_status_context:
                doc.status = _normalize_forum_status(status)
        doc.content = content
        # None means the caller omitted the field: keep existing rich content.
        # An explicit [] clears it (e.g. a plain-Markdown edit).
        if content_blocks is not None:
            doc.content_blocks = content_blocks
        doc.system_info.update_time()
        doc.save()

        if self._notifications:
            root_post_id = str(doc.id)
            root_title = doc.title
            if doc.parent_id is not None:
                root_doc = ForumPostDocument.find_one(
                    {"_id": ObjectId(doc.parent_id), "project_id": project_id, "is_deleted": False}
                ).run()
                if root_doc:
                    root_post_id = str(root_doc.id)
                    root_title = root_doc.title
            try:
                self._notifications.notify_forum_event(
                    project_id=project_id,
                    post_id=str(doc.id),
                    root_post_id=root_post_id,
                    actor_username=username,
                    content=content,
                    title=root_title or "Forum thread",
                )
            except Exception:
                logger.exception("Failed to create forum notifications for post %s", doc.id)

        return self._to_response(doc)

    def delete_post(
        self,
        *,
        project_id: str,
        post_id: str,
        username: str,
        role: ProjectRole | None,
    ) -> SuccessResponse:
        """Delete a forum post."""
        doc = ForumPostDocument.find_one(
            {"_id": ObjectId(post_id), "project_id": project_id, "is_deleted": False}
        ).run()
        if doc is None:
            raise HTTPException(status_code=404, detail="Forum post not found")
        user_id = self._user_id_for_username(username)
        if not self._is_author(doc, user_id=user_id) and role != ProjectRole.OWNER:
            raise HTTPException(
                status_code=403, detail="Only the author or project owner can delete this post"
            )

        doc.is_deleted = True
        doc.system_info.update_time()
        doc.save()
        if doc.parent_id is None:
            replies = ForumPostDocument.find(
                {"project_id": project_id, "parent_id": post_id, "is_deleted": False}
            ).to_list()
            for reply in replies:
                reply.is_deleted = True
                reply.system_info.update_time()
                reply.save()
        return SuccessResponse(message="Forum post archived")

    def close_post(
        self,
        *,
        project_id: str,
        post_id: str,
        username: str,
        role: ProjectRole | None,
    ) -> SuccessResponse:
        """Close a forum thread."""
        doc = ForumPostDocument.find_one(
            {
                "_id": ObjectId(post_id),
                "project_id": project_id,
                "parent_id": None,
                "is_deleted": False,
            }
        ).run()
        if doc is None:
            raise HTTPException(status_code=404, detail="Forum thread not found")
        user_id = self._user_id_for_username(username)
        if not self._is_author(doc, user_id=user_id) and role != ProjectRole.OWNER:
            raise HTTPException(
                status_code=403, detail="Only the author or project owner can close this thread"
            )

        doc.status = "resolved"
        doc.system_info.update_time()
        doc.save()
        return SuccessResponse(message="Forum thread resolved")

    def reopen_post(
        self,
        *,
        project_id: str,
        post_id: str,
        username: str,
        role: ProjectRole | None,
    ) -> SuccessResponse:
        """Reopen a forum thread."""
        doc = ForumPostDocument.find_one(
            {
                "_id": ObjectId(post_id),
                "project_id": project_id,
                "parent_id": None,
                "is_deleted": False,
            }
        ).run()
        if doc is None:
            raise HTTPException(status_code=404, detail="Forum thread not found")
        user_id = self._user_id_for_username(username)
        if not self._is_author(doc, user_id=user_id) and role != ProjectRole.OWNER:
            raise HTTPException(
                status_code=403, detail="Only the author or project owner can reopen this thread"
            )

        doc.status = "open"
        doc.system_info.update_time()
        doc.save()
        return SuccessResponse(message="Forum thread reopened")
