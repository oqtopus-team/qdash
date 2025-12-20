import json
from pathlib import Path

from prefect import flow
from qdash.repository import MongoCalibrationNoteRepository
from qdash.workflow.engine.backend.qubex_paths import get_qubex_paths
from qdash.workflow.worker.tasks.push_github import push_github


@flow(flow_run_name="Push Calibration Note")
def push_calib_note(
    username: str = "admin",
    chip_id: str = "64Qv1",
    commit_message: str = "Update calib_note.json",
    branch: str = "main",
) -> str:
    """Push local calib_note.json to the GitHub repository.

    Args:
    ----
        username: Username for the calibration note
        chip_id: Chip ID for the calibration note
        commit_message: Commit message
        branch: Branch to push to

    Returns:
    -------
        str: Commit SHA

    Raises:
    ------
        ValueError: If no master calibration note is found

    """
    qubex_paths = get_qubex_paths()
    calib_note_path = qubex_paths.calib_note_json(chip_id)
    source_path = str(calib_note_path)
    repo_subpath = f"{chip_id}/calibration/calib_note.json"

    repo = MongoCalibrationNoteRepository()
    latest_note = repo.find_latest_master(chip_id=chip_id, username=username)

    if latest_note is None:
        msg = f"No master calibration note found for user {username}"
        raise ValueError(msg)

    calib_note = latest_note.note
    calib_note_path.parent.mkdir(parents=True, exist_ok=True)
    with Path(calib_note_path).open("w", encoding="utf-8") as f:
        json.dump(calib_note, f, indent=4, ensure_ascii=False, sort_keys=True)

    return str(
        push_github(
            source_path=source_path,
            repo_subpath=repo_subpath,
            commit_message=commit_message,
            branch=branch,
        )
    )
