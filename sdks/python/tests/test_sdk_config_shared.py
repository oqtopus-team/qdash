"""Config file cases shared with the TypeScript SDK (sdks/testdata/config_profiles.json).

Both SDKs read the same config.toml; these cases must parse to the same values, or fail with
the same message, in Python and in TypeScript (sdks/typescript/tests/config.test.ts).
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import pytest

from qdash.sdk import QDashConfig, QDashConfigError

CASES: dict[str, Any] = json.loads(
    (Path(__file__).resolve().parents[2] / "testdata" / "config_profiles.json").read_text(
        encoding="utf-8"
    )
)


def _load(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: dict[str, Any]) -> QDashConfig:
    for name in list(os.environ):
        monkeypatch.delenv(name)
    for name, value in case.get("env", {}).items():
        monkeypatch.setenv(name, value)
    path = tmp_path / "config.toml"
    path.write_text(case["toml"], encoding="utf-8")
    return QDashConfig.from_file(case.get("profile"), path)


@pytest.mark.parametrize("case", CASES["valid"], ids=lambda case: case["name"])
def test_shared_valid_profiles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: dict[str, Any]
) -> None:
    config = _load(tmp_path, monkeypatch, case)
    assert config.model_dump() == {**CASES["defaults"], **case["expected"]}


@pytest.mark.parametrize("case", CASES["invalid"], ids=lambda case: case["name"])
def test_shared_invalid_profiles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: dict[str, Any]
) -> None:
    with pytest.raises(QDashConfigError) as excinfo:
        _load(tmp_path, monkeypatch, case)
    message = str(excinfo.value)
    assert re.search(case["error"], message), message
    assert CASES["secret"] not in message
