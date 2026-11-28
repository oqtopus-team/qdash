"""Tests for shared one-qubit strategy helpers."""

from types import SimpleNamespace
from typing import Any

import pytest

from qdash.workflow.service import strategy


@pytest.mark.parametrize(
    "strategy_cls",
    [
        strategy.OneQubitParallelByMuxStrategy,
        strategy.OneQubitParallelByRoundStrategy,
        strategy.OneQubitSequentialStrategy,
        strategy.OneQubitSimultaneousSpectroscopyStrategy,
    ],
)
def test_scheduler_uses_chip_wiring_and_session_mux_mapping(
    monkeypatch: pytest.MonkeyPatch, strategy_cls: type[strategy.OneQubitStrategy]
) -> None:
    built: list[dict[str, Any]] = []
    monkeypatch.setattr(strategy, "OneQubitScheduler", lambda **kwargs: built.append(kwargs))
    monkeypatch.setattr(
        strategy_cls, "_get_wiring_config_path", lambda self, chip_id: f"{chip_id}/wiring.yaml"
    )
    mapping = object()
    session: Any = SimpleNamespace(chip_id="chip-1", mux_mapping=mapping)

    strategy_cls()._scheduler(session)

    assert built == [
        {"chip_id": "chip-1", "wiring_config_path": "chip-1/wiring.yaml", "mux_mapping": mapping}
    ]
