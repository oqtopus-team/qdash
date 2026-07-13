"""Register system Prefect deployments on worker startup.

This script registers built-in system flows (like single-task re-execution)
as Prefect deployments via the deployment-service HTTP API — the same
code path used for user flows.

It runs after setup_work_pool.py and before the worker starts.
"""

import asyncio
import os
from logging import getLogger

import httpx

logger = getLogger(__name__)

DEPLOYMENT_SERVICE_URL = os.getenv("DEPLOYMENT_SERVICE_URL", "http://deployment-service:8001")

SYSTEM_FLOWS = [
    {
        "file_path": "/app/qdash/workflow/service/single_task_flow.py",
        "flow_function_name": "single_task_executor",
        "deployment_name": "system-single-task",
    },
]


AGENT_SYSTEM_FLOWS = [
    {
        "file_path": "/app/qdash/workflow/service/agent_candidate_apply_flow.py",
        "flow_function_name": "agent_candidate_apply",
        "deployment_name": "system-candidate-apply",
    },
]


def get_system_flows(*, agent_calibration_enabled: bool | None = None) -> list[dict[str, str]]:
    """Return deployments enabled for this worker, preserving legacy defaults."""
    if agent_calibration_enabled is None:
        agent_calibration_enabled = os.getenv("ENABLE_AGENT_CALIBRATION", "false").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
    if agent_calibration_enabled:
        return [*SYSTEM_FLOWS, *AGENT_SYSTEM_FLOWS]
    return list(SYSTEM_FLOWS)


async def register_system_flows() -> None:
    """Register built-in worker deployments via deployment-service."""
    async with httpx.AsyncClient() as client:
        for deployment in get_system_flows():
            name = deployment["deployment_name"]
            logger.info(f"Registering system deployment '{name}' via {DEPLOYMENT_SERVICE_URL}")
            response = await client.post(
                f"{DEPLOYMENT_SERVICE_URL}/register-deployment",
                json=deployment,
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()
            logger.info(
                f"System deployment '{name}' registered: deployment_id={data['deployment_id']}"
            )


if __name__ == "__main__":
    asyncio.run(register_system_flows())
