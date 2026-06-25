from typing import Any

from qdash.datamodel.task import TaskTypes
from qdash.workflow.engine.backend.base import BaseBackend
from qdash.workflow.engine.backend.qubex_paths import get_qubex_paths


class FakeBackend(BaseBackend):
    """Backend management for QUBEX-compatible fake experiments."""

    name: str = "fake"

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize the Fake backend with a configuration dictionary."""
        self._config = config
        self._exp: Any | None = None

    @property
    def config(self) -> dict[str, Any]:
        """Return the configuration dictionary for the Fake backend."""
        return self._config

    def version(self) -> str:
        """Return the version of the Fake backend."""
        return "fake-qubex"

    def connect(self) -> None:
        if self._exp is not None:
            return

        from qdash.workflow.engine.backend.fake_qubex import FakeExperiment

        if self._config.get("task_type") == TaskTypes.QUBIT:
            qubits = [int(qid) for qid in self._config.get("qids", [])]
        elif self._config.get("task_type") == TaskTypes.COUPLING:
            qubits = sorted(
                {int(q) for qid in self._config.get("qids", []) for q in qid.split("-")}
            )
        else:
            qubits = []

        chip_id = self._config.get("chip_id", "64Q")
        qubex_paths = get_qubex_paths()
        self._exp = FakeExperiment(
            chip_id=chip_id,
            qubits=qubits or None,
            muxes=self._config.get("muxes", None),
            config_dir=self._config.get("config_dir", str(qubex_paths.config_dir(chip_id))),
            params_dir=self._config.get("params_dir", str(qubex_paths.params_dir(chip_id))),
            classifier_dir=self._config.get("classifier_dir", "."),
            calib_note_path=self._config.get("note_path", str(qubex_paths.default_calib_note_path)),
        )
        self._exp.connect()

    def get_instance(self) -> Any:
        if self._exp is None:
            self.connect()
        if self._exp is None:
            msg = "Backend instance is not initialized. Please call connect() first."
            raise RuntimeError(msg)
        return self._exp
