"""Load a native Quantum Machines configuration file (``configuration.py``).

Quantum Machines describes a QUA configuration as a Python dictionary, conventionally
exported as ``config`` by a ``configuration.py`` module and passed to
``QuantumMachinesManager.open_qm(config)``. QDash reads that same file unchanged, so a
lab's existing configuration works with the ``qm`` and ``qm-fake`` backends and stays
usable without QDash (``from configuration import config``).

The file is trusted, operator-managed Python: loading it executes it with the rights of
the workflow worker. QDash loads it only in the worker, when a ``qm`` or ``qm-fake``
backend reads its settings; the API never imports it. This is not a sandbox.

The loader keeps the module out of the interpreter's global state:

- The module runs under a private name, so ``if __name__ == "__main__":`` blocks (for
  example a script that opens a machine or simulates a program) do not run.
- The file's directory is on ``sys.path`` only while the file executes, so it can import
  helper modules next to it (``from helpers import ...``). Modules imported from that
  directory are removed from ``sys.modules`` afterwards, and modules of the same name
  loaded from elsewhere are hidden during the load and restored after it, so the helper
  modules of two chips never shadow each other.
- Loads are serialized, since ``sys.path`` and ``sys.modules`` are process-wide.

Local helper names temporarily shadow cached packages and their descendants; give
helpers distinct names to avoid collisions with installed packages.
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import itertools
import sys
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from types import ModuleType

CONFIGURATION_EXPORT = "config"
_LOAD_LOCK = threading.Lock()
_LOAD_COUNTER = itertools.count(1)


class QMConfigurationLoadError(ValueError):
    """Raised when a native QM configuration file cannot be loaded."""


def load_qm_configuration(path: Path) -> dict[str, Any]:
    """Execute the trusted ``configuration.py`` at ``path`` and return its ``config`` dict.

    The dictionary is returned as the module built it: integer keys, tuples, NumPy
    arrays and computed waveforms are kept, with no conversion.
    """
    if path.suffix != ".py":
        raise QMConfigurationLoadError(
            f"QM configuration must be a Python file that defines '{CONFIGURATION_EXPORT}' "
            f"(configuration.py), got: {path}"
        )
    if not path.is_file():
        raise QMConfigurationLoadError(f"QM configuration file not found: {path}")
    path = path.resolve()
    with _LOAD_LOCK:
        module = _execute(path)
    if not hasattr(module, CONFIGURATION_EXPORT):
        raise QMConfigurationLoadError(
            f"QM configuration {path} does not define a module-level "
            f"'{CONFIGURATION_EXPORT}' dictionary"
        )
    config = getattr(module, CONFIGURATION_EXPORT)
    if not isinstance(config, dict):
        raise QMConfigurationLoadError(
            f"'{CONFIGURATION_EXPORT}' in {path} must be a dict, got {type(config).__name__}"
        )
    return config


def _execute(path: Path) -> ModuleType:
    directory = path.parent
    digest = hashlib.sha256(str(path).encode()).hexdigest()[:12]
    module_name = f"_qdash_qm_configuration_{digest}_{next(_LOAD_COUNTER)}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise QMConfigurationLoadError(f"Cannot load QM configuration {path}")
    module = importlib.util.module_from_spec(spec)

    local_names = _local_module_names(directory)
    hidden = {
        name: sys.modules.pop(name)
        for name in list(sys.modules)
        if name.partition(".")[0] in local_names
    }
    before = set(sys.modules)
    sys.path.insert(0, str(directory))
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise QMConfigurationLoadError(
            f"Failed to execute QM configuration {path}: {type(exc).__name__}: {exc}"
        ) from exc
    finally:
        sys.modules.pop(module_name, None)
        _remove_path_entry(str(directory))
        for name in set(sys.modules) - before:
            if _is_inside(sys.modules[name], directory):
                del sys.modules[name]
        sys.modules.update(hidden)
    return module


def _local_module_names(directory: Path) -> set[str]:
    """Top-level module names that ``import`` would find in ``directory``."""
    names = {child.stem for child in directory.glob("*.py")}
    names.update(child.name for child in directory.iterdir() if (child / "__init__.py").is_file())
    return names


def _remove_path_entry(entry: str) -> None:
    with contextlib.suppress(ValueError):
        sys.path.remove(entry)


def _is_inside(module: ModuleType | None, directory: Path) -> bool:
    origin = getattr(module, "__file__", None)
    if not origin:
        return False
    try:
        return Path(origin).resolve().is_relative_to(directory)
    except OSError:
        return False
