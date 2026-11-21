"""Tests for the shared Ruff formatter of editor sources."""

from __future__ import annotations

import subprocess
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import tomllib

from qdash.api.lib import python_format
from qdash.api.lib.python_format import (
    MAX_FORMAT_OUTPUT_BYTES,
    MAX_FORMAT_SOURCE_BYTES,
    RUFF_LINE_LENGTH,
    RUFF_TARGET_VERSION,
    FormatterUnavailableError,
    SourceTooLargeError,
    format_python_source,
    format_source_for_save,
    ruff_format_command,
)

REPO_ROOT = Path(__file__).resolve().parents[4]


def test_formats_source_with_the_project_line_length() -> None:
    source = "x = (1,\n2)\nvalues = [" + ", ".join(str(i) for i in range(40)) + "]\n"

    result = format_python_source(source)

    assert result.status == "formatted"
    assert result.source.startswith("x = (1, 2)\n")
    assert all(len(line) <= RUFF_LINE_LENGTH for line in result.source.splitlines())
    assert result.message is None


def test_formatting_is_stable() -> None:
    once = format_python_source("def f(a,b):\n  return {'a':a,'b':b}\n").source

    again = format_python_source(once)

    assert again.status == "unchanged"
    assert again.source == once


def test_syntax_error_returns_the_input_and_its_location() -> None:
    source = "import math\n\ndef broken(:\n    pass\n"

    result = format_python_source(source)

    assert result.status == "syntax_error"
    assert result.source == source
    assert result.line == 3
    assert result.column == 12
    assert result.message


def test_the_source_is_parsed_and_never_executed(tmp_path: Path) -> None:
    marker = tmp_path / "executed"
    source = (
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('x')\nraise SystemExit(3)\n"
    )

    result = format_python_source(source)

    assert result.status in {"formatted", "unchanged"}
    assert not marker.exists()


def test_settings_mirror_the_repository_ruff_configuration() -> None:
    config = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"][
        "ruff"
    ]

    assert config["line-length"] == RUFF_LINE_LENGTH
    assert config["target-version"] == RUFF_TARGET_VERSION


def test_the_command_is_fixed_and_reads_stdin() -> None:
    command = ruff_format_command("/opt/ruff")

    assert command[:3] == ["/opt/ruff", "format", "--isolated"]
    assert command[-1] == "-"
    assert "--stdin-filename" in command


def test_a_source_over_the_limit_is_refused_before_ruff_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("ruff must not run")

    monkeypatch.setattr(subprocess, "run", fail)

    with pytest.raises(SourceTooLargeError):
        format_python_source("#" * (MAX_FORMAT_SOURCE_BYTES + 1))


def test_a_timeout_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    def slow(command: list[str], **kwargs: Any) -> None:
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", slow)

    with pytest.raises(FormatterUnavailableError, match="longer than"):
        format_python_source("x = 1\n")


def test_a_missing_ruff_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing() -> str:
        raise FormatterUnavailableError("Ruff is not installed")

    monkeypatch.setattr(python_format, "_ruff_binary", missing)

    with pytest.raises(FormatterUnavailableError, match="not installed"):
        format_python_source("x = 1\n")


def test_an_unexpected_failure_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_a, **_k: SimpleNamespace(returncode=2, stdout=b"", stderr=b"error: panic"),
    )

    with pytest.raises(FormatterUnavailableError, match="panic"):
        format_python_source("x = 1\n")


def test_an_oversized_output_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_a, **_k: SimpleNamespace(
            returncode=0, stdout=b"#" * (MAX_FORMAT_OUTPUT_BYTES + 1), stderr=b""
        ),
    )

    with pytest.raises(FormatterUnavailableError, match="too large"):
        format_python_source("x = 1\n")


def test_busy_slots_are_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(python_format, "_slots", threading.BoundedSemaphore(1))
    python_format._slots.acquire()

    with pytest.raises(FormatterUnavailableError, match="busy"):
        format_python_source("x = 1\n", timeout=0.01)


def test_save_stores_the_formatted_source() -> None:
    assert format_source_for_save("x=1\n") == "x = 1\n"


def test_save_keeps_a_source_that_cannot_be_parsed() -> None:
    source = "def broken(:\n"

    assert format_source_for_save(source) == source


def test_save_keeps_the_source_when_the_formatter_fails(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def unavailable(_source: str) -> None:
        raise FormatterUnavailableError("Formatting took longer than 10 s")

    monkeypatch.setattr(python_format, "format_python_source", unavailable)

    assert format_source_for_save("x=1\n") == "x=1\n"
    assert "without formatting" in caplog.text
