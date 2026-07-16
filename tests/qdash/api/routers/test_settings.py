"""Tests for settings API."""

from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.user import UserDocument


def test_get_settings_excludes_slack_secrets(test_client, init_db) -> None:
    UserDocument(
        username="settings-user",
        hashed_password="hashed",
        access_token="settings-token",
        system_info=SystemInfoModel(),
    ).insert()

    response = test_client.get("/settings", headers={"Authorization": "Bearer settings-token"})

    assert response.status_code == 200
    data = response.json()
    assert "slack_bot_token" not in data
    assert "slack_forum_notification" not in data
    assert "slack_channel_id" in data
