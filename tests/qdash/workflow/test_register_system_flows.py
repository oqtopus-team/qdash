"""Tests for built-in Prefect deployment registration metadata."""

from qdash.workflow.register_system_flows import get_system_flows


def test_system_flow_registration_includes_legacy_and_agent_deployments() -> None:
    """Worker startup registers both built-in deployments."""
    by_name = {item["deployment_name"]: item for item in get_system_flows()}

    assert by_name["system-single-task"] == {
        "file_path": "/app/qdash/workflow/service/single_task_flow.py",
        "flow_function_name": "single_task_executor",
        "deployment_name": "system-single-task",
    }
    assert by_name["system-candidate-apply"] == {
        "file_path": "/app/qdash/workflow/service/agent_candidate_apply_flow.py",
        "flow_function_name": "agent_candidate_apply",
        "deployment_name": "system-candidate-apply",
    }
