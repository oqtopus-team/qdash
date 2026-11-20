"""The qdash-client wheel installs qdash.client and qdash.sdk alone, without server packages.

Builds the wheel, installs it into a fresh virtual environment with uv, and imports both
namespaces there. Skipped when uv is not on PATH.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

PACKAGE_DIR = Path(__file__).resolve().parents[1]
UV = shutil.which("uv")

CHECK_SCRIPT = """
import importlib.util
import math
import sys

from qdash.client import QDashClient
from qdash.sdk import QDash
from qdash.sdk.pipeline import CustomOneQubit, Pipeline, Qubits, TaskCall, sweep

time_range = sweep.logspace(math.log10(300), math.log10(500_000), 51)
spec = Pipeline(
    targets=Qubits(["0", "1"]),
    steps=[CustomOneQubit(tasks=[TaskCall(name="CheckT1", run={"time_range": time_range})])],
).to_spec()
assert spec["steps"][0]["type"] == "CustomOneQubit", spec

import qdash
assert not hasattr(qdash, "__file__") or qdash.__file__ is None, qdash.__file__
for name in ("prefect", "qubex", "numpy", "pint", "qdash.api", "qdash.workflow", "qdash.datamodel"):
    assert importlib.util.find_spec(name) is None, name
print("ok")
"""


@pytest.fixture(scope="module")
def wheel(tmp_path_factory: pytest.TempPathFactory) -> Path:
    assert UV is not None
    out_dir = tmp_path_factory.mktemp("dist")
    env = {**os.environ, "SETUPTOOLS_SCM_PRETEND_VERSION": "0.0.0"}
    subprocess.run(  # noqa: S603
        [UV, "build", "--wheel", "--out-dir", str(out_dir), str(PACKAGE_DIR)],
        check=True,
        capture_output=True,
        env=env,
    )
    (built,) = out_dir.glob("qdash_client-*.whl")
    return built


@pytest.mark.skipif(UV is None, reason="uv is not installed")
def test_wheel_keeps_qdash_a_namespace_package(wheel: Path) -> None:
    names = zipfile.ZipFile(wheel).namelist()

    assert "qdash/__init__.py" not in names
    assert "qdash/client/__init__.py" in names
    assert "qdash/sdk/__init__.py" in names
    assert "qdash/sdk/py.typed" in names


@pytest.mark.skipif(UV is None, reason="uv is not installed")
def test_wheel_imports_client_and_sdk_without_server_packages(wheel: Path, tmp_path: Path) -> None:
    assert UV is not None
    venv = tmp_path / "venv"
    subprocess.run(  # noqa: S603
        [UV, "venv", "--python", sys.executable, str(venv)], check=True, capture_output=True
    )
    python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    subprocess.run(  # noqa: S603
        [UV, "pip", "install", "--python", str(python), str(wheel)],
        check=True,
        capture_output=True,
    )
    # -I keeps the repository's sources off sys.path; only the installed wheel is importable.
    result = subprocess.run(  # noqa: S603
        [str(python), "-I", "-c", CHECK_SCRIPT],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "ok"
