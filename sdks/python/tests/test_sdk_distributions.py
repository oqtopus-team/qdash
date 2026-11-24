"""qdash-client and qdash-sdk build as separate, independent distributions of one version.

Builds the sdist and wheel of both packages with the release version override the publish
workflow uses, checks their metadata and contents, and installs them into fresh virtual
environments with uv: each alone, both together, and either removed. Skipped when uv is not
on PATH.
"""

from __future__ import annotations

import email
import os
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
UV = shutil.which("uv")

# Versions in the two formats the release pipeline publishes, high enough that no
# qdash-client release on PyPI can satisfy them; only the local wheels can.
STABLE = "41.2.3"
BETA = "41.2.4b17"

pytestmark = pytest.mark.skipif(UV is None, reason="uv is not installed")

CHECK_SDK = """
import importlib.util
import math

from qdash.calibration import CouplingTargets, TwoQubitCalibration, pipeline_spec
from qdash.sdk import (
    CalibrationSession,
    QDash,
    QDashApi,
    QDashConfig,
    RunResult,
    Workflow,
    WorkflowRun,
)
from qdash.sdk.calibration import CustomOneQubit, QubitTargets, TaskCall, sweep
from qdash.sdk.pipeline import Pipeline
from qdash.sdk.types import ExecutionResponseDetail

pairs = pipeline_spec(
    CouplingTargets([("0", "1")]),
    [TwoQubitCalibration(execution_mode="manual", rounds=[[("0", "1")]])],
)
assert pairs["targets"] == {"pairs": [["0", "1"]]}, pairs
assert CalibrationSession.__module__ == "qdash.sdk._calibration_session"

time_range = sweep.logspace(math.log10(300), math.log10(500_000), 51)
spec = Pipeline(
    targets=QubitTargets(["0", "1"]),
    steps=[CustomOneQubit(tasks=[TaskCall(name="CheckT1", run={"time_range": time_range})])],
).to_spec()
assert spec["steps"][0]["type"] == "CustomOneQubit", spec

# Opening a session and reaching its operations sends nothing to the unreachable host.
with QDash(QDashConfig(base_url="http://qdash.invalid", api_token="t")) as session:
    session.workflows
    session.chip("64Qv3")
    assert isinstance(session.api, QDashApi)
    session.api.calibration_pipeline

import qdash
assert getattr(qdash, "__file__", None) is None, qdash.__file__
for name in ("prefect", "qubex", "numpy", "pint", "qdash.api", "qdash.workflow", "qdash.datamodel"):
    assert importlib.util.find_spec(name) is None, name
print("ok")
"""

CHECK_SDK_ONLY = (
    CHECK_SDK.removesuffix('print("ok")\n')
    + """
import sys
assert importlib.util.find_spec("qdash.client") is None
assert not [m for m in sys.modules if m.startswith("qdash.client")]
print("ok")
"""
)

CHECK_CLIENT_ONLY = """
import importlib.util

from qdash.client import QDashClient, QDashConfig

QDashClient(QDashConfig(base_url="http://qdash.invalid", api_token="t")).close()
assert importlib.util.find_spec("qdash.sdk") is None
print("ok")
"""

CHECK_BOTH = CHECK_SDK.removesuffix('print("ok")\n') + CHECK_CLIENT_ONLY.replace(
    'assert importlib.util.find_spec("qdash.sdk") is None', "import qdash.sdk"
)


def build(package: str, version: str, out_dir: Path) -> tuple[Path, Path]:
    """Build the sdist, then the wheel from it, as ``uv build`` does by default."""
    assert UV is not None
    env = {**os.environ, "SETUPTOOLS_SCM_PRETEND_VERSION": version}
    subprocess.run(  # noqa: S603
        [UV, "build", "--package", package, "--out-dir", str(out_dir)],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        env=env,
    )
    stem = f"{package.replace('-', '_')}-{version}"
    return out_dir / f"{stem}.tar.gz", out_dir / f"{stem}-py3-none-any.whl"


@pytest.fixture(scope="module")
def dists(tmp_path_factory: pytest.TempPathFactory) -> dict[tuple[str, str], tuple[Path, Path]]:
    out_dir = tmp_path_factory.mktemp("dist")
    return {
        (package, version): build(package, version, out_dir)
        for package in ("qdash-client", "qdash-sdk")
        for version in (STABLE, BETA)
    }


def wheel_metadata(wheel: Path) -> email.message.Message:
    with zipfile.ZipFile(wheel) as archive:
        (name,) = [n for n in archive.namelist() if n.endswith(".dist-info/METADATA")]
        return email.message_from_bytes(archive.read(name))


def sdist_metadata(sdist: Path) -> email.message.Message:
    with tarfile.open(sdist) as archive:
        (member,) = [
            m
            for m in archive.getmembers()
            if m.name.count("/") == 1 and m.name.endswith("/PKG-INFO")
        ]
        data = archive.extractfile(member)
        assert data is not None
        return email.message_from_bytes(data.read())


def package_files(wheel: Path) -> set[str]:
    return {n for n in zipfile.ZipFile(wheel).namelist() if ".dist-info/" not in n}


