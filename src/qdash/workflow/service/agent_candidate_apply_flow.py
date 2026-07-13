"""System flow for applying a gated agent candidate on a workflow worker."""

from __future__ import annotations

from typing import Any

from prefect import flow, get_run_logger

from qdash.common.config.backend import get_default_backend
from qdash.dbmodel.agent_session import AgentCandidateCommitDocument
from qdash.dbmodel.initialize import initialize
from qdash.workflow.engine.backend import create_backend
from qdash.workflow.engine.params_updater import (
    get_params_updater,
    resolve_param_yaml_file_names,
)


def _extract_git_result(result: dict[str, Any]) -> str:
    params_result = result.get("all_params")
    if isinstance(params_result, dict):
        error = params_result.get("error")
        if error:
            raise RuntimeError(f"GitHub params push failed: {error}")
        commit = params_result.get("commit")
        if isinstance(commit, str):
            return commit
        status = params_result.get("status")
        if isinstance(status, str):
            return status
    if isinstance(params_result, str):
        if params_result.startswith("Error:"):
            raise RuntimeError(params_result)
        return params_result
    raise RuntimeError("GitHub params push returned no version result")


@flow(name="agent-candidate-apply")
def agent_candidate_apply(
    project_id: str,
    session_id: str,
    commit_id: str,
    push_to_github: bool = True,
) -> dict[str, Any]:
    """Apply one already-gated candidate to worker-side backend parameter files."""
    initialize()
    logger = get_run_logger()
    commit = AgentCandidateCommitDocument.find_one(
        {
            "project_id": project_id,
            "session_id": session_id,
            "commit_id": commit_id,
            "status": "committed",
        }
    ).run()
    if commit is None:
        raise ValueError(f"Committed agent candidate '{commit_id}' not found")

    AgentCandidateCommitDocument.get_motor_collection().update_one(
        {
            "project_id": project_id,
            "commit_id": commit_id,
            "backend_status": {"$in": ["dispatching", "queued"]},
        },
        {"$set": {"backend_status": "applying", "backend_error": ""}},
    )

    try:
        if commit.after_snapshot is None:
            raise ValueError("Candidate commit has no authoritative after snapshot")
        backend_name = get_default_backend()
        github_integration: Any | None = None
        base_git_commit: str | None = None
        if push_to_github:
            from qdash.workflow.service.github import GitHubIntegration

            if not GitHubIntegration.check_credentials():
                raise RuntimeError("GitHub credentials are required for versioned backend apply")
            github_integration = GitHubIntegration(
                commit.committed_by,
                commit.chip_id,
                commit.execution_id,
            )
            base_git_commit = github_integration.pull_config()
            if not base_git_commit:
                raise RuntimeError("Could not pull the latest backend config before apply")

        backend = create_backend(
            backend=backend_name,
            config={
                "task_type": "qubit",
                "username": commit.committed_by,
                "qids": [commit.qid],
                "chip_id": commit.chip_id,
                "project_id": project_id,
                "classifier_dir": ".",
            },
        )
        updater = get_params_updater(backend, commit.chip_id)
        if updater is None:
            raise RuntimeError(f"Backend '{backend_name}' has no parameter updater")

        parameters = {commit.parameter_name: commit.after_snapshot}
        target_files = resolve_param_yaml_file_names(parameters)
        if not target_files:
            raise ValueError(
                f"Parameter '{commit.parameter_name}' has no configured params YAML mapping"
            )
        changed_files = updater.update(commit.qid, parameters)
        verified_files = updater.verify(commit.qid, parameters)
        if verified_files != target_files:
            raise RuntimeError(
                "Backend verification did not cover all target files: "
                f"target={sorted(target_files)}, verified={sorted(verified_files)}"
            )

        AgentCandidateCommitDocument.get_motor_collection().update_one(
            {"project_id": project_id, "commit_id": commit_id},
            {
                "$set": {
                    "backend_name": backend_name,
                    "backend_base_git_commit": base_git_commit,
                    "backend_target_files": sorted(target_files),
                    "backend_changed_files": sorted(changed_files),
                    "backend_verified": True,
                }
            },
        )

        git_commit: str | None = None
        if push_to_github:
            from qdash.workflow.service.github import ConfigFileType, GitHubPushConfig

            if github_integration is None:
                raise RuntimeError("GitHub integration preflight was not initialized")
            git_result = github_integration.push_files(
                GitHubPushConfig(
                    enabled=True,
                    file_types=[ConfigFileType.ALL_PARAMS],
                    params_file_names=sorted(target_files),
                    commit_message=(
                        "Apply agent candidate "
                        f"{commit.commit_id} ({commit.qid}.{commit.parameter_name})"
                    ),
                )
            )
            git_commit = _extract_git_result(git_result)

        from qdash.common.utils.datetime import now

        AgentCandidateCommitDocument.get_motor_collection().update_one(
            {"project_id": project_id, "commit_id": commit_id},
            {
                "$set": {
                    "backend_status": "applied",
                    "backend_name": backend_name,
                    "backend_base_git_commit": base_git_commit,
                    "backend_target_files": sorted(target_files),
                    "backend_changed_files": sorted(changed_files),
                    "backend_verified": True,
                    "backend_git_commit": git_commit,
                    "backend_error": "",
                    "backend_applied_at": now(),
                }
            },
        )
        logger.info(
            "Applied agent candidate commit=%s files=%s git=%s",
            commit_id,
            sorted(target_files),
            git_commit,
        )
        return {
            "commit_id": commit_id,
            "backend": backend_name,
            "target_files": sorted(target_files),
            "changed_files": sorted(changed_files),
            "verified": True,
            "git_commit": git_commit,
        }
    except Exception as exc:
        from qdash.common.utils.datetime import now

        AgentCandidateCommitDocument.get_motor_collection().update_one(
            {"project_id": project_id, "commit_id": commit_id},
            {
                "$set": {
                    "backend_status": "failed",
                    "backend_error": str(exc),
                    "backend_applied_at": now(),
                }
            },
        )
        logger.error("Agent candidate backend apply failed: %s", exc)
        raise
