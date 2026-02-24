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

# The flow file lives at /app/qdash/workflow/service/single_task_flow.py
# inside both the worker and deployment-service containers (shared volume).
FLOW_FILE_PATH = "/app/qdash/workflow/service/single_task_flow.py"
FLOW_FUNCTION_NAME = "single_task_executor"
DEPLOYMENT_NAME = "system-single-task"


async def register_system_flows() -> None:
    """Register the single-task-executor deployment via deployment-service."""
    logger.info(
        f"Registering system deployment '{DEPLOYMENT_NAME}' " f"via {DEPLOYMENT_SERVICE_URL}"
    )

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{DEPLOYMENT_SERVICE_URL}/register-deployment",
            json={
                "file_path": FLOW_FILE_PATH,
                "flow_function_name": FLOW_FUNCTION_NAME,
                "deployment_name": DEPLOYMENT_NAME,
            },
            timeout=30.0,
        )
        response.raise_for_status()
        data = response.json()
        logger.info(
            f"System deployment '{DEPLOYMENT_NAME}' registered: "
            f"deployment_id={data['deployment_id']}"
        )


if __name__ == "__main__":
    asyncio.run(register_system_flows())
