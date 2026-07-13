"""Tests for built-in Prefect deployment registration metadata."""

from qdash.workflow.register_system_flows import get_system_flows


def test_system_flow_registration_preserves_legacy_default() -> None:
    """Worker startup keeps only the established deployment enabled by default."""
    assert get_system_flows(agent_calibration_enabled=False) == [
        {
            "file_path": "/app/qdash/workflow/service/single_task_flow.py",
            "flow_function_name": "single_task_executor",
            "deployment_name": "system-single-task",
        }
    ]


def test_system_flow_registration_can_enable_agent_candidate_apply() -> None:
    """Agent backend apply is registered only after deployment opt-in."""
    by_name = {
        item["deployment_name"]: item for item in get_system_flows(agent_calibration_enabled=True)
    }

    assert by_name["system-single-task"]["flow_function_name"] == "single_task_executor"
    assert by_name["system-candidate-apply"] == {
        "file_path": "/app/qdash/workflow/service/agent_candidate_apply_flow.py",
        "flow_function_name": "agent_candidate_apply",
        "deployment_name": "system-candidate-apply",
    }
