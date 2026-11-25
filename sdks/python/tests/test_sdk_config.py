"""Config file resolution: config.toml, its profiles and the deprecated config.ini."""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING

import httpx
import pytest

from qdash.sdk import QDash, QDashConfig, QDashConfigDeprecationWarning, QDashConfigError
from qdash.sdk._config import default_config_path, legacy_config_path

if TYPE_CHECKING:
    from pathlib import Path

SECRET = "s3cret-token-value"  # noqa: S105 - a marker that must not leak

TOML = """\
default_profile = "lab"

[default]
base_url = "http://default.local"
api_token = "default-token"

[lab]
base_url = "http://lab.local/"
api_token = "lab-token"
project_id = "lab"
timeout_sec = 9
verify_tls = false
read_attempts = 2
proxy = "http://proxy.local:3128"
"""

INI = (
    "[default]\nbase_url = http://ini-default.local\napi_token = d\n\n"
    "[lab]\nbase_url = http://ini-lab.local\napi_token = l\n"
)


@pytest.fixture
def config_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An empty ``$XDG_CONFIG_HOME/qdash``, so no test reads the real user config."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    directory = tmp_path / "xdg" / "qdash"
    directory.mkdir(parents=True)
    return directory


def write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def load_toml(tmp_path: Path, text: str, profile: str | None = None) -> QDashConfig:
    return QDashConfig.from_file(profile, write(tmp_path / "config.toml", text))


def test_the_default_paths_follow_xdg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert default_config_path() == tmp_path / "qdash" / "config.toml"
    assert legacy_config_path() == tmp_path / "qdash" / "config.ini"
    monkeypatch.delenv("XDG_CONFIG_HOME")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    assert default_config_path() == tmp_path / "home" / ".config" / "qdash" / "config.toml"


def test_toml_profile_values_and_types(tmp_path: Path) -> None:
    config = load_toml(tmp_path, TOML, "lab")

    assert (config.base_url, config.api_token, config.project_id) == (
        "http://lab.local",
        "lab-token",
        "lab",
    )
    assert (config.timeout_sec, config.verify_tls, config.read_attempts) == (9.0, False, 2)
    assert config.proxy == "http://proxy.local:3128"


def test_profile_selection_precedence(tmp_path: Path) -> None:
    # An explicit profile wins over default_profile.
    assert load_toml(tmp_path, TOML, "default").base_url == "http://default.local"
    # Without one, default_profile selects the profile.
    assert load_toml(tmp_path, TOML).base_url == "http://lab.local"
    # Without default_profile, the profile named "default".
    without_default = TOML.replace('default_profile = "lab"\n', "")
    assert load_toml(tmp_path, without_default).base_url == "http://default.local"


def test_from_profile_uses_the_default_profile_of_the_file(config_home: Path) -> None:
    write(config_home / "config.toml", TOML)
    with QDash.from_profile() as qdash:
        assert qdash.config.base_url == "http://lab.local"
        assert qdash.project_id == "lab"
    with QDash.from_profile("default") as qdash:
        assert qdash.config.base_url == "http://default.local"
    with QDash.from_profile(profile="lab", project_id="other") as qdash:
        assert qdash.project_id == "other"


def no_request(request: httpx.Request) -> httpx.Response:
    raise AssertionError(f"unexpected request: {request.method} {request.url}")


def test_qdash_without_config_reads_the_default_profile(config_home: Path) -> None:
    write(config_home / "config.toml", TOML)

    with QDash() as qdash:
        assert qdash.config == QDash.from_profile().config
        assert (qdash.config.base_url, qdash.project_id) == ("http://lab.local", "lab")
        assert (qdash.config.timeout_sec, qdash.config.read_attempts) == (9.0, 2)
    with QDash(None, project_id="other") as qdash:
        assert qdash.project_id == "other"
        assert qdash.config.base_url == "http://lab.local"


