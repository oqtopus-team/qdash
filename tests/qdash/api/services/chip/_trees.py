"""Shared-layout Qubex configuration trees for the chip provisioning tests."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import yaml

if TYPE_CHECKING:
    from pathlib import Path

QUEL1_BOX = {"name": "box a", "type": "quel1se-riken8", "address": "10.1.0.1", "adapter": "X"}
QUEL3_BOX = {"name": "q3", "type": "quel3"}


def quel1_rows(*mux_ids: int, box: str = "BOXA") -> list[dict[str, Any]]:
    return [
        {
            "mux": mux,
            "ctrl": [f"{box}-{port}" for port in (5, 6, 7, 8)],
            "read_out": f"{box}-1",
            "read_in": f"{box}-0",
            "pump": f"{box}-2",
        }
        for mux in mux_ids
    ]


def quel3_rows(*mux_ids: int, box: str = "q3") -> list[dict[str, Any]]:
    return [
        {
            "mux": mux,
            "ctrl": [f"{box}:{port}" for port in (2, 4, 9, 11)],
            "read_out": f"{box}:1",
            "read_in": f"{box}:0",
        }
        for mux in mux_ids
    ]


def write_shared_tree(
    root: Path,
    *,
    chip_id: str = "src16",
    n_qubits: int = 16,
    two_systems: bool = True,
    manifest: bool = True,
) -> Path:
    """A chip with a QuEL-1 System on MUX 0-1 and, optionally, a QuEL-3 System on MUX 2-3.

    The tree declares layout 2.0 in ``qubex-config.json`` like a real repository; pass
    ``manifest=False`` to model a repository that has not been updated yet.
    """
    config = root / "config"
    config.mkdir(parents=True, exist_ok=True)
    if manifest:
        (root / "qubex-config.json").write_text('{"layout_version": "2.0"}\n')
    (config / "chip.yaml").write_text(
        yaml.safe_dump(
            {
                chip_id: {
                    "name": chip_id,
                    "n_qubits": n_qubits,
                    "topology": {"type": "square-lattice", "mux_size": 4},
                }
            }
        )
    )
    systems: dict[str, Any] = {
        chip_id: {"chip_id": chip_id, "backend": "quel1", "quel1": {"clock_master": "10.0.0.1"}}
    }
    wiring: dict[str, Any] = {chip_id: quel1_rows(0, 1) if two_systems else quel1_rows(0, 1, 2, 3)}
    if two_systems:
        systems[f"{chip_id}-quel3"] = {"chip_id": chip_id, "backend": "quel3", "quel3": {}}
        wiring[f"{chip_id}-quel3"] = quel3_rows(2, 3)
    (config / "system.yaml").write_text(yaml.safe_dump(systems))
    (config / "wiring.yaml").write_text(yaml.safe_dump(wiring))
    (config / "box.yaml").write_text(
        "# boxes\nBOXA:\n  name: box a\n  type: quel1se-riken8\n  address: 10.1.0.1\n  adapter: X\n"
        "q3:\n  name: q3\n  type: quel3\n"
    )
    for system_id in systems:
        params = root / "params" / system_id
        params.mkdir(parents=True, exist_ok=True)
        unit = "ndelay" if systems[system_id]["backend"] == "quel1" else "ns"
        (params / "capture_delay.yaml").write_text(
            yaml.safe_dump({"meta": {"unit": unit}, "data": dict.fromkeys(range(4), 8)})
        )
        (root / "calibration" / system_id).mkdir(parents=True, exist_ok=True)
        (root / "calibration" / system_id / "calib_note.json").write_text("{}\n")
    return root


def load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


class FakeRepository:
    """Records publish calls; ``fail`` makes every call raise."""

    def __init__(self, *, fail: bool = False, mode: str = "plain") -> None:
        from qdash.common.infrastructure.config_repository import RepoMode

        self.mode = RepoMode(mode)
        self.fail = fail
        self.upserts: list[tuple[dict[str, Any], str, str | None]] = []
        self.published: list[tuple[list[str], str, str | None]] = []

    def upsert_shared(self, entries: Any, message: str, *, chip_id: str | None = None) -> Any:
        if self.fail:
            raise RuntimeError("remote rejected the push")
        self.upserts.append((dict(entries), message, chip_id))
        return type("Result", (), {"commit": None})()

    def publish_owned(self, paths: Any, message: str, *, chip_id: str | None = None) -> Any:
        if self.fail:
            raise RuntimeError("remote rejected the push")
        self.published.append(([str(p) for p in paths], message, chip_id))
        return type("Result", (), {"commit": "abc123"})()
