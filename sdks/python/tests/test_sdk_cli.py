"""The ``qdash`` command: ``qdash config init`` writes a config.toml the SDK reads back."""

from __future__ import annotations

import os
import re
import stat
import subprocess
import sys
from pathlib import Path

import pytest
import tomllib

from qdash.sdk import QDashConfig
from qdash.sdk._cli import main, render_config, toml_key, toml_string
from qdash.sdk._config import _TOML_PROFILE_KEYS

SECRET = "s3cret-token-value"  # noqa: S105 - a marker that must not leak

TESTDATA = Path(__file__).resolve().parents[2] / "testdata"
# The file both SDKs' `qdash config init` writes without options.
DEFAULT_FILE = (TESTDATA / "config_init_default.toml").read_text(encoding="utf-8")
# The file both SDKs write for TOKEN_ENV_ARGV.
TOKEN_ENV_FILE = (TESTDATA / "config_init_token_env.toml").read_text(encoding="utf-8")
TOKEN_ENV_ARGV = [
    "--profile", "lab", "--base-url", "https://qdash.example/api",
    "--project-id", "p1", "--api-token-env", "QDASH_LAB_TOKEN",
]  # fmt: skip
# A commented-out profile setting: "# key = value", optionally followed by a comment.
_COMMENTED_KEY = re.compile(r"^# ([a-z_]+) = ")


def _commented_settings(text: str) -> dict[str, object]:
    """The settings of the commented-out ``key = value`` lines, each parsed as TOML."""
    settings: dict[str, object] = {}
    for line in text.splitlines():
        if _COMMENTED_KEY.match(line):
            settings.update(tomllib.loads(line[2:]))
    return settings


@pytest.fixture
def xdg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """``$XDG_CONFIG_HOME``, not yet holding a qdash directory."""
    home = tmp_path / "xdg"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home))
    return home


def test_init_defaults(
    xdg: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("QDASH_LOCAL_TOKEN", raising=False)
    assert main(["config", "init"]) == 0

    path = xdg / "qdash" / "config.toml"
    assert path.read_text(encoding="utf-8") == DEFAULT_FILE
    out = capsys.readouterr().out
    assert f"Created {path} with profile local as default_profile." in out
    assert f"paste your QDash API token (Settings > API Token) into api_token in {path}" in out
    assert "export" not in out
    assert "not the default config path" not in out
    if os.name == "posix":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600

    # The commented-out api_token_env is not read: the empty api_token means no token.
    monkeypatch.setenv("QDASH_LOCAL_TOKEN", SECRET)
    config = QDashConfig.from_file()
    assert config == QDashConfig(base_url="http://localhost:5714/api")
    assert (config.timeout_sec, config.verify_tls, config.read_attempts) == (30, True, 3)


def test_default_file_lists_every_profile_key() -> None:
    document = tomllib.loads(DEFAULT_FILE)
    active = document["local"]
    assert active == {
        "base_url": "http://localhost:5714/api",
        "api_token": "",
        "timeout_sec": 30,
        "verify_tls": True,
        "read_attempts": 3,
    }
    commented = _commented_settings(DEFAULT_FILE)
    assert set(commented).isdisjoint(active)
    assert set(commented) | set(active) == _TOML_PROFILE_KEYS
    assert all(isinstance(value, str) and value for value in commented.values())
    assert commented["api_token_env"] == "QDASH_LOCAL_TOKEN"  # noqa: S105 - a variable name


def test_token_env_file_sets_the_variable_and_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "config.toml"
    assert main(["config", "init", *TOKEN_ENV_ARGV, "--path", str(path)]) == 0
    text = path.read_text(encoding="utf-8")
    assert text == TOKEN_ENV_FILE
    out = capsys.readouterr().out
    assert "Next: set QDASH_LAB_TOKEN to your QDash API token" in out
    assert "export QDASH_LAB_TOKEN=<token>" in out

    active = tomllib.loads(text)["lab"]
    assert active["api_token_env"] == "QDASH_LAB_TOKEN"  # noqa: S105 - a variable name
    assert active["project_id"] == "p1"
    assert "api_token" not in active
    assert text.count("project_id = ") == 1
    commented = _commented_settings(text)
    assert set(commented).isdisjoint(active)
    assert set(commented) | set(active) == _TOML_PROFILE_KEYS
    assert "api_token" in commented

    monkeypatch.setenv("QDASH_LAB_TOKEN", SECRET)
    config = QDashConfig.from_file(path=path)
    assert (config.api_token, config.project_id, config.username) == (SECRET, "p1", None)


def test_init_custom_values_read_back(
    tmp_path: Path, xdg: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "a" / "b" / "lab.toml"
    argv = [
        "config", "init", "--profile", "lab", "--base-url", "https://qdash.example/api",
        "--project-id", "p1", "--api-token-env", "QDASH_LAB_TOKEN", "--path", str(path),
    ]  # fmt: skip
    assert main(argv) == 0
    assert "not the default config path" in capsys.readouterr().out
    assert not (xdg / "qdash").exists()

    monkeypatch.setenv("QDASH_LAB_TOKEN", "t")
    config = QDashConfig.from_file(path=path)
    assert (config.base_url, config.api_token, config.project_id) == (
        "https://qdash.example/api",
        "t",
        "p1",
    )


def test_init_expands_the_home_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    assert main(["config", "init", "--path", "~/qdash.toml"]) == 0
    assert (tmp_path / "qdash.toml").exists()


@pytest.mark.parametrize(
    "profile",
    ["lab.dev", 'quote " and \\ backslash', "tab\tnew\nline", "ünïcode 量子", "[x]", "del\x7f"],
)
def test_profile_names_are_escaped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, profile: str
) -> None:
    path = tmp_path / "config.toml"
    url = 'http://h/"\\\n'
    assert (
        main(["config", "init", "--profile", profile, "--base-url", url, "--path", str(path)]) == 0
    )

    document = tomllib.loads(path.read_text(encoding="utf-8"))
    assert document["default_profile"] == profile
    assert set(document) == {"default_profile", profile}
    monkeypatch.setenv("QDASH_LOCAL_TOKEN", "t")
    assert QDashConfig.from_file(path=path).base_url == url
    assert QDashConfig.from_file(profile, path).base_url == url


def test_toml_helpers() -> None:
    assert toml_key("local-1_A") == "local-1_A"
    assert toml_key("a.b") == '"a.b"'
    assert toml_string('a"b\\c\x01\x7f\r') == '"a\\"b\\\\c\\u0001\\u007F\\r"'
    assert render_config("local", "http://localhost:5714/api") == DEFAULT_FILE
    text = render_config("p", "u", "E", "proj")
    assert '\napi_token_env = "E"\n' in text
    assert '\nproject_id = "proj"\n' in text


@pytest.mark.parametrize("symlink", [False, True])
def test_init_refuses_an_existing_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], symlink: bool
) -> None:
    path = tmp_path / "config.toml"
    target = tmp_path / "target.toml"
    if symlink:
        # A dangling symlink: following it would create the target.
        path.symlink_to(target)
    else:
        path.write_text("keep", encoding="utf-8")

    assert main(["config", "init", "--path", str(path)]) == 1
    assert "already exists; it was left unchanged" in capsys.readouterr().err
    if symlink:
        assert path.is_symlink()
        assert not target.exists()
    else:
        assert path.read_text(encoding="utf-8") == "keep"


