"""Setup script to register the zombie-flow detection automation if it is absent.

Follow-up to #1111 / #1350. When an OOM kill takes down the worker process itself
(not just the flow subprocess), no runner survives to report the crash, so the
Prefect flow run is never marked terminal and stays ``Running`` forever. This
registers Prefect's recommended heartbeat-based zombie detection
(https://docs.prefect.io/v3/advanced/detect-zombie-flows): a Proactive automation
that flips a stalled run to ``CRASHED`` when its heartbeats stop. Once the run is
``CRASHED``, the API's reconciliation (#1350) finalizes the execution and releases
the execution lock.

Run automatically by ``start_worker.py`` on container startup. Idempotent: an
existing automation with the same name is left untouched, so worker restarts do
not create duplicates.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from logging import getLogger
from typing import TYPE_CHECKING

from prefect.client.orchestration import get_client
from prefect.client.schemas.objects import StateType
from prefect.events.actions import ChangeFlowRunState
from prefect.events.schemas.automations import AutomationCore, EventTrigger, Posture
from prefect.events.schemas.events import ResourceSpecification

if TYPE_CHECKING:
    from prefect.client.orchestration import PrefectClient

logger = getLogger(__name__)

AUTOMATION_NAME = "Crash zombie flows"

# Flow runs emit a heartbeat every PREFECT_FLOWS_HEARTBEAT_FREQUENCY seconds
# (default 180). Fire once no heartbeat has arrived for 3x that interval, as the
# Prefect docs recommend, to avoid false positives from a single missed beat.
_HEARTBEAT_TIMEOUT_SECONDS = 540


def _build_zombie_automation() -> AutomationCore:
    """Build the AutomationCore for heartbeat-based zombie detection."""
    return AutomationCore(
        name=AUTOMATION_NAME,
        description="Mark flow runs as crashed when their heartbeats stop (zombie detection).",
        trigger=EventTrigger(
            after={"prefect.flow-run.heartbeat"},
            expect={"prefect.flow-run.*"},
            match=ResourceSpecification({"prefect.resource.id": ["prefect.flow-run.*"]}),
            for_each={"prefect.resource.id"},
            posture=Posture.Proactive,
            threshold=1,
            within=timedelta(seconds=_HEARTBEAT_TIMEOUT_SECONDS),
        ),
        actions=[
            ChangeFlowRunState(
                state=StateType.CRASHED,
                message="Flow run marked as crashed due to missing heartbeats.",
            )
        ],
    )


async def _ensure_zombie_automation(client: PrefectClient) -> None:
    """Create the zombie-detection automation unless one with the same name exists."""
    existing = await client.read_automations_by_name(AUTOMATION_NAME)
    if existing:
        logger.info(f"Automation '{AUTOMATION_NAME}' already exists: {existing[0].id}")
        return

    logger.info(f"Creating automation '{AUTOMATION_NAME}'...")
    automation_id = await client.create_automation(_build_zombie_automation())
    logger.info(f"Automation '{AUTOMATION_NAME}' created: {automation_id}")


async def setup_automations() -> None:
    """Register all required automations against the Prefect server."""
    async with get_client() as client:
        await _ensure_zombie_automation(client)


if __name__ == "__main__":
    asyncio.run(setup_automations())