@pytest.mark.parametrize("version", [STABLE, BETA])
def test_both_packages_carry_the_version_and_the_sdk_needs_no_client(dists, version: str) -> None:
    sdist, wheel = dists["qdash-sdk", version]

    for metadata in (wheel_metadata(wheel), sdist_metadata(sdist)):
        assert metadata["Name"] == "qdash-sdk"
        assert metadata["Version"] == version
        requirements = metadata.get_all("Requires-Dist") or []
        assert sorted(r.split(">=")[0] for r in requirements) == [
            "httpx",
            "pydantic",
            "typing-extensions",
        ]
    client = wheel_metadata(dists["qdash-client", version][1])
    assert client["Version"] == version
    assert not any("qdash-sdk" in r for r in client.get_all("Requires-Dist") or [])


def test_each_wheel_ships_only_its_own_namespace(dists) -> None:
    client = package_files(dists["qdash-client", STABLE][1])
    sdk = package_files(dists["qdash-sdk", STABLE][1])

    assert "qdash/client/__init__.py" in client
    assert "qdash/client/py.typed" in client
    assert {
        "qdash/sdk/__init__.py",
        "qdash/sdk/py.typed",
        "qdash/sdk/_generated/__init__.py",
        "qdash/sdk/_generated/client.py",
        "qdash/sdk/_generated/_authoring.py",
        "qdash/calibration/__init__.py",
        "qdash/calibration/py.typed",
        "qdash/calibration/sweep.py",
    } <= sdk
    assert all(n.startswith("qdash/client/") for n in client), client
    # qdash.calibration, the definitions the worker shares, ships with the SDK.
    assert all(n.startswith(("qdash/sdk/", "qdash/calibration/")) for n in sdk), sdk
    assert not client & sdk


def test_the_sdk_sdist_carries_its_sources_and_generation_config(dists) -> None:
    sdist, _ = dists["qdash-sdk", STABLE]
    with tarfile.open(sdist) as archive:
        names = {
            member.name.split("/", 1)[1] for member in archive.getmembers() if "/" in member.name
        }

    assert {"fern/generators.yml", "fern/fern.config.json", "pyproject.toml"} <= names
    assert "src/qdash/sdk/_generated/_authoring.py" in names
    assert "src/qdash/calibration/steps.py" in names
    assert not [n for n in names if n.startswith("src/qdash/") and n.count("/") == 2]
    assert "src/qdash/__init__.py" not in names


def venv_python(tmp_path: Path) -> Path:
    assert UV is not None
    venv = tmp_path / "venv"
    subprocess.run(  # noqa: S603
        [UV, "venv", "--python", sys.executable, str(venv)], check=True, capture_output=True
    )
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def uv_pip(python: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    assert UV is not None
    return subprocess.run(  # noqa: S603
        [UV, "pip", *args, "--python", str(python)],
        capture_output=True,
        text=True,
        check=check,
    )


def run_check(python: Path, script: str, cwd: Path) -> None:
    # -I keeps the repository's sources off sys.path; only installed packages are importable.
    result = subprocess.run(  # noqa: S603
        [str(python), "-I", "-c", script], cwd=cwd, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "ok"


def installed_files(python: Path, distribution: str) -> set[str]:
    script = (
        "import importlib.metadata as m, sys\n"
        "print('\\n'.join(str(f) for f in m.files(sys.argv[1]) if '.dist-info' not in str(f)))"
    )
    result = subprocess.run(  # noqa: S603
        [str(python), "-I", "-c", script, distribution], capture_output=True, text=True, check=True
    )
    return set(result.stdout.split())


@pytest.mark.parametrize("artifact", [0, 1], ids=["sdist", "wheel"])
def test_the_sdk_installs_alone(dists, artifact: int, tmp_path: Path) -> None:
    python = venv_python(tmp_path)
    uv_pip(python, "install", str(dists["qdash-sdk", STABLE][artifact]))

    assert f"Version: {STABLE}" in uv_pip(python, "show", "qdash-sdk").stdout
    assert "qdash-client" not in uv_pip(python, "freeze").stdout
    run_check(python, CHECK_SDK_ONLY, tmp_path)


def test_client_installs_without_the_sdk(dists, tmp_path: Path) -> None:
    python = venv_python(tmp_path)
    uv_pip(python, "install", str(dists["qdash-client", STABLE][1]))

    assert "qdash-sdk" not in uv_pip(python, "freeze").stdout
    run_check(python, CHECK_CLIENT_ONLY, tmp_path)


@pytest.mark.parametrize("version", [STABLE, BETA])
def test_both_install_side_by_side_and_either_can_be_removed(
    dists, version: str, tmp_path: Path
) -> None:
    python = venv_python(tmp_path)
    client, sdk = dists["qdash-client", version][1], dists["qdash-sdk", version][1]
    uv_pip(python, "install", str(client), str(sdk))

    run_check(python, CHECK_BOTH, tmp_path)
    assert not installed_files(python, "qdash-client") & installed_files(python, "qdash-sdk")

    uv_pip(python, "uninstall", "qdash-client")
    run_check(python, CHECK_SDK_ONLY, tmp_path)

    uv_pip(python, "install", str(client))
    uv_pip(python, "uninstall", "qdash-sdk")
    run_check(python, CHECK_CLIENT_ONLY, tmp_path)


def test_an_sdk_of_another_version_coexists_with_the_client(dists, tmp_path: Path) -> None:
    python = venv_python(tmp_path)
    uv_pip(
        python, "install", str(dists["qdash-sdk", STABLE][1]), str(dists["qdash-client", BETA][1])
    )

    run_check(python, CHECK_BOTH, tmp_path)
