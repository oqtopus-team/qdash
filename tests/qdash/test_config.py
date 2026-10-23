import pytest
from pydantic import ValidationError

from qdash.config import Settings, resolve_api_cors_origins


def test_resolve_api_cors_origins_prefers_explicit_list() -> None:
    settings = Settings.model_construct(
        env="production",
        api_cors_origins=("https://app.example.com", "https://admin.example.com"),
        client_url="",
        prefect_api_url="http://prefect.example.com",
        postgres_data_path="/tmp/postgres",
        mongo_data_path="/tmp/mongo",
        calib_data_path="/tmp/calib",
    )

    assert resolve_api_cors_origins(settings) == [
        "https://app.example.com",
        "https://admin.example.com",
    ]


def test_resolve_api_cors_origins_falls_back_to_client_url() -> None:
    settings = Settings.model_construct(
        env="production",
        client_url="https://app.example.com",
        api_cors_origins=(),
        prefect_api_url="http://prefect.example.com",
        postgres_data_path="/tmp/postgres",
        mongo_data_path="/tmp/mongo",
        calib_data_path="/tmp/calib",
    )

    assert resolve_api_cors_origins(settings) == ["https://app.example.com"]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("  https://app.example.com/  ", "https://app.example.com"),
        ("https://app.example.com:8443///", "https://app.example.com:8443"),
        ("HTTPS://EXAMPLE.COM:443/", "https://example.com"),
        ("HTTP://LOCALHOST:80/", "http://localhost"),
        ("https://例え.テスト/", "https://xn--r8jz45g.xn--zckzah"),
        ("http://localhost:5714", "http://localhost:5714"),
    ],
)
def test_client_url_normalizes_public_origin(value: str, expected: str) -> None:
    """CLIENT_URL trims whitespace and trailing slashes while preserving its origin."""
    settings = Settings.model_validate(
        {
            "env": "test",
            "client_url": value,
            "prefect_api_url": "http://prefect.example.com",
            "postgres_data_path": "/tmp/postgres",
            "mongo_data_path": "/tmp/mongo",
            "calib_data_path": "/tmp/calib",
        }
    )

    assert settings.client_url == expected
    assert settings.public_origin == expected
    assert resolve_api_cors_origins(settings) == [expected]


@pytest.mark.parametrize(
    "value",
    [
        "ftp://app.example.com",
        "https://user:secret@app.example.com",
        "https://app.example.com/path",
        "https://app.example.com/?",
        "https://app.example.com/#",
        "https://app.example.com:invalid",
        "https://app.example.com:",
        "https://app.example.com:0",
        "https://app.example.com:65536",
        "https://app example.com",
        "https://app|example.com",
        "https://999.999.999.999",
    ],
)
def test_client_url_rejects_non_origin_values(value: str) -> None:
    """CLIENT_URL rejects schemes, credentials, paths, and URL components beyond origin."""
    with pytest.raises(ValidationError):
        Settings.model_validate(
            {
                "env": "test",
                "client_url": value,
                "prefect_api_url": "http://prefect.example.com",
                "postgres_data_path": "/tmp/postgres",
                "mongo_data_path": "/tmp/mongo",
                "calib_data_path": "/tmp/calib",
            }
        )


def test_public_origin_falls_back_to_local_ui_port() -> None:
    """An unset CLIENT_URL resolves to the configured local UI port."""
    settings = Settings.model_construct(client_url="", ui_port=3000)

    assert settings.public_origin == "http://localhost:3000"


def test_resolve_api_cors_origins_uses_localhost_defaults_in_local_env() -> None:
    settings = Settings.model_construct(
        env="local",
        client_url="",
        api_cors_origins=(),
        ui_port=3000,
        prefect_api_url="http://prefect.example.com",
        postgres_data_path="/tmp/postgres",
        mongo_data_path="/tmp/mongo",
        calib_data_path="/tmp/calib",
    )

    assert resolve_api_cors_origins(settings) == [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]


def test_boolean_settings_treat_empty_env_strings_as_false() -> None:
    """Empty or whitespace-only env strings parse as False for boolean settings."""
    settings = Settings.model_validate(
        {
            "env": "test",
            "prefect_api_url": "http://prefect.example.com",
            "postgres_data_path": "/tmp/postgres",
            "mongo_data_path": "/tmp/mongo",
            "calib_data_path": "/tmp/calib",
            "slack_forum_notification": "",
        }
    )

    assert settings.slack_forum_notification is False


def test_boolean_settings_parse_non_empty_strings() -> None:
    """Non-empty strings parse with normal boolean semantics."""
    settings = Settings.model_validate(
        {
            "env": "test",
            "prefect_api_url": "http://prefect.example.com",
            "postgres_data_path": "/tmp/postgres",
            "mongo_data_path": "/tmp/mongo",
            "calib_data_path": "/tmp/calib",
            "slack_forum_notification": "true",
        }
    )

    assert settings.slack_forum_notification is True


def test_resolve_api_cors_origins_returns_empty_list_without_configuration() -> None:
    settings = Settings.model_construct(
        env="production",
        client_url="",
        api_cors_origins=(),
        ui_port=5714,
        prefect_api_url="http://prefect.example.com",
        postgres_data_path="/tmp/postgres",
        mongo_data_path="/tmp/mongo",
        calib_data_path="/tmp/calib",
    )

    assert resolve_api_cors_origins(settings) == []
