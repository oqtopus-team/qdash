"""Format Python source text with the Ruff formatter.

Workflow and metric script editors share this formatter, and their save paths use it so
the stored source is the formatted text. The source is handled as data: it is piped to
``ruff format`` on stdin and the result is read from stdout. Ruff only parses the text; it
never imports or executes it, and no path or option comes from the caller. The run is
bounded by input size, output size, wall time and a small number of concurrent runs.

The options are fixed and ``--isolated`` ignores any configuration file, so the result
does not depend on the working directory of the API process. They mirror the repository's
``[tool.ruff]`` settings; a test keeps the two in step.
"""

from __future__ import annotations

import logging
import re
import subprocess
import threading
from dataclasses import dataclass
from typing import Literal

logger = logging.getLogger("uvicorn.app")

RUFF_LINE_LENGTH = 100
RUFF_TARGET_VERSION = "py310"
MAX_FORMAT_SOURCE_BYTES = 512 * 1024
# Formatting rarely grows a module; twice the input is a generous bound.
MAX_FORMAT_OUTPUT_BYTES = 2 * MAX_FORMAT_SOURCE_BYTES
FORMAT_TIMEOUT_SECONDS = 10.0
MAX_CONCURRENT_FORMATS = 4

# The name Ruff reports in diagnostics; it is never opened.
_STDIN_FILENAME = "source.py"
_PARSE_ERROR = re.compile(r"Failed to parse [^\n]*?:(\d+):(\d+):\s*(.+)")
_slots = threading.BoundedSemaphore(MAX_CONCURRENT_FORMATS)

FormatStatus = Literal["formatted", "unchanged", "syntax_error"]


class FormatterUnavailableError(RuntimeError):
    """Ruff could not format the source: missing, busy, too slow, or failed unexpectedly."""


class SourceTooLargeError(ValueError):
    """The source exceeds ``MAX_FORMAT_SOURCE_BYTES``."""


@dataclass(frozen=True)
class FormatResult:
    """Outcome of formatting one source text.

    ``source`` is the formatted text, or the input unchanged when it cannot be parsed.
    """

    status: FormatStatus
    source: str
    message: str | None = None
    line: int | None = None
    column: int | None = None


def _ruff_binary() -> str:
    """Return the Ruff executable installed with the ``ruff`` package."""
    try:
        from ruff.__main__ import find_ruff_bin
    except ImportError as exc:
        raise FormatterUnavailableError("Ruff is not installed") from exc
    try:
        return str(find_ruff_bin())
    except FileNotFoundError as exc:
        raise FormatterUnavailableError("Ruff is not installed") from exc


def ruff_format_command(binary: str) -> list[str]:
    """Return the fixed ``ruff format`` command that reads stdin and writes stdout."""
    return [
        binary,
        "format",
        "--isolated",
        "--no-cache",
        "--line-length",
        str(RUFF_LINE_LENGTH),
        "--target-version",
        RUFF_TARGET_VERSION,
        "--stdin-filename",
        _STDIN_FILENAME,
        "-",
    ]


def _syntax_error(source: str, stderr: str) -> FormatResult | None:
    match = _PARSE_ERROR.search(stderr)
    if match is None:
        return None
    return FormatResult(
        status="syntax_error",
        source=source,
        message=match.group(3).strip(),
        line=int(match.group(1)),
        column=int(match.group(2)),
    )


def format_python_source(source: str, *, timeout: float = FORMAT_TIMEOUT_SECONDS) -> FormatResult:
    """Format ``source`` with Ruff and return the result.

    A source Ruff cannot parse returns ``syntax_error`` with the input unchanged and the
    location of the first error.

    Raises:
        SourceTooLargeError: the source exceeds ``MAX_FORMAT_SOURCE_BYTES``.
        FormatterUnavailableError: Ruff is missing, all slots stay busy for ``timeout``,
            the run exceeds ``timeout``, its output is too large, or it fails otherwise.
    """
    data = source.encode("utf-8")
    if len(data) > MAX_FORMAT_SOURCE_BYTES:
        raise SourceTooLargeError(
            f"Source exceeds the {MAX_FORMAT_SOURCE_BYTES // 1024} KiB formatting limit"
        )
    command = ruff_format_command(_ruff_binary())
    if not _slots.acquire(timeout=timeout):
        raise FormatterUnavailableError("The formatter is busy; try again")
    try:
        completed = subprocess.run(  # noqa: S603 - fixed argv, the source goes to stdin
            command,
            input=data,
            capture_output=True,
            timeout=timeout,
            check=False,
            env={},
        )
    except subprocess.TimeoutExpired as exc:
        raise FormatterUnavailableError(f"Formatting took longer than {timeout:g} s") from exc
    except OSError as exc:
        raise FormatterUnavailableError(f"Ruff could not run: {exc}") from exc
    finally:
        _slots.release()

    stderr = completed.stderr[:4096].decode("utf-8", errors="replace")
    if completed.returncode != 0:
        result = _syntax_error(source, stderr)
        if result is not None:
            return result
        raise FormatterUnavailableError(f"Ruff failed: {stderr.strip() or completed.returncode}")
    if len(completed.stdout) > MAX_FORMAT_OUTPUT_BYTES:
        raise FormatterUnavailableError("Formatted output is too large")
    formatted = completed.stdout.decode("utf-8")
    return FormatResult(
        status="unchanged" if formatted == source else "formatted", source=formatted
    )


def format_source_for_save(source: str) -> str:
    """Return the text a save stores: the formatted source, else ``source`` as given.

    A source that cannot be parsed is stored as written, so the save can report its
    syntax error. A formatter failure is logged and the source is stored as written; the
    saved response returns the stored text, so a caller never sees a different source than
    the one stored.
    """
    try:
        return format_python_source(source).source
    except (FormatterUnavailableError, SourceTooLargeError) as exc:
        logger.warning(f"Saving source without formatting: {exc}")
        return source
