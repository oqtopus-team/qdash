"""Schemas for in-app notifications."""

from datetime import datetime

from pydantic import BaseModel, Field


class NotificationResponse(BaseModel):
    """Single notification row."""

    id: str
    project_id: str
    recipient_user_id: str | None = None
    recipient_username: str
    actor_user_id: str | None = None
    actor_username: str
    kind: str
    source_type: str
    source_id: str
    target_url: str
    title: str
    excerpt: str = ""
    read_at: datetime | None = None
    created_at: datetime


class ListNotificationsResponse(BaseModel):
    """Paginated notifications for the current user."""

    notifications: list[NotificationResponse]
    total: int
    unread_count: int
    skip: int
    limit: int


class UnreadNotificationCountResponse(BaseModel):
    """Unread notification count."""

    unread_count: int = Field(..., ge=0)
