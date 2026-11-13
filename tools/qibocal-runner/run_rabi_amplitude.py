"""Run Qibocal's ``rabi_amplitude`` protocol on a Qibolab emulator platform for QDash.

This script runs inside the isolated environment defined by ``pyproject.toml`` and
``uv.lock`` in this directory. QDash never imports Qibocal or Qibolab; it starts this
script as a subprocess and reads the files it writes.

Usage::

    python -I run_rabi_amplitude.py REQUEST_JSON

The request is a JSON object written by QDash (see ``QibocalBackend``). The script writes
``result.json`` into the request's ``output_dir`` and exits with:

* 0: the protocol ran. ``result.json`` reports whether the fit succeeded.
* 3: the platform was rejected before acquisition (not an emulator).
* 4: the request was invalid, including a qubit the platform does not have.
* 1: any other error. ``result.json`` carries the error when it could be written.

The script never updates the platform: the executor runs with ``update=False``, the
protocol call passes ``update=False``, and the platform files are hashed before and after
the run so that QDash can verify they did not change.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
import os
import platform as host_platform
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any

RESULT_FILE = "result.json"
PROTOCOL = "rabi_amplitude"
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_REJECTED = 3
EXIT_INVALID = 4
DISTRIBUTIONS = (
    "qibo",
    "qibolab",
    "qibocal",
    "numpy",
    "scipy",
    "qutip",
    "dynamiqs",
    "jax",
    "plotly",
)


class RequestError(ValueError):
    """The request cannot be run."""


class PlatformRejected(RuntimeError):
    """The platform does not consist only of Qibolab emulator controllers."""


def _hash_tree(root: Path) -> dict[str, str]:
    """Return the SHA-256 of every regular file below ``root``, keyed by relative path."""
    hashes: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts:
            hashes[path.relative_to(root).as_posix()] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    return hashes


def _versions() -> dict[str, str | None]:
    versions: dict[str, str | None] = {}
    for name in DISTRIBUTIONS:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    versions["python"] = host_platform.python_version()
    return versions


def _finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _validate_request(request: dict[str, Any]) -> dict[str, Any]:
    """Check the sweep before any library import, so a bad request costs nothing."""
    required = (
        "platform",
        "platforms_dir",
        "output_dir",
        "qubit",
        "min_amp",
        "max_amp",
        "step_amp",
        "nshots",
        "relaxation_time",
        "seed",
    )
    missing = [key for key in required if key not in request]
    if missing:
        raise RequestError(f"Request is missing {', '.join(missing)}")
    min_amp = float(request["min_amp"])
    max_amp = float(request["max_amp"])
    step_amp = float(request["step_amp"])
    if not all(math.isfinite(v) for v in (min_amp, max_amp, step_amp)):
        raise RequestError("Amplitude sweep values must be finite")
    # At zero amplitude the binomial error is zero, which makes the weighted fit undefined.
    if min_amp <= 0:
        raise RequestError("min_amp must be greater than 0")
    if max_amp <= min_amp:
        raise RequestError("max_amp must be greater than min_amp")
    if step_amp <= 0 or (max_amp - min_amp) / step_amp < 4:
        raise RequestError("step_amp must be positive and give at least 5 sweep points")
    if int(request["nshots"]) <= 0:
        raise RequestError("nshots must be positive")
    if float(request["relaxation_time"]) < 0:
        raise RequestError("relaxation_time must not be negative")
    pulse_length = request.get("pulse_length")
    if pulse_length is not None and float(pulse_length) <= 0:
        raise RequestError("pulse_length must be positive when given")
    return request


def _check_emulator(platform: Any) -> list[str]:
    """Reject every platform that is not driven only by Qibolab emulator controllers.

    The check uses the instantiated instrument objects, so a platform that names an
    emulator but loads ``DummyInstrument`` or any hardware controller is rejected before
    acquisition. Subclasses are rejected as well: only the upstream class is accepted.
    """
    from qibolab.instruments.emulator import EmulatorController

    instruments = dict(platform.instruments)
    if not instruments:
        raise PlatformRejected("Platform defines no instruments")
    classes = []
    for name, instrument in instruments.items():
        cls = type(instrument)
        qualified = f"{cls.__module__}.{cls.__qualname__}"
        classes.append(f"{name}={qualified}")
        if cls is not EmulatorController:
            raise PlatformRejected(
                f"Instrument '{name}' is {qualified}; only "
                "qibolab EmulatorController platforms are allowed"
            )
    return classes


def _float_pair(value: Any) -> tuple[float | None, float | None]:
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return float(value[0]), float(value[1])
    if value is None:
        return None, None
    return float(value), None


def run(request: dict[str, Any]) -> dict[str, Any]:
    """Run the protocol and return the JSON-serializable result."""
    started = time.time()
    output_dir = Path(request["output_dir"])
    platforms_dir = Path(request["platforms_dir"])
    platform_name = str(request["platform"])
    qubit = request["qubit"]
    platform_dir = platforms_dir / platform_name
    platform_hash_before = _hash_tree(platform_dir)

    # Qibolab resolves platforms only through this variable; point it at the run's copy.
    os.environ["QIBOLAB_PLATFORMS"] = str(platforms_dir)

    import numpy as np

    np.random.seed(int(request["seed"]))

    from qibocal import Executor
    from qibocal.calibration import create_calibration_platform
    from qibocal.protocols.rabi.amplitude import rabi_amplitude

    platform = create_calibration_platform(platform_name)
    controllers = _check_emulator(platform)
    # Only the platform's own qubits exist on the emulator; never map a QDash qubit ID onto
    # another qubit. The upstream `qubit` platform has exactly one qubit, 0.
    if qubit not in platform.qubits:
        raise RequestError(
            f"Qubit {qubit!r} is not on platform '{platform_name}'; "
            f"its qubits are {sorted(platform.qubits)}"
        )

    rx = platform.natives.single_qubit[qubit].RX[0][1]
    rx_before = {"amplitude": float(rx.amplitude), "duration": float(rx.duration)}

    protocol_kwargs: dict[str, Any] = {
        "min_amp": float(request["min_amp"]),
        "max_amp": float(request["max_amp"]),
        "step_amp": float(request["step_amp"]),
        "nshots": int(request["nshots"]),
        "relaxation_time": float(request["relaxation_time"]),
    }
    if request.get("pulse_length") is not None:
        protocol_kwargs["pulse_length"] = float(request["pulse_length"])

    qibocal_dir = output_dir / "qibocal"
    with Executor.open(
        qibocal_dir, targets=[qubit], platform=platform, update=False, force=False
    ) as executor:
        if executor.update is not False:
            raise RuntimeError("Qibocal executor must run with update=False")
        completed = executor.rabi_amplitude(update=False, **protocol_kwargs)
        data = completed.data
        results = completed.results
        rx_after = platform.natives.single_qubit[qubit].RX[0][1]
        rx_after_values = {
            "amplitude": float(rx_after.amplitude),
            "duration": float(rx_after.duration),
        }

    figures, fit_report = rabi_amplitude.report(data=data, fit=results, target=qubit)
    figure_paths = []
    for index, figure in enumerate(figures):
        path = output_dir / f"figure_{index}.json"
        figure.write_json(str(path))
        figure_paths.append(str(path))

    qubit_data = data[qubit]
    amplitude, amplitude_error = _float_pair(results.amplitude.get(qubit))
    chi2, chi2_error = _float_pair(results.chi2.get(qubit))
    length, _ = _float_pair(results.length.get(qubit))
    fitted = results.fitted_parameters.get(qubit)
    fitted_parameters = [float(v) for v in fitted] if fitted is not None else None

    fit_errors = []
    if amplitude is None:
        fit_errors.append("Qibocal fit produced no pi-pulse amplitude")
    else:
        if not (_finite(amplitude) and _finite(amplitude_error)):
            fit_errors.append("Qibocal pi-pulse amplitude or its error is not finite")
        if chi2 is None or not _finite(chi2):
            fit_errors.append("Qibocal reduced chi-squared is missing or not finite")
        if fitted_parameters is None or not all(_finite(v) for v in fitted_parameters):
            fit_errors.append("Qibocal fitted parameters are missing or not finite")

    platform_hash_after = _hash_tree(platform_dir)
    return {
        "status": "ok",
        "protocol": PROTOCOL,
        "qubit": qubit,
        "request": request,
        "fit": {
            "status": "ok" if not fit_errors else "failed",
            "errors": fit_errors,
            "pi_amplitude": amplitude,
            "pi_amplitude_error": amplitude_error,
            "chi2": chi2,
            "chi2_error": chi2_error,
            "pulse_length": length,
            "fitted_parameters": fitted_parameters,
        },
        "data": {
            "amplitude": np.asarray(qubit_data.amp, dtype=float).tolist(),
            "probability": np.asarray(qubit_data.prob, dtype=float).tolist(),
            "error": np.asarray(qubit_data.error, dtype=float).tolist(),
        },
        "figures": figure_paths,
        "fit_report_html": fit_report,
        "provenance": {
            "source": "qibolab-emulator",
            "synthetic": True,
            "controllers": controllers,
            "platform": platform_name,
            "platform_sha256_before": platform_hash_before,
            "platform_sha256_after": platform_hash_after,
            "platform_unchanged": platform_hash_before == platform_hash_after,
            "rx_before": rx_before,
            "rx_after": rx_after_values,
            "executor_update": False,
            "seed": int(request["seed"]),
            "versions": _versions(),
            "qibocal_output_dir": str(qibocal_dir),
            "python_executable": sys.executable,
        },
        "elapsed_seconds": round(time.time() - started, 3),
    }


def _write_result(output_dir: Path, result: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / RESULT_FILE
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(result, indent=1, allow_nan=True), encoding="utf-8")
    tmp.replace(path)


def _exit_with_parent(poll_seconds: float = 1.0) -> None:
    """Exit when the QDash process that started the runner is gone.

    QDash starts the runner in its own session so that it can stop the whole process
    group on timeout or cancellation. If QDash itself is killed without running its
    cleanup, this watchdog keeps the runner from emulating on as an orphan.
    """
    parent = os.getppid()

    def watch() -> None:
        while True:
            time.sleep(poll_seconds)
            if os.getppid() != parent:
                os._exit(EXIT_ERROR)

    threading.Thread(target=watch, name="qdash-parent-watchdog", daemon=True).start()


def main(argv: list[str]) -> int:
    _exit_with_parent()
    if len(argv) != 2:
        print("usage: run_rabi_amplitude.py REQUEST_JSON", file=sys.stderr)
        return EXIT_INVALID
    request_path = Path(argv[1])
    try:
        request = json.loads(request_path.read_text(encoding="utf-8"))
        if not isinstance(request, dict):
            raise RequestError("Request must be a JSON object")
        _validate_request(request)
    except (OSError, ValueError) as exc:
        print(f"Invalid request: {exc}", file=sys.stderr)
        output_dir = request_path.parent
        _write_result(output_dir, {"status": "invalid", "error": str(exc)})
        return EXIT_INVALID

    output_dir = Path(request["output_dir"])
    try:
        result = run(request)
    except PlatformRejected as exc:
        print(f"Platform rejected: {exc}", file=sys.stderr)
        _write_result(output_dir, {"status": "rejected", "error": str(exc)})
        return EXIT_REJECTED
    except RequestError as exc:
        print(f"Invalid request: {exc}", file=sys.stderr)
        _write_result(output_dir, {"status": "invalid", "error": str(exc)})
        return EXIT_INVALID
    except Exception as exc:
        traceback.print_exc()
        _write_result(
            output_dir,
            {"status": "error", "error": f"{type(exc).__name__}: {exc}"},
        )
        return EXIT_ERROR
    _write_result(output_dir, result)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv))
