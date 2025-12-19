"""Setup script to create user-flows work pool if it doesn't exist."""

import asyncio
from logging import getLogger

from prefect.client.orchestration import get_client
from prefect.client.schemas.actions import WorkPoolCreate

logger = getLogger(__name__)

WORK_POOL_NAME = "user-flows-pool"


async def setup_work_pool() -> None:
    """Create user-flows work pool if it doesn't exist."""
    from prefect.exceptions import ObjectAlreadyExists, ObjectNotFound

    async with get_client() as client:
        try:
            # Check if work pool already exists
            work_pool = await client.read_work_pool(WORK_POOL_NAME)
            logger.info(f"Work pool '{WORK_POOL_NAME}' already exists: {work_pool.id}")
        except ObjectNotFound:
            # Work pool doesn't exist, create it
            logger.info(f"Creating work pool '{WORK_POOL_NAME}'...")
            try:
                work_pool = await client.create_work_pool(
                    WorkPoolCreate(
                        name=WORK_POOL_NAME,
                        type="process",  # Process work pool type
                        description="Work pool for user-defined flows",
                    )
                )
                logger.info(f"Work pool '{WORK_POOL_NAME}' created successfully: {work_pool.id}")
            except ObjectAlreadyExists:
                # Race condition: another process created it
                logger.info(f"Work pool '{WORK_POOL_NAME}' was created by another process")
        except Exception as e:
            logger.error(f"Error checking/creating work pool: {e}")
            raise


if __name__ == "__main__":
    asyncio.run(setup_work_pool())
