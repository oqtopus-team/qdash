"""Native ``configuration.py`` files against the real pinned ``qm-qua`` SDK.

The configuration is imported the way a Quantum Machines script imports it
(``from configuration import config``) and through the QDash loader; the SDK must
accept both, and the qm-fake backend must run QMAmplitudeRabi from settings files that
point at the native file. Everything runs offline: outgoing sockets are blocked and no
QOP server is involved. Skipped without the workflow ``qm`` extra.
"""

from __future__ import annotations

import socket
import sys
from typing import TYPE_CHECKING, Any

import numpy as np
import pytest

qm = pytest.importorskip("qm")
pytest.importorskip("qualang_tools.addons.calibration.calibrations")

from qdash.workflow.calibtasks.qm.qm_amplitude_rabi import QMAmplitudeRabi  # noqa: E402
from qdash.workflow.engine.backend.factory import create_backend  # noqa: E402
from qdash.workflow.engine.backend.qm import load_qm_settings  # noqa: E402
from qdash.workflow.engine.backend.qm_configuration import load_qm_configuration  # noqa: E402
from qdash.workflow.engine.backend.qm_fake import (  # noqa: E402
    QMFakeBackend,
    load_qm_fake_settings,
)
from qdash.workflow.engine.backend.qm_fake_qop import QMFakeQuantumMachinesManager  # noqa: E402
from tests.qdash.workflow.qm_helpers import (  # noqa: E402
    EXAMPLE_CONFIGURATION_PATH,
    EXAMPLE_FAKE_SETTINGS_PATH,
    EXAMPLE_SETTINGS_PATH,
)

if TYPE_CHECKING:
    from pathlib import Path

CHIP_ID = "native-chip"
DRIVE_LENGTH = 40
DRIVE_AMPLITUDE = 0.2
PI_SCALE = 0.6

PULSES_MODULE = """
import numpy as np


def gaussian(amplitude, length, sigma):
    t = np.arange(length) - (length - 1) / 2
    return amplitude * np.exp(-0.5 * (t / sigma) ** 2)
"""


@pytest.fixture(autouse=True)
def offline(monkeypatch: pytest.MonkeyPatch) -> None:
    def no_network(*_: Any, **__: Any) -> Any:
        raise AssertionError("native configuration tests must not open network connections")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)


def _import_directly(path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    monkeypatch.syspath_prepend(str(path.parent))
    for name in ("configuration", "pulses"):
        monkeypatch.delitem(sys.modules, name, raising=False)
    try:
        from configuration import config
    finally:
        for name in ("configuration", "pulses"):
            sys.modules.pop(name, None)
    return config  # type: ignore[no-any-return]


def _gaussian_area() -> float:
    t = np.arange(DRIVE_LENGTH) - (DRIVE_LENGTH - 1) / 2
    return float(np.sum(DRIVE_AMPLITUDE * np.exp(-0.5 * (t / 8) ** 2)))


def _lab_tree(root: Path) -> Path:
    """Write a native configuration with a computed drive pulse and QDash settings for it.

    Returns the path of ``qm-fake.yaml``.
    """
    native = root / "qm-config" / CHIP_ID
    native.mkdir(parents=True)
    (native / "pulses.py").write_text(PULSES_MODULE, encoding="utf-8")
    source = EXAMPLE_CONFIGURATION_PATH.read_text(encoding="utf-8")
    constant = '"x180_wf": {"type": "constant", "sample": x180_amp},'
    assert constant in source
    source = "from pulses import gaussian\n" + source.replace(
        constant,
        '"x180_wf": {"type": "arbitrary", "samples": gaussian(x180_amp, x180_len, 8)},',
    )
    (native / "configuration.py").write_text(source, encoding="utf-8")

    settings = root / "qm-backend" / CHIP_ID
    settings.mkdir(parents=True)
    (settings / "qm.yaml").write_text(
        EXAMPLE_SETTINGS_PATH.read_text(encoding="utf-8").replace(
            "qm-config/example/", f"qm-config/{CHIP_ID}/"
        ),
        encoding="utf-8",
    )
    fake = EXAMPLE_FAKE_SETTINGS_PATH.read_text(encoding="utf-8").replace(
        "pi_pulse_area: 4.8", f"pi_pulse_area: {PI_SCALE * _gaussian_area()!r}"
    )
    (settings / "qm-fake.yaml").write_text(fake, encoding="utf-8")
    return settings / "qm-fake.yaml"


def test_example_configuration_is_accepted_by_the_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    imported = _import_directly(EXAMPLE_CONFIGURATION_PATH, monkeypatch)
    loaded = load_qm_configuration(EXAMPLE_CONFIGURATION_PATH)
    manager = QMFakeQuantumMachinesManager(load_qm_fake_settings(EXAMPLE_FAKE_SETTINGS_PATH))

    assert loaded == imported
    # open_qm validates the dictionary with the SDK's load_config.
    for config in (imported, loaded):
        manager.open_qm(config)


def test_computed_configuration_is_accepted_directly_and_through_the_loader(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_path = _lab_tree(tmp_path)
    native_path = tmp_path / "qm-config" / CHIP_ID / "configuration.py"
    imported = _import_directly(native_path, monkeypatch)
    settings = load_qm_fake_settings(fake_path)
    manager = QMFakeQuantumMachinesManager(settings)

    samples = settings.qua_config["waveforms"]["x180_wf"]["samples"]
    assert isinstance(samples, np.ndarray)
    np.testing.assert_array_equal(samples, imported["waveforms"]["x180_wf"]["samples"])
    assert settings.qua_config["elements"]["qubit"]["mixInputs"]["I"] == ("con1", 1)
    for config in (imported, settings.qua_config):
        machine = manager.open_qm(config)
        assert machine.config_view.envelope_area("qubit", "x180") == pytest.approx(_gaussian_area())


def test_qm_and_qm_fake_read_the_same_native_configuration(tmp_path: Path) -> None:
    fake_path = _lab_tree(tmp_path)

    hardware = load_qm_settings(fake_path.parent / "qm.yaml")
    fake = load_qm_fake_settings(fake_path)

    assert hardware.qubits == fake.qubits
    assert hardware.qua_config.keys() == fake.qua_config.keys()
    np.testing.assert_array_equal(
        hardware.qua_config["waveforms"]["x180_wf"]["samples"],
        fake.qua_config["waveforms"]["x180_wf"]["samples"],
    )


def test_qm_fake_runs_the_rabi_task_from_a_native_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_path = _lab_tree(tmp_path)
    backend = create_backend("qm-fake", {"qm_fake_settings_path": str(fake_path)})
    assert isinstance(backend, QMFakeBackend)
    opened: list[dict[str, Any]] = []
    open_qm = QMFakeQuantumMachinesManager.open_qm

    def spy(self: Any, config: dict[str, Any], *args: Any, **kwargs: Any) -> Any:
        opened.append(config)
        return open_qm(self, config, *args, **kwargs)

    monkeypatch.setattr(QMFakeQuantumMachinesManager, "open_qm", spy)

    result = QMAmplitudeRabi().run(backend, "0")

    # run_rabi handed the loaded dictionary itself to open_qm, without conversion.
    assert [id(config) for config in opened] == [id(backend.settings.qua_config)]
    assert result.raw_result["fit"].pi_amplitude_scale == pytest.approx(PI_SCALE, rel=0.02)
    assert "pulses" not in sys.modules
