"""Notification router."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from qdash.api.dependencies import get_notification_service
from qdash.api.lib.auth import get_current_active_user
from qdash.api.lib.project import get_project_id_from_header
from qdash.api.schemas.auth import User
from qdash.api.schemas.notification import (
    ListNotificationsResponse,
    NotificationResponse,
    UnreadNotificationCountResponse,
)
from qdash.api.services.notification_service import NotificationService

router = APIRouter(prefix="/notifications")


@router.get(
    "",
    summary="List current user's notifications",
    operation_id="listNotifications",
    response_model=ListNotificationsResponse,
)
def list_notifications(
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[NotificationService, Depends(get_notification_service)],
    project_id: Annotated[str | None, Depends(get_project_id_from_header)] = None,
    unread_only: Annotated[bool, Query(description="Only return unread notifications")] = False,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> ListNotificationsResponse:
    """List notifications addressed to the current user."""
    return service.list_notifications(
        username=current_user.username,
        project_id=project_id,
        unread_only=unread_only,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/unread-count",
    summary="Get unread notification count",
    operation_id="getUnreadNotificationCount",
    response_model=UnreadNotificationCountResponse,
)
def get_unread_count(
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[NotificationService, Depends(get_notification_service)],
    project_id: Annotated[str | None, Depends(get_project_id_from_header)] = None,
) -> UnreadNotificationCountResponse:
    """Return unread notification count for the current user."""
    return service.unread_count(username=current_user.username, project_id=project_id)


@router.patch(
    "/{notification_id}/read",
    summary="Mark a notification as read",
    operation_id="markNotificationRead",
    response_model=NotificationResponse,
)
def mark_notification_read(
    notification_id: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[NotificationService, Depends(get_notification_service)],
) -> NotificationResponse:
    """Mark one notification as read."""
    return service.mark_read(notification_id=notification_id, username=current_user.username)


@router.patch(
    "/read-all",
    summary="Mark all notifications as read",
    operation_id="markAllNotificationsRead",
    response_model=dict[str, int],
)
def mark_all_notifications_read(
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[NotificationService, Depends(get_notification_service)],
    project_id: Annotated[str | None, Depends(get_project_id_from_header)] = None,
) -> dict[str, int]:
    """Mark all matching notifications as read."""
    return service.mark_all_read(username=current_user.username, project_id=project_id)
