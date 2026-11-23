"""Keep the workflow editor's Execution help media in step with the docs GIFs.

``docs/demos/one_qubit_execution_modes.py`` and ``docs/demos/two_qubit_cr_schedule.py`` write
each GIF to ``docs/public/images/guides/`` and a byte-identical copy plus a still poster to
``ui/public/images/execution-help/``. A hand edit or a partial regeneration breaks the copy.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_DOCS = _ROOT / "docs" / "public" / "images" / "guides"
_UI = _ROOT / "ui" / "public" / "images" / "execution-help"
_NAMES = ("one-qubit-execution-modes", "two-qubit-cr-schedule")
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


@pytest.mark.parametrize("name", _NAMES)
def test_ui_gif_matches_docs_gif(name: str) -> None:
    assert (_UI / f"{name}.gif").read_bytes() == (_DOCS / f"{name}.gif").read_bytes()


@pytest.mark.parametrize("name", _NAMES)
def test_ui_poster_is_png(name: str) -> None:
    assert (_UI / f"{name}-poster.png").read_bytes().startswith(_PNG_SIGNATURE)


def test_ui_help_dir_holds_only_generated_assets() -> None:
    expected = {f"{name}{suffix}" for name in _NAMES for suffix in (".gif", "-poster.png")}
    assert {path.name for path in _UI.iterdir()} == expected
