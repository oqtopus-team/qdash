from qdash.common.utils.commit_message import format_machine_commit_message


def test_format_machine_commit_message_prefixes_env(monkeypatch):
    monkeypatch.setenv("ENV", "prod-osaka")

    message = format_machine_commit_message("Update params", "2026-05-22T12:00:00+00:00")

    assert message == "[ENV=prod-osaka] Update params at 2026-05-22T12:00:00+00:00"


def test_format_machine_commit_message_sanitizes_env_token():
    message = format_machine_commit_message(
        "Update params",
        "2026-05-22T12:00:00+00:00",
        env=" staging env ",
    )

    assert message == "[ENV=staging-env] Update params at 2026-05-22T12:00:00+00:00"


def test_format_machine_commit_message_uses_unknown_for_empty_env():
    message = format_machine_commit_message(
        "Update params",
        "2026-05-22T12:00:00+00:00",
        env=" ",
    )

    assert message == "[ENV=unknown] Update params at 2026-05-22T12:00:00+00:00"
