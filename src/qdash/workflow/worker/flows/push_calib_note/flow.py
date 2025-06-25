import json
from pathlib import Path

from prefect import flow
from qdash.dbmodel.calibration_note import CalibrationNoteDocument
from qdash.workflow.worker.tasks.push_github import push_github


@flow(flow_run_name="Push Calibration Note")
def push_calib_note(
    username: str = "admin",
    source_path: str = "/app/config/qubex/64Q/calibration/calib_note.json",
    repo_subpath: str = "64Q/calibration/calib_note.json",
    commit_message: str = "Update calib_note.json",
    branch: str = "main",
) -> str:
    """Push local calib_note.json to the GitHub repository.

    Args:
    ----
        username: Username for the calibration note
        source_path: Local path to the updated calib_note.json
        repo_subpath: Relative path inside the repo to replace
        commit_message: Commit message
        branch: Branch to push to

    Returns:
    -------
        str: Commit SHA

    """
    latest = (
        CalibrationNoteDocument.find({"username": username, "task_id": "master"})
        .sort([("timestamp", -1)])  # 更新時刻で降順ソート
        .limit(1)
        .run()
    )[0]
    calib_note_dir = "/app/config/qubex/64Q/calibration"
    calib_note = latest.note
    calib_note_path = f"{calib_note_dir}/calib_note.json"
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