def test_qdash_without_config_falls_back_to_the_default_profile_name(
    config_home: Path,
) -> None:
    write(config_home / "config.toml", TOML.replace('default_profile = "lab"\n', ""))

    with QDash() as qdash:
        assert qdash.config == QDashConfig.from_file("default")
        assert qdash.config.base_url == "http://default.local"


def test_qdash_without_config_borrows_a_client_and_sends_nothing(config_home: Path) -> None:
    write(config_home / "config.toml", TOML)
    http_client = httpx.Client(transport=httpx.MockTransport(no_request))

    with QDash(http_client=http_client, project_id="p") as qdash:
        assert qdash._http_client is http_client
        assert qdash.project_id == "p"
    assert not http_client.is_closed
    http_client.close()


def test_qdash_with_a_config_reads_no_file(
    config_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The config directory holds a file the explicit config must not touch.
    write(config_home / "config.toml", "default_profile = \n")
    monkeypatch.setattr(
        "qdash.sdk._session._load_config",
        lambda *args, **kwargs: pytest.fail("QDash(config) read the config file"),
    )
    config = QDashConfig(base_url="http://explicit.local", api_token="t")

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        with QDash(config) as qdash:
            assert qdash.config == config


def test_qdash_without_config_does_not_fall_back_to_the_environment(
    config_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("QDASH_BASE_URL", "http://env.local")
    monkeypatch.setenv("QDASH_API_TOKEN", "env-token")

    with pytest.raises(QDashConfigError, match=r"Config file not found: .*config\.toml"):
        QDash()


@pytest.mark.parametrize(
    ("text", "match"),
    [
        ("default_profile = \n", "Invalid TOML"),
        ('default_profile = "absent"\n[default]\nbase_url = "http://d.local"\n', "absent"),
        ('[lab]\nbase_url = "http://lab.local"\n', "profile not found: default"),
    ],
)
def test_qdash_without_config_raises_config_errors(
    config_home: Path, text: str, match: str
) -> None:
    write(config_home / "config.toml", text)
    write(config_home / "config.ini", INI)

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        with pytest.raises(QDashConfigError, match=match):
            QDash()


def test_qdash_without_config_falls_back_to_ini_only_without_toml(config_home: Path) -> None:
    write(config_home / "config.ini", INI)

    with pytest.warns(QDashConfigDeprecationWarning) as record, QDash() as qdash:
        assert qdash.config.base_url == "http://ini-default.local"
    assert len(record) == 1
    assert record[0].filename == __file__


def test_discovery_prefers_toml_and_never_merges_the_ini(config_home: Path) -> None:
    write(config_home / "config.ini", INI)
    write(config_home / "config.toml", '[default]\nbase_url = "http://toml.local"\n')

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert QDashConfig.from_file().base_url == "http://toml.local"
        # "lab" exists only in the INI: no fallback to it.
        with pytest.raises(QDashConfigError, match="profile not found: lab"):
            QDashConfig.from_file("lab")


def test_discovery_falls_back_to_ini_only_without_toml(config_home: Path) -> None:
    ini_path = write(config_home / "config.ini", INI)

    with pytest.warns(QDashConfigDeprecationWarning) as record:
        config = QDashConfig.from_file()

    assert config.base_url == "http://ini-default.local"
    assert len(record) == 1
    message = str(record[0].message)
    assert str(ini_path) in message
    assert "deprecated" in message
    assert str(config_home / "config.toml") in message
    assert "top-level [<name>] tables" in message
    assert "qdash config init" in message
    assert "qdash-client keeps using config.ini" in message
    assert record[0].filename == __file__
    assert issubclass(QDashConfigDeprecationWarning, FutureWarning)

    with (
        pytest.warns(QDashConfigDeprecationWarning) as record,
        QDash.from_profile("lab") as qdash,
    ):
        assert qdash.config.base_url == "http://ini-lab.local"
    assert record[0].filename == __file__


def test_discovery_does_not_fall_back_on_an_invalid_toml(config_home: Path) -> None:
    write(config_home / "config.ini", INI)
    write(config_home / "config.toml", "default_profile = \n")

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        with pytest.raises(QDashConfigError, match="Invalid TOML"):
            QDashConfig.from_file()


def test_discovery_without_any_file(config_home: Path) -> None:
    with pytest.raises(QDashConfigError, match=r"Config file not found: .*config\.toml"):
        QDashConfig.from_file()


def test_explicit_paths_are_authoritative(config_home: Path, tmp_path: Path) -> None:
    write(config_home / "config.toml", TOML)
    write(config_home / "config.ini", INI)

    with pytest.raises(QDashConfigError, match="not found"):
        QDashConfig.from_file(path=tmp_path / "absent.toml")
    with (
        pytest.warns(QDashConfigDeprecationWarning),
        pytest.raises(QDashConfigError, match="not found"),
    ):
        QDashConfig.from_file(path=tmp_path / "absent.ini")
    other = write(tmp_path / "other.TOML", '[default]\nbase_url = "http://o.local"\n')
    assert QDashConfig.from_file(path=other).base_url == "http://o.local"
    with pytest.raises(QDashConfigError, match="profile not found: lab"):
        QDashConfig.from_file("lab", other)


def test_explicit_ini_keeps_its_keys_and_warns(tmp_path: Path) -> None:
    path = write(
        tmp_path / "client.ini",
        "[lab]\nbase_url = http://lab.local/\napi_token = t\ntimeout_seconds = 4\n"
        "verify_tls = false\nretry_max_attempts = 5\nmax_workers = 4\n",
    )
    with pytest.warns(QDashConfigDeprecationWarning, match="deprecated"):
        config = QDashConfig.from_file("lab", path)
    assert (config.base_url, config.timeout_sec, config.verify_tls, config.read_attempts) == (
        "http://lab.local",
        4.0,
        False,
        5,
    )


@pytest.mark.parametrize("name", ["config.yaml", "config", "config.json"])
def test_unsupported_extensions(tmp_path: Path, name: str) -> None:
    path = write(tmp_path / name, "")
    with pytest.raises(QDashConfigError, match="Unsupported config file extension"):
        QDashConfig.from_file(path=path)


def test_api_token_env_resolves_the_selected_profile_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    text = (
        '[default]\nbase_url = "http://d.local"\napi_token_env = "QDASH_TEST_TOKEN"\n'
        '[other]\nbase_url = "http://o.local"\napi_token_env = "QDASH_TEST_UNSET"\n'
    )
    monkeypatch.setenv("QDASH_TEST_TOKEN", SECRET)
    monkeypatch.delenv("QDASH_TEST_UNSET", raising=False)

    assert load_toml(tmp_path, text).api_token == SECRET


@pytest.mark.parametrize("value", [None, ""])
def test_api_token_env_unset_or_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str | None
) -> None:
    if value is None:
        monkeypatch.delenv("QDASH_TEST_TOKEN", raising=False)
    else:
        monkeypatch.setenv("QDASH_TEST_TOKEN", value)
    text = '[default]\nbase_url = "http://d.local"\napi_token_env = "QDASH_TEST_TOKEN"\n'
    with pytest.raises(QDashConfigError, match=r"QDASH_TEST_TOKEN .* is not set or empty"):
        load_toml(tmp_path, text)


def test_api_token_env_is_not_interpolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QDASH_TEST_TOKEN", SECRET)
    text = '[default]\nbase_url = "http://d.local"\napi_token = "${QDASH_TEST_TOKEN}"\n'
    assert load_toml(tmp_path, text).api_token == "${QDASH_TEST_TOKEN}"  # noqa: S105


@pytest.mark.parametrize(
    ("body", "match"),
    [
        ('api_token_env = ""', "must name an environment variable"),
        ("api_token_env = 1", "'api_token_env' in profile 'default' must be a string"),
        (f'api_token = "{SECRET}"\napi_token_env = "X"', "sets both"),
    ],
)
def test_api_token_env_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, body: str, match: str
) -> None:
    monkeypatch.setenv("X", SECRET)
    text = f'[default]\nbase_url = "http://d.local"\n{body}\n'
    with pytest.raises(QDashConfigError, match=match) as excinfo:
        load_toml(tmp_path, text)
    assert SECRET not in str(excinfo.value)


