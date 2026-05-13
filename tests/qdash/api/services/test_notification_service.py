"""Tests for notification mention handling."""

from qdash.api.services.notification_service import NotificationService
from qdash.datamodel.project import ProjectRole
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.notification import NotificationDocument
from qdash.dbmodel.project_membership import ProjectMembershipDocument
from qdash.dbmodel.user import UserDocument


def _create_user(
    username: str,
    *,
    status: str = "active",
    disabled: bool = False,
) -> UserDocument:
    user = UserDocument(
        username=username,
        hashed_password="hashed",
        access_token=f"{username}_token",
        default_project_id="test_project",
        disabled=disabled,
        system_info=SystemInfoModel(),
    )
    user.insert()
    ProjectMembershipDocument(
        project_id="test_project",
        user_id=user.user_id,
        username=username,
        role=ProjectRole.VIEWER,
        status=status,
        invited_by_user_id=user.user_id,
        invited_by=username,
    ).insert()
    return user


def test_project_mention_is_reserved_for_username_extraction() -> None:
    service = NotificationService()

    assert service.extract_mentions("@project please check with @alice and @QDash") == ["alice"]
    assert service.has_project_mention("Please check @Project") is True


def test_project_mention_notifies_active_project_members(init_db) -> None:
    service = NotificationService()
    _create_user("actor")
    active = _create_user("active")
    _create_user("pending", status="pending")
    _create_user("disabled", disabled=True)

    service.notify_issue_event(
        project_id="test_project",
        issue_id="issue_1",
        root_issue_id="root_1",
        task_id="task_1",
        actor_username="actor",
        content="@project please review",
        title="Calibration issue",
    )

    notifications = NotificationDocument.find({}).to_list()
    assert [notification.recipient_username for notification in notifications] == [active.username]
    assert notifications[0].kind == "mention"


def test_project_and_direct_mentions_are_deduplicated(init_db) -> None:
    service = NotificationService()
    _create_user("actor")
    _create_user("active")

    service.notify_forum_event(
        project_id="test_project",
        post_id="post_1",
        root_post_id="root_1",
        actor_username="actor",
        content="@project @active please review",
        title="Forum thread",
    )

    notifications = NotificationDocument.find({"recipient_username": "active"}).to_list()
    assert len(notifications) == 1
    assert notifications[0].kind == "forum_mention"
