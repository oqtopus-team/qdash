import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from qdash.datamodel.calibration_note import CalibrationNoteModel
from qdash.datamodel.task import TaskTypes
from qdash.workflow.engine.backend.base import BaseBackend
from qdash.workflow.engine.backend.qubex_paths import get_qubex_paths

if TYPE_CHECKING:
    from qdash.repository.protocols import CalibrationNoteRepository


class QubexBackend(BaseBackend):
    """Backend management for Qubex experiments."""

    name: str = "qubex"

    from qubex import Experiment

    def __init__(
        self,
        config: dict[str, Any],
        *,
        calibration_note_repo: "CalibrationNoteRepository | None" = None,
    ) -> None:
        """Initialize the Qubex backend with a configuration dictionary.

        Parameters
        ----------
        config : dict[str, Any]
            Configuration dictionary for the backend.
        calibration_note_repo : CalibrationNoteRepository, optional
            Repository for calibration notes. If None, uses the default
            MongoDB implementation.

        """
        from qubex import Experiment

        self._config = config
        self._exp: Experiment | None = None
        self._calibration_note_repo = calibration_note_repo

    @property
    def calibration_note_repo(self) -> "CalibrationNoteRepository":
        """Get the calibration note repository, creating default if needed."""
        if self._calibration_note_repo is None:
            from qdash.repository import MongoCalibrationNoteRepository

            self._calibration_note_repo = MongoCalibrationNoteRepository()
        return self._calibration_note_repo

    @property
    def config(self) -> dict[str, Any]:
        """Return the configuration dictionary for the Qubex backend."""
        return self._config

    def version(self) -> str:
        """Return the version of the Qubex backend."""
        from qubex.version import get_package_version

        return str(get_package_version("qubex"))

    def connect(self) -> None:
        if self._exp is None:
            from qubex import Experiment

            if self._config.get("task_type") == TaskTypes.QUBIT:
                qubits = [
                    int(qid) for qid in self._config.get("qids", [])
                ]  # e.g. : ["0", "1", "2"] → [0, 1, 2]
            elif self._config.get("task_type") == TaskTypes.COUPLING:
                qubits = sorted(
                    {int(q) for qid in self._config.get("qids", []) for q in qid.split("-")}
                )  # e.g. : ["0-1", "1-2"] → [0, 1, 2]
            else:
                # Default to all qubits if task_type is not specified
                qubits = []

            chip_id = self._config.get("chip_id", "64Q")
            qubex_paths = get_qubex_paths()
            classifier_dir = self._config.get("classifier_dir")
            if classifier_dir is None:
                msg = "classifier_dir must be provided in config"
                raise ValueError(msg)
            self._exp = Experiment(
                chip_id=chip_id,
                qubits=qubits,
                muxes=self._config.get("muxes", None),
                config_dir=self._config.get("config_dir", str(qubex_paths.config_dir(chip_id))),
                params_dir=self._config.get("params_dir", str(qubex_paths.params_dir(chip_id))),
                classifier_dir=classifier_dir,
                calib_note_path=self._config.get(
                    "note_path", str(qubex_paths.default_calib_note_path)
                ),
            )
            self._exp.connect()

    def get_instance(self) -> Experiment | None:
        if self._exp is None:
            self.connect()
        if self._exp is None:
            msg = "Experiment instance is not initialized. Please call connect() first."
            raise RuntimeError(msg)
        return self._exp or None

    def get_note(self) -> str:
        """Get the calibration note from the experiment."""
        exp = self.get_instance()
        if exp is None:
            msg = "Experiment instance is not initialized. Please call connect() first."
            raise RuntimeError(msg)
        return str(exp.calib_note)

    def save_note(
        self,
        username: str,
        chip_id: str,
        calib_dir: str,
        execution_id: str,
        task_manager_id: str,
        project_id: str,
    ) -> None:
        """Save the calibration note to the experiment."""
        # Initialize calibration note
        note_path = Path(f"{calib_dir}/calib_note/{task_manager_id}.json")
        note_path.parent.mkdir(parents=True, exist_ok=True)

        repo = self.calibration_note_repo
        master_note = repo.find_latest_master(chip_id=chip_id, project_id=project_id)

        if master_note is None:
            master_note = repo.upsert(
                CalibrationNoteModel(
                    project_id=project_id,
                    username=username,
                    chip_id=chip_id,
                    execution_id=execution_id,
                    task_id="master",
                    note={},
                )
            )

        note_path.write_text(json.dumps(master_note.note, indent=2))

    def update_note(
        self,
        username: str,
        chip_id: str,
        calib_dir: str,
        execution_id: str,
        task_manager_id: str,
        project_id: str,
        qid: str | None = None,
    ) -> None:
        """Update the master calibration note in MongoDB atomically.

        Uses per-qubit atomic $set operations to avoid TOCTOU race conditions
        when multiple Dask workers update different qubits in parallel. Each
        worker only touches its own qubit paths via dot-notation
        (e.g., "note.rabi_params.Q024"), so concurrent updates don't conflict.

        When ``qid`` is provided, only note entries whose key matches the qid
        are written.  This prevents a worker from overwriting another worker's
        freshly-calibrated data with its own stale snapshot.

        Note:
        ----
            task_manager_id is kept as a parameter for backward compatibility but not used.
            Only the master note (task_id="master") is updated.
        """
        calib_note = json.loads(self.get_note())

        # Filter to only the calibrated qubit/coupling to avoid TOCTOU.
        # Each param_type dict is keyed by qubit label (e.g. "Q024") or
        # coupling label (e.g. "Q024-Q025").  We keep only the entry that
        # matches the qid that was just calibrated.
        if qid is not None:
            filtered: dict[str, Any] = {}
            for param_type, qubits in calib_note.items():
                if isinstance(qubits, dict) and qid in qubits:
                    filtered[param_type] = {qid: qubits[qid]}
            calib_note = filtered

        repo = self.calibration_note_repo

        query_filter = {
            "task_id": "master",
            "chip_id": chip_id,
            "project_id": project_id,
            "username": username,
            "execution_id": execution_id,
        }

        repo.merge_note_fields(
            query_filter=query_filter,
            calib_note=calib_note,
        )