@pytest.mark.parametrize(
    ("text", "match"),
    [
        ('base_url = "http://x"\n', "Unknown top-level keys .*: base_url"),
        ("default_profile = 1\n", "default_profile .* must be a non-empty string"),
        ('default_profile = ""\n', "default_profile .* must be a non-empty string"),
        ('profiles = "lab"\n', r"removed \[profiles\.<name>\] layout"),
        ("[profiles.lab]\nbase_url = 'x'\n", r"removed \[profiles\.<name>\] layout"),
        ("lab = 1\n", "Unknown top-level keys .*: lab"),
        ('default_profile = "profiles"\n', "'profiles' is reserved"),
        ('default_profile = "missing"\n[lab]\nbase_url = "x"\n', "not found: missing"),
        ("[default]\nproject_id = 'p'\n", "'base_url' is required"),
        ("[default]\nbase_url = 'x'\ntimeout_seconds = 3\n", "Unknown keys .*timeout_"),
        ("[default]\nbase_url = 'x'\nverify_tls = 'false'\n", "must be a boolean"),
        ("[default]\nbase_url = 'x'\ntimeout_sec = '3'\n", "must be a number"),
        ("[default]\nbase_url = 'x'\ntimeout_sec = true\n", "must be a number"),
        ("[default]\nbase_url = 'x'\ntimeout_sec = 0\n", "timeout_sec"),
        ("[default]\nbase_url = 'x'\nread_attempts = 1.5\n", "must be an integer"),
        ("[default]\nbase_url = 'x'\nread_attempts = 0\n", "read_attempts"),
        ("[default]\nbase_url = 1\n", "'base_url' .* must be a string"),
        ("[default\n", "Invalid TOML"),
    ],
)
def test_invalid_toml_files(tmp_path: Path, text: str, match: str) -> None:
    with pytest.raises(QDashConfigError, match=match):
        load_toml(tmp_path, text)


