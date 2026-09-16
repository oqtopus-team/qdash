"""Wiring module names preserve hyphens when channels use colon separators."""

import pytest

from qdash.common.wiring_resources import mux_module_resources


@pytest.mark.parametrize(
    ("channel", "module"),
    [
        ("control-box-a:0", "control-box-a"),
        ("control-box-b:1", "control-box-b"),
        ("BOX:0:1", "BOX"),
        ("BOX-0", "BOX"),
        ("control-box-a", "control"),
        ("BOX", "BOX"),
    ],
)
def test_module_names_for_readout_and_control(channel: str, module: str) -> None:
    assert mux_module_resources({"read_out": channel, "ctrl": [channel]}) == {
        f"module:read_out:{module}",
        f"module:ctrl:{module}",
    }


def test_mixed_channel_formats() -> None:
    assert mux_module_resources(
        {"read_out": "control-box-a:0", "ctrl": ["control-box-b:1", "LEGACY-2"]}
    ) == {
        "module:read_out:control-box-a",
        "module:ctrl:control-box-b",
        "module:ctrl:LEGACY",
    }
