import json
from pathlib import Path

from qdash.dbmodel.calibration_note import CalibrationNoteDocument
from qdash.workflow._internal.merge_notes import merge_notes_by_timestamp
from qdash.workflow.engine.backend.base import BaseBackend


class QubexBackend(BaseBackend):
    """Backend management for Qubex experiments."""

    name: str = "qubex"

    from qubex import Experiment

    def __init__(self, config: dict) -> None:
        from qubex import Experiment

        """Initialize the Qubex backend with a configuration dictionary."""
        self._config = config
        self._exp: Experiment | None = None

    @property
    def config(self) -> dict:
        """Return the configuration dictionary for the Qubex backend."""
        return self._config

    def version(self) -> str:
        """Return the version of the Qubex backend."""
        from qubex.version import get_package_version

        return get_package_version("qubex")

    def connect(self) -> None:
        if self._exp is None:
            from qubex import Experiment

            if self._config.get("task_type") == "qubit":
                qubits = [int(qid) for qid in self._config.get("qids", [])]  # e.g. : ["0", "1", "2"] → [0, 1, 2]
            elif self._config.get("task_type") == "coupling":
                qubits = sorted(
                    {int(q) for qid in self._config.get("qids", []) for q in qid.split("-")}
                )  # e.g. : ["0-1", "1-2"] → [0, 1, 2]
            else:
                # Default to all qubits if task_type is not specified
                qubits = []

            chip_id = self._config.get("chip_id", "64Q")
            self._exp = Experiment(
                chip_id=chip_id,
                qubits=qubits,
                muxes=self._config.get("muxes", None),
                config_dir=self._config.get("config_dir", f"/app/config/qubex/{chip_id}/config"),
                params_dir=self._config.get("params_dir", f"/app/config/qubex/{chip_id}/params"),
                classifier_dir=self._config.get("classifier_dir", "/app/.classifier"),
                calib_note_path=self._config.get("note_path", "/app/calib_note.json"),
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
        self, username: str, chip_id: str, calib_dir: str, execution_id: str, task_manager_id: str, project_id: str
    ) -> None:
        """Save the calibration note to the experiment."""
        # Initialize calibration note
        note_path = Path(f"{calib_dir}/calib_note/{task_manager_id}.json")
        note_path.parent.mkdir(parents=True, exist_ok=True)

        master_doc = (
            CalibrationNoteDocument.find({"task_id": "master", "chip_id": chip_id, "project_id": project_id})
            .sort([("timestamp", -1)])
            .limit(1)
            .run()
        )

        if not master_doc:
            master_doc = CalibrationNoteDocument.upsert_note(
                username=username,
                chip_id=chip_id,
                execution_id=execution_id,
                task_id="master",
                note={},
                project_id=project_id,
            )
        else:
            master_doc = master_doc[0]
        note_path.write_text(json.dumps(master_doc.note, indent=2))

    def update_note(
        self, username: str, chip_id: str, calib_dir: str, execution_id: str, task_manager_id: str, project_id: str
    ) -> None:
        """Update the master calibration note in MongoDB only.

        This method saves calibration notes exclusively to MongoDB, avoiding
        file I/O operations during task execution. This design:
        - Eliminates race conditions in thread-based parallel execution
        - Reduces unnecessary disk I/O
        - Establishes MongoDB as the single source of truth
        - Simplified architecture: only master note is maintained (no per-task notes)

        The calibration note file is only written during initialization (save_note)
        and optionally during export (finish_calibration with export_note_to_file=True).

        Note:
        ----
            task_manager_id is kept as a parameter for backward compatibility but not used.
            Only the master note (task_id="master") is updated.
        """
        calib_note = json.loads(self.get_note())

        # Get the latest master note for this chip
        master_doc = CalibrationNoteDocument.find_one(
            {
                "task_id": "master",
                "chip_id": chip_id,
                "project_id": project_id,
            }
        ).run()

        if master_doc is None:
            # マスターノートが存在しない場合は新規作成
            CalibrationNoteDocument.upsert_note(
                username=username,
                chip_id=chip_id,
                execution_id=execution_id,
                task_id="master",
                note=calib_note,
                project_id=project_id,
            )
        else:
            # マスターノートが存在する場合はマージ
            merged_note = merge_notes_by_timestamp(master_doc.note, calib_note)
            CalibrationNoteDocument.upsert_note(
                username=username,
                chip_id=chip_id,
                execution_id=execution_id,
                task_id="master",
                note=merged_note,
                project_id=project_id,
            )

        # File I/O removed - MongoDB is the single source of truth
        # For file export, use finish_calibration(export_note_to_file=True)
