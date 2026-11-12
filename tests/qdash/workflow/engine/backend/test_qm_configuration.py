"""Loading native Quantum Machines ``configuration.py`` files.

These tests need no QM package: they check that the loader returns the ``config``
dictionary the module built, unchanged, and leaves no trace in ``sys.path`` or
``sys.modules``. SDK acceptance of the loaded dictionaries is checked in
``tests/qdash/workflow/calibtasks/qm/test_qm_native_config_sdk.py``.
"""

from __future__ import annotations

import sys
import textwrap
from types import ModuleType
from typing import TYPE_CHECKING, Any

import numpy as np
import pytest
from tests.qdash.workflow.qm_helpers import EXAMPLE_CONFIGURATION_PATH, EXAMPLE_SETTINGS_PATH

from qdash.workflow.engine.backend.qm import QMConfigurationError, load_qm_settings
from qdash.workflow.engine.backend.qm_configuration import (
    QMConfigurationLoadError,
    load_qm_configuration,
)

if TYPE_CHECKING:
    from pathlib import Path


def _write(path: Path, source: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(source), encoding="utf-8")
    return path


def _import_directly(path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Import ``configuration`` the way a QM script does: ``from configuration import config``."""
    monkeypatch.syspath_prepend(str(path.parent))
    monkeypatch.delitem(sys.modules, "configuration", raising=False)
    try:
        from configuration import config
    finally:
        sys.modules.pop("configuration", None)
    assert isinstance(config, dict)
    return config


class TestExample:
    def test_loader_returns_what_a_direct_import_returns(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        loaded = load_qm_configuration(EXAMPLE_CONFIGURATION_PATH)
        imported = _import_directly(EXAMPLE_CONFIGURATION_PATH, monkeypatch)

        assert loaded == imported
        assert loaded is not imported

    def test_native_key_and_value_types_are_kept(self) -> None:
        config = load_qm_configuration(EXAMPLE_CONFIGURATION_PATH)

        assert list(config["controllers"]["con1"]["analog_outputs"]) == [1, 2, 3, 4]
        assert config["elements"]["qubit"]["mixInputs"]["I"] == ("con1", 1)
        assert config["integration_weights"]["cosine_weights"]["cosine"] == [(1.0, 200)]

    def test_settings_hold_the_dictionary_unchanged(self) -> None:
        settings = load_qm_settings(EXAMPLE_SETTINGS_PATH)

        assert settings.qua_config == load_qm_configuration(EXAMPLE_CONFIGURATION_PATH)
        assert settings.qua_config["elements"]["resonator"]["outputs"]["out1"] == ("con1", 1)


class TestComputedValues:
    def test_numpy_waveforms_tuples_and_int_keys_are_not_converted(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path / "configuration.py",
            """
            import numpy as np

            length = 16
            samples = 0.2 * np.exp(-0.5 * ((np.arange(length) - length / 2) / 4) ** 2)
            config = {
                "controllers": {"con1": {"analog_outputs": {1: {"offset": 0.0}}}},
                "waveforms": {"gauss_wf": {"type": "arbitrary", "samples": samples}},
                "elements": {"q": {"singleInput": {"port": ("con1", 1)}}},
            }
            """,
        )

        config = load_qm_configuration(path)

        samples = config["waveforms"]["gauss_wf"]["samples"]
        assert isinstance(samples, np.ndarray)
        assert samples.shape == (16,)
        assert samples.max() == pytest.approx(0.2)
        assert config["elements"]["q"]["singleInput"]["port"] == ("con1", 1)
        assert 1 in config["controllers"]["con1"]["analog_outputs"]


class TestErrors:
    def test_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(QMConfigurationLoadError, match="not found"):
            load_qm_configuration(tmp_path / "configuration.py")

    @pytest.mark.parametrize("name", ["config.yaml", "config.json", "configuration"])
    def test_non_python_file(self, tmp_path: Path, name: str) -> None:
        path = tmp_path / name
        path.write_text("{}", encoding="utf-8")

        with pytest.raises(QMConfigurationLoadError, match="must be a Python file"):
            load_qm_configuration(path)

    def test_missing_export(self, tmp_path: Path) -> None:
        path = _write(tmp_path / "configuration.py", "qua_config = {}\n")

        with pytest.raises(
            QMConfigurationLoadError, match="does not define a module-level 'config'"
        ):
            load_qm_configuration(path)

    @pytest.mark.parametrize("value", ["[('elements', {})]", "None", "'config.yaml'"])
    def test_export_must_be_a_dict(self, tmp_path: Path, value: str) -> None:
        path = _write(tmp_path / "configuration.py", f"config = {value}\n")

        with pytest.raises(QMConfigurationLoadError, match=r"'config' in .* must be a dict"):
            load_qm_configuration(path)

    @pytest.mark.parametrize(
        ("source", "error"),
        [
            ("config = {\n", "SyntaxError"),
            ("raise RuntimeError('broken lab file')\n", "RuntimeError: broken lab file"),
            ("from not_a_module_qdash_test import x\nconfig = {}\n", "ModuleNotFoundError"),
        ],
    )
    def test_failing_module(self, tmp_path: Path, source: str, error: str) -> None:
        path = _write(tmp_path / "configuration.py", source)

        with pytest.raises(QMConfigurationLoadError, match=f"Failed to execute .*{error}"):
            load_qm_configuration(path)
        assert str(tmp_path) not in sys.path

    def test_settings_report_loader_errors(self, tmp_path: Path) -> None:
        _write(tmp_path / "configuration.py", "config = None\n")
        settings = tmp_path / "qm.yaml"
        settings.write_text(
            EXAMPLE_SETTINGS_PATH.read_text(encoding="utf-8").replace(
                "../../qm-config/example/configuration.py", "configuration.py"
            ),
            encoding="utf-8",
        )

        with pytest.raises(QMConfigurationError, match="must be a dict"):
            load_qm_settings(settings)


class TestIsolation:
    def test_main_block_does_not_run(self, tmp_path: Path) -> None:
        marker = tmp_path / "connected"
        path = _write(
            tmp_path / "configuration.py",
            f"""
            from pathlib import Path

            config = {{"elements": {{}}}}

            if __name__ == "__main__":
                Path({str(marker)!r}).write_text("opened a QOP connection")
            """,
        )

        assert load_qm_configuration(path) == {"elements": {}}
        assert not marker.exists()

    def test_each_chip_imports_its_own_helpers(self, tmp_path: Path) -> None:
        configuration = """
            from helpers import AMPLITUDE
            from lab.pulses import LENGTH

            config = {"waveforms": {"x180_wf": {"type": "constant", "sample": AMPLITUDE}},
                      "length": LENGTH}
            """
        paths = {}
        for chip, amplitude, length in (("chip-a", 0.1, 40), ("chip-b", 0.3, 60)):
            directory = tmp_path / chip
            _write(directory / "helpers.py", f"AMPLITUDE = {amplitude}\n")
            _write(directory / "lab" / "__init__.py", "")
            _write(directory / "lab" / "pulses.py", f"LENGTH = {length}\n")
            paths[chip] = _write(directory / "configuration.py", configuration)

        for _ in range(2):
            a = load_qm_configuration(paths["chip-a"])
            b = load_qm_configuration(paths["chip-b"])
            assert (a["waveforms"]["x180_wf"]["sample"], a["length"]) == (0.1, 40)
            assert (b["waveforms"]["x180_wf"]["sample"], b["length"]) == (0.3, 60)

        assert "helpers" not in sys.modules
        assert "lab" not in sys.modules and "lab.pulses" not in sys.modules
        assert not any(str(tmp_path) in entry for entry in sys.path)
        assert not any(name.startswith("_qdash_qm_configuration") for name in sys.modules)

    def test_unrelated_module_of_the_same_name_is_restored(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        unrelated = ModuleType("helpers")
        unrelated.AMPLITUDE = "unrelated"  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "helpers", unrelated)
        _write(tmp_path / "helpers.py", "AMPLITUDE = 0.25\n")
        path = _write(
            tmp_path / "configuration.py",
            "from helpers import AMPLITUDE\nconfig = {'sample': AMPLITUDE}\n",
        )

        assert load_qm_configuration(path) == {"sample": 0.25}
        assert sys.modules["helpers"] is unrelated

    def test_sys_path_is_restored_when_a_helper_fails(self, tmp_path: Path) -> None:
        before = list(sys.path)
        _write(tmp_path / "helpers.py", "raise ValueError('bad helper')\n")
        path = _write(tmp_path / "configuration.py", "import helpers\nconfig = {}\n")

        with pytest.raises(QMConfigurationLoadError, match="bad helper"):
            load_qm_configuration(path)

        assert sys.path == before
        assert "helpers" not in sys.modules

    @pytest.mark.parametrize("fail", [False, True])
    def test_cached_package_descendants_are_isolated_and_restored(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fail: bool
    ) -> None:
        package = ModuleType("lab")
        package.__path__ = [str(tmp_path / "chip-a" / "lab")]
        pulses = ModuleType("lab.pulses")
        pulses.LENGTH = 11  # type: ignore[attr-defined]
        package.pulses = pulses  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "lab", package)
        monkeypatch.setitem(sys.modules, "lab.pulses", pulses)
        directory = tmp_path / "chip-b"
        _write(directory / "lab" / "__init__.py", "")
        _write(directory / "lab" / "pulses.py", "LENGTH = 22\n")
        _write(directory / "lab" / "fresh.py", "VALUE = 33\n")
        path = _write(
            directory / "configuration.py",
            "from lab.pulses import LENGTH\n"
            "from lab.fresh import VALUE\n"
            "assert LENGTH == 22\n"
            "config = {'length': LENGTH, 'value': VALUE}\n"
            + ("raise RuntimeError('after helper import')\n" if fail else ""),
        )
        before = list(sys.path)

        if fail:
            with pytest.raises(QMConfigurationLoadError, match="after helper import"):
                load_qm_configuration(path)
        else:
            assert load_qm_configuration(path) == {"length": 22, "value": 33}

        assert sys.path == before
        assert sys.modules["lab"] is package
        assert sys.modules["lab.pulses"] is pulses
        assert package.pulses is pulses
        assert "lab.fresh" not in sys.modules