def test_errors_do_not_carry_secrets(tmp_path: Path) -> None:
    cases = [
        f"[default]\nbase_url = 'x'\napi_token = 1\ncf_access_client_secret = 2\n"
        f"username = '{SECRET}'\nread_attempts = 0\n",
        f"[default]\nbase_url = 'x'\napi_token = '{SECRET}'\nread_attempts = 0\n",
        f"[default]\nbase_url = 'x'\napi_token = '{SECRET}\n",
    ]
    for text in cases:
        with pytest.raises(QDashConfigError) as excinfo:
            load_toml(tmp_path, text)
        assert SECRET not in str(excinfo.value)
        # No chained exception carries the input values either.
        assert excinfo.value.__cause__ is None
        assert excinfo.value.__context__ is None or excinfo.value.__suppress_context__


def test_unreadable_and_non_utf8_files(tmp_path: Path) -> None:
    directory = tmp_path / "dir.toml"
    directory.mkdir()
    with pytest.raises(QDashConfigError, match="Cannot read config file"):
        QDashConfig.from_file(path=directory)
    binary = tmp_path / "bad.toml"
    binary.write_bytes(b"\xff\xfe")
    with pytest.raises(QDashConfigError, match="not valid UTF-8"):
        QDashConfig.from_file(path=binary)


def test_the_sdk_toml_and_the_client_ini_coexist(config_home: Path) -> None:
    """qdash-client keeps its config.ini; qdash-sdk reads config.toml beside it."""
    client_config = pytest.importorskip("qdash.client").QDashConfig

    write(config_home / "config.ini", INI)
    write(config_home / "config.toml", TOML)

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert QDashConfig.from_file().base_url == "http://lab.local"
        assert client_config.from_file("lab").base_url == "http://ini-lab.local"
