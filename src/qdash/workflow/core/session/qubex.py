import json
from pathlib import Path

from qdash.dbmodel.calibration_note import CalibrationNoteDocument

from qdash.workflow.core.session.base import BaseSession
from qdash.workflow.utils.merge_notes import merge_notes_by_timestamp


class QubexSession(BaseSession):
    """Session management for Qubex experiments."""

    name: str = "qubex"

    from qubex import Experiment

    def __init__(self, config: dict) -> None:
        from qubex import Experiment

        """Initialize the Qubex session with a configuration dictionary."""
        self._config = config
        self._exp: Experiment | None = None

    @property
    def config(self) -> dict:
        """Return the configuration dictionary for the Qubex session."""
        return self._config

    def version(self) -> str:
        """Return the version of the Qubex session."""
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
                config_dir=self._config.get("config_dir", f"/app/config/qubex/{chip_id}/config"),
                params_dir=self._config.get("params_dir", f"/app/config/qubex/{chip_id}/params"),
                calib_note_path=self._config.get("note_path", "/app/calib_note.json"),
            )
            self._exp.connect()

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

    def save_note(self, username: str, calib_dir: str, execution_id: str, task_manager_id: str) -> None:
        """Save the calibration note to the experiment."""
        # Initialize calibration note
        note_path = Path(f"{calib_dir}/calib_note/{task_manager_id}.json")
        note_path.parent.mkdir(parents=True, exist_ok=True)

        master_doc = CalibrationNoteDocument.find({"task_id": "master"}).sort([("timestamp", -1)]).limit(1).run()

        if not master_doc:
            master_doc = CalibrationNoteDocument.upsert_note(
                username=username,
                execution_id=execution_id,
                task_id="master",
                note={},
            )
        else:
            master_doc = master_doc[0]
        note_path.write_text(json.dumps(master_doc.note, indent=2))

    def update_note(self, username: str, calib_dir: str, execution_id: str, task_manager_id: str) -> None:
        """Update the calibration note in the experiment."""
        calib_note = json.loads(self.get_note())
        task_doc = CalibrationNoteDocument.find_one(
            {
                "execution_id": execution_id,
                "task_id": task_manager_id,
                "username": username,
            }
        ).run()

        if task_doc is None:
            # タスクノートが存在しない場合は新規作成
            task_doc = CalibrationNoteDocument.upsert_note(
                username=username,
                execution_id=execution_id,
                task_id=task_manager_id,
                note=calib_note,
            )
        else:
            # タスクノートが存在する場合はマージ
            merged_note = merge_notes_by_timestamp(task_doc.note, calib_note)
            task_doc = CalibrationNoteDocument.upsert_note(
                username=username,
                execution_id=execution_id,
                task_id=task_manager_id,
                note=merged_note,
            )

        # JSONファイルとして出力
        note_dir = Path(f"{calib_dir}/calib_note")
        note_dir.mkdir(parents=True, exist_ok=True)
        note_path = note_dir / f"{task_manager_id}.json"
        note_path.write_text(json.dumps(task_doc.note, indent=2))
