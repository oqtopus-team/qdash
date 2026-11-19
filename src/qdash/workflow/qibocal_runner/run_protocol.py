"""Run allowlisted official Qibocal protocols on a Qibolab emulator for QDash.

This script runs inside the isolated environment defined by ``pyproject.toml`` and
``uv.lock`` in this directory. QDash never imports Qibocal or Qibolab; it starts this
script as a subprocess and reads the files it writes.

Usage::

    python -I run_protocol.py REQUEST_JSON

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
PROTOCOL_PARAMETERS = {
    "rabi_amplitude": {"min_amp", "max_amp", "step_amp", "nshots", "relaxation_time"},
    "flipping": {"nflips_max", "nflips_step", "delta_amplitude", "nshots", "relaxation_time"},
}
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
        except importlib.metadata.PackageNotFoundError:  # noqa: PERF203 - report optional metadata
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
        "seed",
        "protocol",
        "parameters",
        "calibration",
        "targets",
    )
    missing = [key for key in required if key not in request]
    if missing:
        raise RequestError(f"Request is missing {', '.join(missing)}")
    if request.get("protocol") not in PROTOCOL_PARAMETERS:
        raise RequestError("Protocol is not allowed")
    if request.get("targets") != [request["qubit"]]:
        raise RequestError("Exactly one matching target is required")
    if not isinstance(request.get("calibration"), dict):
        raise RequestError("Calibration values are required")
    parameters = request["parameters"]
    if (
        not isinstance(parameters, dict)
        or set(parameters) != PROTOCOL_PARAMETERS[request["protocol"]]
    ):
        raise RequestError("Protocol parameters must match the allowlist")
    if not all(
        isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
        for value in parameters.values()
    ):
        raise RequestError("Protocol parameters must be finite numbers")
    if parameters["nshots"] <= 0 or parameters["relaxation_time"] < 0:
        raise RequestError("Invalid shots or relaxation time")
    if request["protocol"] == "rabi_amplitude":
        if not 0 < parameters["min_amp"] < parameters["max_amp"] <= 1:
            raise RequestError("Rabi amplitudes must satisfy 0 < min < max <= 1")
        if (
            parameters["step_amp"] <= 0
            or (parameters["max_amp"] - parameters["min_amp"]) / parameters["step_amp"] < 4
        ):
            raise RequestError("Rabi requires at least five points")
    else:
        if (
            parameters["nflips_step"] <= 0
            or parameters["nflips_max"] / parameters["nflips_step"] < 6
        ):
            raise RequestError("Flipping requires at least six points")
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
    from qibocal.protocols.flipping import flipping
    from qibocal.protocols.rabi.amplitude import rabi_amplitude

    protocol_name = request["protocol"]
    protocol = {"rabi_amplitude": rabi_amplitude, "flipping": flipping}[protocol_name]

    platform = create_calibration_platform(platform_name)
    controllers = _check_emulator(platform)
    # Only the platform's own qubits exist on the emulator; never map a QDash qubit ID onto
    # another qubit. The upstream `qubit` platform has exactly one qubit, 0.
    if qubit not in platform.qubits:
        raise RequestError(
            f"Qubit {qubit!r} is not on platform '{platform_name}'; "
            f"its qubits are {sorted(platform.qubits)}"
        )

    # Load the dependency-free shared mapping explicitly: -I excludes the project path.
    import importlib.util

    mapping_path = Path(__file__).resolve().parents[2] / "common" / "qibocal_platform.py"
    spec = importlib.util.spec_from_file_location("qdash_qibocal_mapping", mapping_path)
    mapping = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mapping
    spec.loader.exec_module(mapping)
    assignments = mapping.native_assignments(qubit, request["calibration"])
    platform.update({entry["path"]: entry["value"] for entry in assignments})
    applied = platform.parameters.model_dump(mode="json")
    mismatches = mapping.readback_mismatches(applied, assignments)
    if mismatches:
        raise RequestError("Calibration readback mismatch: " + "; ".join(mismatches))

    rx = platform.natives.single_qubit[qubit].RX[0][1]
    rx_before = {"amplitude": float(rx.amplitude), "duration": float(rx.duration)}

    protocol_kwargs = dict(request["parameters"])

    qibocal_dir = output_dir / "qibocal"
    with Executor.open(
        qibocal_dir, targets=[qubit], platform=platform, update=False, force=False
    ) as executor:
        if executor.update is not False:
            raise RuntimeError("Qibocal executor must run with update=False")
        completed = getattr(executor, protocol_name)(update=False, **protocol_kwargs)
        data = completed.data
        results = completed.results
        rx_after = platform.natives.single_qubit[qubit].RX[0][1]
        rx_after_values = {
            "amplitude": float(rx_after.amplitude),
            "duration": float(rx_after.duration),
        }

    figures, fit_report = protocol.report(
        data=data, fit=results if qubit in results.fitted_parameters else None, target=qubit
    )
    figure_paths = []
    for index, figure in enumerate(figures):
        path = output_dir / f"figure_{index}.json"
        figure.write_json(str(path))
        figure_paths.append(str(path))

    qubit_data = data[qubit]
    amplitude, amplitude_error = _float_pair(results.amplitude.get(qubit))
    chi2, chi2_error = _float_pair(results.chi2.get(qubit))
    length = float(rx_before["duration"])
    fitted = results.fitted_parameters.get(qubit)
    fitted_parameters = [float(v) for v in fitted] if fitted is not None else None

    fit_errors = []
    if amplitude is None:
        fit_errors.append("Qibocal fit produced no pi-pulse amplitude")
    else:
        if not (_finite(amplitude) and _finite(amplitude_error)):
            fit_errors.append("Qibocal pi-pulse amplitude or its error is not finite")
        if chi2 is None or not _finite(chi2) or not _finite(chi2_error):
            fit_errors.append("Qibocal reduced chi-squared is missing or not finite")
        if fitted_parameters is None or not all(_finite(v) for v in fitted_parameters):
            fit_errors.append("Qibocal fitted parameters are missing or not finite")

    platform_hash_after = _hash_tree(platform_dir)
    return {
        "status": "ok",
        "protocol": protocol_name,
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
            "amplitude": np.asarray(
                qubit_data.amp if protocol_name == "rabi_amplitude" else qubit_data.flips,
                dtype=float,
            ).tolist(),
            "probability": np.asarray(qubit_data.prob, dtype=float).tolist(),
            "error": np.asarray(qubit_data.error, dtype=float).tolist(),
        },
        "figures": figure_paths,
        "fit_report_html": fit_report,
        "provenance": {
            "source": "qibolab-emulator",
            "applied_parameters": applied,
            "calibration": request["calibration"],
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
        print("usage: run_protocol.py REQUEST_JSON", file=sys.stderr)
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
