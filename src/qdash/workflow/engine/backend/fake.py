from typing import Any

from qdash.datamodel.task import TaskTypes
from qdash.workflow.engine.backend.base import BaseBackend
from qdash.workflow.engine.backend.qubex_paths import (
    resolve_session_system_id,
    session_experiment_paths,
)


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

        system_id = resolve_session_system_id(self._config)
        self._config["system_id"] = system_id
        paths = session_experiment_paths(self._config, system_id)
        self._exp = FakeExperiment(
            system_id=system_id,
            qubits=qubits or None,
            muxes=self._config.get("muxes", None),
            config_dir=paths["config_dir"],
            params_dir=paths["params_dir"],
            classifier_dir=self._config.get("classifier_dir", "."),
            readout_duration=self._config.get("readout_duration"),
            calib_note_path=paths["calib_note_path"],
        )
        self._exp.connect()

    def disconnect(self) -> None:
        """Release the fake Experiment if it was created."""
        if self._exp is not None:
            self._exp.disconnect()
            self._exp = None

    @property
    def is_connected(self) -> bool:
        """Return whether a fake Experiment has been created and connected."""
        return self._exp is not None

    def get_instance(self) -> Any:
        if self._exp is None:
            self.connect()
        if self._exp is None:
            msg = "Backend instance is not initialized. Please call connect() first."
            raise RuntimeError(msg)
        return self._exp
