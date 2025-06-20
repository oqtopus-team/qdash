from typing import Any

from qdash.workflow.core.session.base import BaseSession

# Constants
CONFIG_DIR = "/app/config"
PARAMS_DIR = "/app/config"
CHIP_SIZE_64 = 64
CHIP_SIZE_144 = 144
CHIP_SIZE_256 = 256


class QubexSession(BaseSession):
    """Session management for Qubex experiments."""

    from qubex import Experiment

    def __init__(self, config: dict) -> None:
        """Initialize the Qubex session with a configuration dictionary."""
        self._config = config
        self._exp: Any | None = None

    def connect(self) -> None:
        if self._exp is None:
            from qubex import Experiment

            self._exp = Experiment(
                chip_id=self._config.get("chip_id", "64Q"),
                qubits=self._config.get("qubits", []),
                config_dir=self._config.get("config_dir", CONFIG_DIR),
                params_dir=self._config.get("params_dir", PARAMS_DIR),
                calib_note_path=self._config.get("calib_note_path", "/app/calib_note.json"),
            )

    def get_session(self) -> Experiment | None:
        if self._exp is None:
            self.connect()
        if self._exp is None:
            msg = "Experiment instance is not initialized. Please call connect() first."
            raise RuntimeError(msg)
        return self._exp or None

    def get_note(self) -> str:
        """Get the calibration note from the experiment."""
        exp = self.get_session()
        if exp is None:
            msg = "Experiment instance is not initialized. Please call connect() first."
            raise RuntimeError(msg)
        return str(exp.calib_note)
