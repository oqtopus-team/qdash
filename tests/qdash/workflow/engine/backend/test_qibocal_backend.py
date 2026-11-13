"""QibocalBackend runs the isolated runner safely and accepts only emulator results."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from tests.qdash.workflow.qibocal_helpers import (
    REPO_ROOT,
    RUNNER_SCRIPT,
    UPSTREAM_PLATFORMS,
    copy_platforms,
    fake_backend,
)

from qdash.workflow.engine.backend.factory import create_backend
from qdash.workflow.engine.backend.qibocal import (
    QibocalBackend,
    QibocalPlatformRejectedError,
    QibocalRunnerError,
    QibocalRunnerSettings,
    QibocalRunnerTimeoutError,
    RabiAmplitudeRequest,
    hash_tree,
)

REQUEST = RabiAmplitudeRequest(
    qubit=0,
    min_amp=0.01,
    max_amp=0.5,
    step_amp=0.01,
    nshots=1024,
    relaxation_time=0.0,
    seed=1234,
)

# SHA-256 recorded in config/domain/qibocal/UPSTREAM.md for qiboteam/qibocal@52450c17.
UPSTREAM_SHA256 = {
    "platforms/qubit/platform.py": (
        "56922cbe3e2a6adbad0fe83347450e72e70d4795b75a75680f5bd9818598d760"
    ),
    "platforms/qubit/parameters.json": (
        "2bc867f724e731de28931dfc08393a62ea3386c0bdca7a8d6a6a8ad9fb89a645"
    ),
    "platforms/qubit/calibration.json": (
        "6fe0ab6257115217ae0bd399ee9dce17221deaac0f660f6bad0ba8bbdaa38a59"
    ),
    "LICENSE": "c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4",
}


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    # A zombie still answers kill(0); reap it if it is our child.
    try:
        waited, _ = os.waitpid(pid, os.WNOHANG)
    except ChildProcessError:
        # Not our child: an orphan the init process has not reaped yet is a zombie.
        stat = Path(f"/proc/{pid}/stat")
        if stat.exists():
            return stat.read_text().rsplit(")", 1)[-1].split()[0] != "Z"
        state = subprocess.run(  # noqa: S603 - fixed argv
            ["ps", "-o", "stat=", "-p", str(pid)],  # noqa: S607
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        return bool(state) and not state.startswith("Z")
    return waited == 0


def _wait_dead(pid: int, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _alive(pid):
            return True
        time.sleep(0.05)
    return False


class TestUpstreamPlatform:
    def test_platform_files_match_the_recorded_upstream_commit(self) -> None:
        root = UPSTREAM_PLATFORMS.parent
        for relative, expected in UPSTREAM_SHA256.items():
            digest = hashlib.sha256((root / relative).read_bytes()).hexdigest()
            assert digest == expected, f"{relative} differs from qiboteam/qibocal@52450c17"
        assert sorted(hash_tree(UPSTREAM_PLATFORMS / "qubit")) == [
            "calibration.json",
            "parameters.json",
            "platform.py",
        ]

    def test_backend_yaml_only_registers_the_backend_and_its_tasks(self) -> None:
        from qdash.common.config.loader import ConfigLoader

        backends = ConfigLoader._load_yaml(REPO_ROOT / "config/app/backend.yaml")["backends"]
        backend = backends["qibocal"]
        assert set(backend) == {"description", "requires_wiring", "tasks"}
        assert backend["requires_wiring"] is False
        assert backend["tasks"] == {"One Qubit": ["QibocalRabiAmplitude"]}
        # Hardware-scheduled backends keep the default.
        assert "requires_wiring" not in backends["qubex"]
        assert "requires_wiring" not in backends["fake"]


class TestSettings:
    def test_default_settings_point_at_the_runner_and_upstream_platform(self) -> None:
        settings = QibocalRunnerSettings.load()

        assert settings.python == REPO_ROOT / "tools/qibocal-runner/.venv/bin/python"
        assert settings.script == REPO_ROOT / "tools/qibocal-runner/run_rabi_amplitude.py"
        assert settings.platform_dir.resolve() == (UPSTREAM_PLATFORMS / "qubit").resolve()
        assert settings.timeout_seconds == 600

    @pytest.mark.parametrize("name", ["../qubit", "a/b", ".."])
    def test_platform_name_must_be_a_folder_name(self, name: str) -> None:
        with pytest.raises(ValueError, match="folder name"):
            QibocalRunnerSettings.load({"platform": name})

    def test_connect_reports_a_missing_runner_environment(self, tmp_path: Path) -> None:
        backend = QibocalBackend(
            {"runner_python": str(tmp_path / "missing/python"), "calib_data_path": str(tmp_path)}
        )
        with pytest.raises(QibocalRunnerError, match="uv sync --frozen"):
            backend.connect()
        assert not backend.is_connected

    def test_factory_creates_the_backend_without_importing_qibocal(self) -> None:
        backend = create_backend("qibocal", {})

        assert isinstance(backend, QibocalBackend)
        assert "qibocal" not in sys.modules
        assert "qibolab" not in sys.modules


class TestRun:
    def test_successful_run_is_isolated_and_leaves_the_platform_unchanged(
        self, tmp_path: Path
    ) -> None:
        backend = fake_backend(tmp_path)
        source = backend.settings.platform_dir
        before = hash_tree(source)

        run = backend.run_rabi_amplitude(REQUEST, label="QibocalRabiAmplitude_q0")

        assert run.fit["pi_amplitude"] == pytest.approx(0.127)
        assert run.run_dir.parent == tmp_path / "calib" / "qibocal"
        assert run.run_dir.name.startswith("QibocalRabiAmplitude_q0_")
        request = json.loads((run.run_dir / "request.json").read_text())
        assert request["platforms_dir"] == str(run.run_dir / "platforms")
        assert hash_tree(run.run_dir / "platforms" / "qubit") == before
        assert hash_tree(source) == before
        assert run.stdout_path.exists() and run.stderr_path.exists()

    def test_runner_gets_a_minimal_environment_without_a_shell(self, tmp_path: Path) -> None:
        backend = fake_backend(tmp_path)
        calls: list[dict[str, object]] = []
        real_popen = subprocess.Popen

        def spy(*args: object, **kwargs: object) -> subprocess.Popen[bytes]:
            calls.append({"args": args, **kwargs})
            return real_popen(*args, **kwargs)  # type: ignore[call-overload,no-any-return]

        with (
            patch.dict(os.environ, {"QDASH_SECRET_FOR_TEST": "leak"}),
            patch("qdash.workflow.engine.backend.qibocal.subprocess.Popen", spy),
        ):
            run = backend.run_rabi_amplitude(REQUEST, label="env")

        (call,) = calls
        assert call["shell"] is False
        assert call["start_new_session"] is True
        args = call["args"]
        assert isinstance(args, tuple)
        argv = args[0]
        assert isinstance(argv, list)
        assert argv[1] == "-I"
        env = json.loads((run.run_dir / "env.json").read_text())
        assert "QDASH_SECRET_FOR_TEST" not in env
        assert "QIBOLAB_PLATFORMS" not in env  # the runner sets it from the request

    def test_concurrent_runs_never_share_artifacts(self, tmp_path: Path) -> None:
        backend = fake_backend(tmp_path)
        source_hash = hash_tree(backend.settings.platform_dir)
        runs = []
        errors: list[BaseException] = []

        def run(index: int) -> None:
            try:
                runs.append(backend.run_rabi_amplitude(REQUEST, label="parallel"))
            except BaseException as exc:
                errors.append(exc)

        threads = [threading.Thread(target=run, args=(i,)) for i in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert not errors
        run_dirs = {r.run_dir for r in runs}
        assert len(run_dirs) == 4
        for r in runs:
            assert json.loads((r.run_dir / "request.json").read_text())["output_dir"] == str(
                r.run_dir
            )
        assert hash_tree(backend.settings.platform_dir) == source_hash

    def test_runner_rejection_raises_platform_rejected(self, tmp_path: Path) -> None:
        backend = fake_backend(tmp_path, "rejected")
        with pytest.raises(QibocalPlatformRejectedError, match="DummyInstrument"):
            backend.run_rabi_amplitude(REQUEST, label="rejected")

    @pytest.mark.parametrize(
        "controller",
        [
            "dummy=qibolab._core.instruments.dummy.DummyInstrument",
            "qm=qibolab._core.instruments.qm.controller.QmController",
        ],
    )
    def test_result_from_a_non_emulator_controller_is_rejected(
        self, tmp_path: Path, controller: str
    ) -> None:
        backend = fake_backend(tmp_path, overrides={"provenance": {"controllers": [controller]}})
        with pytest.raises(QibocalPlatformRejectedError, match="non-emulator"):
            backend.run_rabi_amplitude(REQUEST, label="controller")

    @pytest.mark.parametrize(
        ("provenance", "message"),
        [
            ({"executor_update": True}, "update=False"),
            ({"synthetic": False}, "synthetic"),
            ({"platform_unchanged": False}, "platform"),
            ({"platform_sha256_after": {"platform.py": "0"}}, "platform"),
        ],
    )
    def test_result_that_breaks_an_invariant_is_rejected(
        self, tmp_path: Path, provenance: dict[str, object], message: str
    ) -> None:
        backend = fake_backend(tmp_path, overrides={"provenance": provenance})
        with pytest.raises(QibocalRunnerError, match=message):
            backend.run_rabi_amplitude(REQUEST, label="invariant")

    def test_runner_crash_reports_stderr(self, tmp_path: Path) -> None:
        backend = fake_backend(tmp_path, "crash")
        with pytest.raises(QibocalRunnerError, match="boom from runner"):
            backend.run_rabi_amplitude(REQUEST, label="crash")

    def test_runner_without_result_fails(self, tmp_path: Path) -> None:
        backend = fake_backend(tmp_path, "no_result")
        with pytest.raises(QibocalRunnerError, match="without a readable result"):
            backend.run_rabi_amplitude(REQUEST, label="none")

    def test_changing_the_configured_platform_fails_the_run(self, tmp_path: Path) -> None:
        platforms = copy_platforms(tmp_path)
        backend = fake_backend(
            tmp_path,
            "touch_original",
            overrides={"original": str(platforms / "qubit")},
            platforms_dir=platforms,
        )
        with pytest.raises(QibocalRunnerError, match="changed during the run"):
            backend.run_rabi_amplitude(REQUEST, label="touch")

    def test_timeout_stops_the_whole_process_group(self, tmp_path: Path) -> None:
        backend = fake_backend(tmp_path, "sleep", timeout_seconds=2, terminate_grace_seconds=1)
        started = time.monotonic()
        with pytest.raises(QibocalRunnerTimeoutError, match="exceeded 2 s"):
            backend.run_rabi_amplitude(REQUEST, label="timeout")
        assert time.monotonic() - started < 20

        (run_dir,) = (tmp_path / "calib" / "qibocal").iterdir()
        assert _wait_dead(int((run_dir / "pid").read_text()))
        assert _wait_dead(int((run_dir / "child_pid").read_text()))

    def test_runner_exits_when_its_parent_is_killed(self, tmp_path: Path) -> None:
        """SIGKILL of the QDash process skips its cleanup; the runner's watchdog stops it."""
        backend = fake_backend(tmp_path, "watchdog", overrides={"runner": str(RUNNER_SCRIPT)})
        config = json.dumps(backend.config)
        request = json.dumps(REQUEST.__dict__)
        parent = subprocess.Popen(  # noqa: S603 - fixed argv
            [
                sys.executable,
                "-c",
                "import json, sys\n"
                "from qdash.workflow.engine.backend.qibocal import QibocalBackend, "
                "RabiAmplitudeRequest\n"
                "backend = QibocalBackend(json.loads(sys.argv[1]))\n"
                "backend.run_rabi_amplitude(RabiAmplitudeRequest(**json.loads(sys.argv[2])), "
                "label='orphan')\n",
                config,
                request,
            ],
        )
        run_root = tmp_path / "calib" / "qibocal"
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and not any(run_root.glob("*/pid")):
            time.sleep(0.05)
        (run_dir,) = run_root.iterdir()
        runner_pid = int((run_dir / "pid").read_text())
        time.sleep(0.5)  # let the runner start its watchdog
        assert _alive(runner_pid)

        parent.kill()
        parent.wait(timeout=10)

        assert _wait_dead(runner_pid, timeout=10)
        # The run's artifacts stay for inspection.
        for name in ("request.json", "runner.stdout.log", "runner.stderr.log", "env.json"):
            assert (run_dir / name).is_file()
        assert (run_dir / "platforms" / "qubit" / "platform.py").is_file()
        assert not (run_dir / "result.json").exists()

    def test_cancellation_stops_the_runner_and_propagates(self, tmp_path: Path) -> None:
        backend = fake_backend(tmp_path, "sleep", terminate_grace_seconds=1)
        real_wait = subprocess.Popen.wait
        cancelled = {"done": False}

        def cancel_once(self: subprocess.Popen[bytes], timeout: float | None = None) -> int:
            if not cancelled["done"]:
                cancelled["done"] = True
                deadline = time.monotonic() + 10
                run_root = tmp_path / "calib" / "qibocal"
                while time.monotonic() < deadline and not any(run_root.glob("*/child_pid")):
                    time.sleep(0.05)
                raise KeyboardInterrupt
            return real_wait(self, timeout=timeout)

        with (
            patch.object(subprocess.Popen, "wait", cancel_once),
            pytest.raises(KeyboardInterrupt),
        ):
            backend.run_rabi_amplitude(REQUEST, label="cancel")

        (run_dir,) = (tmp_path / "calib" / "qibocal").iterdir()
        assert _wait_dead(int((run_dir / "pid").read_text()))
        assert _wait_dead(int((run_dir / "child_pid").read_text()))
