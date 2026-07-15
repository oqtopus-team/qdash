"""Tests for Slack notification service."""

from __future__ import annotations

import httpx

from qdash.api.services.slack_notification_service import SlackNotificationService
from qdash.config import Settings
from qdash.dbmodel.forum import ForumPostDocument
from qdash.dbmodel.system_setting import SystemSettingDocument


def _settings(webhook_url: str = "https://hooks.slack.test/services/T000/B000/secret") -> Settings:
    return Settings.model_construct(
        env="test",
        client_url="http://localhost:3000",
        prefect_api_url="http://localhost:4200/api",
        slack_webhook_url=webhook_url,
        postgres_data_path="/tmp/postgres",
        mongo_data_path="/tmp/mongo",
        calib_data_path="/tmp/calib",
    )


def _post(**overrides: object) -> ForumPostDocument:
    data = {
        "project_id": "project-1",
        "number": 7,
        "category": "qubit",
        "username": "alice",
        "title": "T1 drift on Q12",
        "content": "@qdash please inspect\nLine one\nLine two\nLine three\nLine four",
        "chip_id": "chip-a",
        "target_type": "qubit",
        "target_id": "Q12",
    }
    data.update(overrides)
    return ForumPostDocument(**data)


def _block_texts(payload: dict[str, object]) -> str:
    blocks = payload["blocks"]
    assert isinstance(blocks, list)
    return "\n".join(str(block) for block in blocks)


def test_build_forum_post_payload_contains_expected_fields(init_db) -> None:
    service = SlackNotificationService(settings=_settings())

    payload = service._build_forum_post_payload(post=_post(), actor_username="alice")

    text = _block_texts(payload)
    assert payload["text"] == "New forum thread: #7 T1 drift on Q12"
    assert "#7 T1 drift on Q12" in text
    assert "alice" in text
    assert "test" in text
    assert "chip-a" in text
    assert "qubit:Q12" in text
    assert "Line one" in text
    assert "@qdash" not in text


def test_notify_forum_post_skips_when_webhook_url_missing(init_db, monkeypatch) -> None:
    calls: list[dict[str, object]] = []
    SystemSettingDocument.set_slack_forum_notifications_enabled(True)
    monkeypatch.setattr("qdash.api.services.slack_notification_service.httpx.post", calls.append)
    service = SlackNotificationService(settings=_settings(webhook_url=""))

    service.notify_forum_post(post=_post(), actor_username="alice")

    assert calls == []


def test_notify_forum_post_skips_when_flag_disabled(init_db, monkeypatch) -> None:
    calls: list[dict[str, object]] = []
    monkeypatch.setattr("qdash.api.services.slack_notification_service.httpx.post", calls.append)
    service = SlackNotificationService(settings=_settings())

    service.notify_forum_post(post=_post(), actor_username="alice")

    assert calls == []


def test_notify_forum_post_sends_when_enabled(init_db, monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    class _Response:
        def raise_for_status(self) -> None:
            return None

    def fake_post(url: str, *, json: dict[str, object], timeout: float) -> _Response:
        calls.append({"url": url, "json": json, "timeout": timeout})
        return _Response()

    SystemSettingDocument.set_slack_forum_notifications_enabled(True)
    monkeypatch.setattr("qdash.api.services.slack_notification_service.httpx.post", fake_post)
    service = SlackNotificationService(settings=_settings())

    service.notify_forum_post(post=_post(), actor_username="alice")

    assert calls == [
        {
            "url": "https://hooks.slack.test/services/T000/B000/secret",
            "json": service._build_forum_post_payload(post=_post(), actor_username="alice"),
            "timeout": 5.0,
        }
    ]


def test_notify_forum_post_swallows_httpx_errors(init_db, monkeypatch) -> None:
    def fail_post(url: str, *, json: dict[str, object], timeout: float) -> httpx.Response:
        raise httpx.ConnectError("network down")

    SystemSettingDocument.set_slack_forum_notifications_enabled(True)
    monkeypatch.setattr("qdash.api.services.slack_notification_service.httpx.post", fail_post)
    service = SlackNotificationService(settings=_settings())

    service.notify_forum_post(post=_post(), actor_username="alice")


def test_notify_forum_post_ignores_replies_and_ai_replies(init_db, monkeypatch) -> None:
    calls: list[dict[str, object]] = []
    SystemSettingDocument.set_slack_forum_notifications_enabled(True)
    monkeypatch.setattr("qdash.api.services.slack_notification_service.httpx.post", calls.append)
    service = SlackNotificationService(settings=_settings())

    service.notify_forum_post(post=_post(parent_id="root-id"), actor_username="alice")
    service.notify_forum_post(post=_post(is_ai_reply=True), actor_username="qdash")

    assert calls == []