def test_init_reports_an_uncreatable_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "file").write_text("", encoding="utf-8")
    assert main(["config", "init", "--path", str(tmp_path / "file" / "config.toml")]) == 1
    err = capsys.readouterr().err
    assert "cannot create" in err
    assert "already exists" not in err


@pytest.mark.parametrize(
    ("option", "value", "match"),
    [
        ("--profile", "", "--profile must not be empty"),
        ("--profile", "profiles", "reserved name"),
        ("--profile", "default_profile", "reserved name"),
        ("--profile", "bad\udcff", "valid Unicode"),
        ("--base-url", "", "--base-url must not be empty"),
        ("--project-id", "", "--project-id must not be empty"),
        ("--api-token-env", "", "environment variable name"),
        ("--api-token-env", SECRET + "-x", "environment variable name"),
        ("--api-token-env", "1ABC", "environment variable name"),
        ("--path", "config.json", "must name a .toml file"),
        ("--path", "", "--path must not be empty"),
    ],
)
def test_init_rejects_invalid_values(
    tmp_path: Path,
    xdg: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    option: str,
    value: str,
    match: str,
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["config", "init", option, value]) == 2
    err = capsys.readouterr().err
    assert match in err
    assert SECRET not in err
    assert not (xdg / "qdash").exists()
    assert not list(tmp_path.glob("*.json"))


@pytest.mark.parametrize("argv", [[], ["config"], ["config", "init", "--bogus"], ["other"]])
def test_usage_errors_exit_2(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(argv)
    assert excinfo.value.code == 2


def test_module_entry_point(tmp_path: Path) -> None:
    env = {**os.environ, "XDG_CONFIG_HOME": str(tmp_path)}
    run = [sys.executable, "-m", "qdash.sdk", "config", "init"]
    first = subprocess.run(run, env=env, capture_output=True, text=True, check=False)  # noqa: S603
    assert first.returncode == 0, first.stderr
    assert (tmp_path / "qdash" / "config.toml").read_text(encoding="utf-8") == DEFAULT_FILE
    second = subprocess.run(run, env=env, capture_output=True, text=True, check=False)  # noqa: S603
    assert second.returncode == 1
    assert second.stderr.startswith("qdash: error:")
