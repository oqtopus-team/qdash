from prefect import flow
from qdash.workflow.worker.flows.push_props.create_props import create_chip_properties
from qdash.workflow.worker.tasks.push_github import push_github


@flow(flow_run_name="Push Chip Properties")
def push_props(
    username: str = "admin",
    source_path: str = "/app/config/qubex/64Q/params/props.yaml",
    repo_subpath: str = "64Q/params/props.yaml",
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
        branch: Branch to push to

    Returns:
    -------
        str: Commit SHA

    """
    create_chip_properties(username=username, source_path=source_path, target_path=source_path)
    return str(push_github(source_path, repo_subpath, commit_message, branch))
