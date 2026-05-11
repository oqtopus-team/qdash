"""Forum service for QDash API."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

from bson import ObjectId
from bunnet import SortDirection
from pymongo.errors import DuplicateKeyError
from qdash.api.schemas.forum import (
    ForumCategoryResponse,
    ForumPostResponse,
    ListForumCategoriesResponse,
    ListForumPostsResponse,
)
from qdash.api.schemas.success import SuccessResponse
from qdash.datamodel.project import ProjectRole
from qdash.dbmodel.forum import ForumCategoryDocument, ForumPostDocument
from qdash.dbmodel.user import UserDocument
from starlette.exceptions import HTTPException

if TYPE_CHECKING:
    from qdash.api.services.notification_service import NotificationService

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
logger = logging.getLogger(__name__)


class ForumService:
    """Service for project forum CRUD operations."""

    def __init__(self, notification_service: NotificationService | None = None) -> None:
        self._notifications = notification_service

    @staticmethod
    def _user_id_for_username(username: str) -> str | None:
        user = UserDocument.find_one({"username": username}).run()
        return user.user_id if user else None

    @staticmethod
    def _is_author(doc: ForumPostDocument, *, user_id: str | None) -> bool:
        return bool(user_id and doc.user_id == user_id)

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
            category=doc.category,
            user_id=doc.user_id,
            username=doc.username,
            avatar_key=user.avatar_key if user else None,
            title=doc.title,
            content=doc.content,
            parent_id=doc.parent_id,
            reply_count=reply_count,
            is_closed=doc.is_closed,
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
        is_closed: bool | None = False,
    ) -> ListForumPostsResponse:
        """List root forum threads with reply counts."""
        query: dict[str, object] = {
            "project_id": project_id,
            "parent_id": None,
            "is_deleted": False,
        }
        if category:
            query["category"] = category
        if is_closed is not None:
            query["is_closed"] = is_closed

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
            if root_doc.is_closed:
                raise HTTPException(status_code=409, detail="Forum thread is closed")
            category = root_doc.category
        else:
            self._ensure_active_category(project_id, category)

        doc = ForumPostDocument(
            project_id=project_id,
            category=category,
            user_id=self._user_id_for_username(username),
            username=username,
            title=title if parent_id is None else None,
            content=content,
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
            category=root_doc.category,
            username="qdash",
            title=None,
            content=content,
            parent_id=parent_id,
            is_ai_reply=True,
        )
        ai_doc.insert()
        return self._to_response(ai_doc)

    def update_post(
        self,
        *,
        project_id: str,
        post_id: str,
        username: str,
        title: str | None,
        content: str,
    ) -> ForumPostResponse:
        """Update a forum post."""
        doc = ForumPostDocument.find_one(
            {"_id": ObjectId(post_id), "project_id": project_id, "is_deleted": False}
        ).run()
        if doc is None:
            raise HTTPException(status_code=404, detail="Forum post not found")
        user_id = self._user_id_for_username(username)
        if not self._is_author(doc, user_id=user_id):
            raise HTTPException(status_code=403, detail="You can only edit your own posts")

        if doc.parent_id is None and title is not None:
            doc.title = title
        doc.content = content
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

        doc.is_closed = True
        doc.save()
        return SuccessResponse(message="Forum thread closed")

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

        doc.is_closed = False
        doc.save()
        return SuccessResponse(message="Forum thread reopened")
