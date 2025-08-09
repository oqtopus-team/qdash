from prefect import flow
from qdash.workflow.worker.flows.push_props.create_props import create_chip_properties
from qdash.workflow.worker.tasks.push_github import push_github


@flow(flow_run_name="Push Chip Properties")
def push_props(
    username: str = "admin",
    chip_id: str = "64Qv1",
    commit_message: str = "Update props.yaml",
    branch: str = "main",
) -> str:
    """Push local chip_properties.yaml to the GitHub repository.

    Args:
    ----
        username: username
        source_path: Local path to the updated chip_properties.yaml
        repo_subpath: Relative path inside the repo to replace
        commit_message: Commit message
        chip_id: Chip ID for the properties
        branch: Branch to push to

    Returns:
    -------
        str: Commit SHA

    """
    source_path = f"/app/config/qubex/{chip_id}/params/props.yaml"
    repo_subpath = f"{chip_id}/params/props.yaml"
    create_chip_properties(username=username, source_path=source_path, target_path=source_path, chip_id=chip_id)
    return str(push_github(source_path, repo_subpath, commit_message, branch))
