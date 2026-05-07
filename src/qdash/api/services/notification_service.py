"""Service for in-app notifications and mentions."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from bson import ObjectId
from fastapi import HTTPException, status
from pymongo.errors import DuplicateKeyError
from qdash.api.schemas.notification import (
    ListNotificationsResponse,
    NotificationResponse,
    UnreadNotificationCountResponse,
)
from qdash.common.datetime_utils import now
from qdash.dbmodel.notification import NotificationDocument
from qdash.dbmodel.project_membership import ProjectMembershipDocument
from qdash.dbmodel.user import UserDocument

if TYPE_CHECKING:
    from collections.abc import Iterable

MENTION_RE = re.compile(r"(?<![\w.-])@([A-Za-z0-9_.-]+)\b")
RESERVED_MENTIONS = {"qdash"}
EXCERPT_LIMIT = 180


class NotificationService:
    """Notification CRUD and mention fan-out."""

    @staticmethod
    def extract_mentions(content: str) -> list[str]:
        """Extract unique non-reserved usernames from Markdown text."""
        usernames: list[str] = []
        seen: set[str] = set()
        for match in MENTION_RE.finditer(content):
            username = match.group(1)
            key = username.lower()
            if key in RESERVED_MENTIONS or key in seen:
                continue
            seen.add(key)
            usernames.append(username)
        return usernames

    @staticmethod
    def _excerpt(content: str) -> str:
        compact = " ".join(content.split())
        if len(compact) <= EXCERPT_LIMIT:
            return compact
        return compact[: EXCERPT_LIMIT - 1].rstrip() + "..."

    @staticmethod
    def _to_response(doc: NotificationDocument) -> NotificationResponse:
        return NotificationResponse(
            id=str(doc.id),
            project_id=doc.project_id,
            recipient_username=doc.recipient_username,
            actor_username=doc.actor_username,
            kind=doc.kind,
            source_type=doc.source_type,
            source_id=doc.source_id,
            target_url=doc.target_url,
            title=doc.title,
            excerpt=doc.excerpt,
            read_at=doc.read_at,
            created_at=doc.created_at,
        )

    def _active_project_recipients(
        self, project_id: str, usernames: Iterable[str], actor_username: str
    ) -> list[str]:
        requested = {u for u in usernames if u != actor_username}
        if not requested:
            return []

        memberships = ProjectMembershipDocument.find(
            {"project_id": project_id, "status": "active", "username": {"$in": list(requested)}}
        ).to_list()
        active_usernames = {m.username for m in memberships}
        if not active_usernames:
            return []

        users = UserDocument.find(
            {"username": {"$in": list(active_usernames)}, "disabled": {"$ne": True}}
        ).to_list()
        return sorted({u.username for u in users})

    def create_notification(
        self,
        *,
        project_id: str,
        recipient_username: str,
        actor_username: str,
        kind: str,
        source_type: str,
        source_id: str,
        target_url: str,
        title: str,
        excerpt: str,
        dedupe_key: str,
    ) -> NotificationDocument | None:
        """Create a notification unless an equivalent one already exists."""
        doc = NotificationDocument(
            project_id=project_id,
            recipient_username=recipient_username,
            actor_username=actor_username,
            kind=kind,
            source_type=source_type,
            source_id=source_id,
            target_url=target_url,
            title=title,
            excerpt=self._excerpt(excerpt),
            dedupe_key=dedupe_key,
        )
        try:
            doc.insert()
        except DuplicateKeyError:
            return None
        return doc

    def notify_issue_event(
        self,
        *,
        project_id: str,
        issue_id: str,
        root_issue_id: str,
        task_id: str,
        actor_username: str,
        content: str,
        title: str | None,
        parent_author: str | None = None,
    ) -> None:
        """Create mention and reply notifications for an issue or reply."""
        target_url = f"/issues/{root_issue_id}"
        issue_title = title or f"Issue on {task_id}"
        mentioned = self._active_project_recipients(
            project_id, self.extract_mentions(content), actor_username
        )

        for recipient in mentioned:
            self.create_notification(
                project_id=project_id,
                recipient_username=recipient,
                actor_username=actor_username,
                kind="mention",
                source_type="issue",
                source_id=issue_id,
                target_url=target_url,
                title=f"{actor_username} mentioned you in {issue_title}",
                excerpt=content,
                dedupe_key=f"mention:issue:{issue_id}:{recipient}",
            )

        if parent_author and parent_author != actor_username and parent_author not in mentioned:
            self.create_notification(
                project_id=project_id,
                recipient_username=parent_author,
                actor_username=actor_username,
                kind="issue_reply",
                source_type="issue",
                source_id=issue_id,
                target_url=target_url,
                title=f"{actor_username} replied to {issue_title}",
                excerpt=content,
                dedupe_key=f"issue_reply:{issue_id}:{parent_author}",
            )

    def notify_note_mentions(
        self,
        *,
        project_id: str,
        note_event_id: str,
        actor_username: str,
        content: str,
        target_url: str,
        title: str,
    ) -> None:
        """Create mention notifications for a note event."""
        recipients = self._active_project_recipients(
            project_id, self.extract_mentions(content), actor_username
        )
        for recipient in recipients:
            self.create_notification(
                project_id=project_id,
                recipient_username=recipient,
                actor_username=actor_username,
                kind="note_mention",
                source_type="note_event",
                source_id=note_event_id,
                target_url=target_url,
                title=title,
                excerpt=content,
                dedupe_key=f"mention:note_event:{note_event_id}:{recipient}",
            )

    def notify_forum_event(
        self,
        *,
        project_id: str,
        post_id: str,
        root_post_id: str,
        actor_username: str,
        content: str,
        title: str,
        parent_author: str | None = None,
    ) -> None:
        """Create mention and reply notifications for a forum thread."""
        target_url = f"/forum/{root_post_id}"
        mentioned = self._active_project_recipients(
            project_id, self.extract_mentions(content), actor_username
        )

        for recipient in mentioned:
            self.create_notification(
                project_id=project_id,
                recipient_username=recipient,
                actor_username=actor_username,
                kind="forum_mention",
                source_type="forum_post",
                source_id=post_id,
                target_url=target_url,
                title=f"{actor_username} mentioned you in {title}",
                excerpt=content,
                dedupe_key=f"mention:forum_post:{post_id}:{recipient}",
            )

        if parent_author and parent_author != actor_username and parent_author not in mentioned:
            self.create_notification(
                project_id=project_id,
                recipient_username=parent_author,
                actor_username=actor_username,
                kind="forum_reply",
                source_type="forum_post",
                source_id=post_id,
                target_url=target_url,
                title=f"{actor_username} replied to {title}",
                excerpt=content,
                dedupe_key=f"forum_reply:{post_id}:{parent_author}",
            )

    def list_notifications(
        self,
        *,
        username: str,
        project_id: str | None,
        unread_only: bool,
        skip: int,
        limit: int,
    ) -> ListNotificationsResponse:
        """List notifications for a user."""
        query: dict[str, object] = {"recipient_username": username}
        if project_id:
            query["project_id"] = project_id
        if unread_only:
            query["read_at"] = None

        unread_query: dict[str, object] = {"recipient_username": username, "read_at": None}
        if project_id:
            unread_query["project_id"] = project_id

        total = NotificationDocument.find(query).count()
        unread_count = NotificationDocument.find(unread_query).count()
        docs = (
            NotificationDocument.find(query).sort("-created_at").skip(skip).limit(limit).to_list()
        )
        return ListNotificationsResponse(
            notifications=[self._to_response(doc) for doc in docs],
            total=total,
            unread_count=unread_count,
            skip=skip,
            limit=limit,
        )

    def unread_count(
        self, *, username: str, project_id: str | None
    ) -> UnreadNotificationCountResponse:
        """Return unread notification count for a user."""
        query: dict[str, object] = {"recipient_username": username, "read_at": None}
        if project_id:
            query["project_id"] = project_id
        return UnreadNotificationCountResponse(
            unread_count=NotificationDocument.find(query).count()
        )

    def mark_read(self, *, notification_id: str, username: str) -> NotificationResponse:
        """Mark one notification as read."""
        doc = NotificationDocument.find_one(
            {"_id": ObjectId(notification_id), "recipient_username": username}
        ).run()
        if doc is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found"
            )
        if doc.read_at is None:
            doc.read_at = now()
            doc.save()
        return self._to_response(doc)

    def mark_all_read(self, *, username: str, project_id: str | None) -> dict[str, int]:
        """Mark all matching notifications as read."""
        query: dict[str, object] = {"recipient_username": username, "read_at": None}
        if project_id:
            query["project_id"] = project_id
        read_at = now()
        result = NotificationDocument.find(query).update_many({"$set": {"read_at": read_at}}).run()
        modified_count = getattr(result, "modified_count", 0)
        return {"updated": int(modified_count)}
