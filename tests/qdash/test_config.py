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
            "enable_local_codex_agent": "  ",
        }
    )

    assert settings.slack_forum_notification is False
    assert settings.enable_local_codex_agent is False


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
            "enable_local_codex_agent": "false",
        }
    )

    assert settings.slack_forum_notification is True
    assert settings.enable_local_codex_agent is False


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
