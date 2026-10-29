import hashlib
import logging
import re
from collections.abc import Generator, Iterable
from contextlib import contextmanager
from typing import cast

from prefect.client.orchestration import SyncPrefectClient, get_client
from prefect.client.schemas.actions import (
    GlobalConcurrencyLimitCreate,
    GlobalConcurrencyLimitUpdate,
)
from prefect.concurrency.sync import concurrency
from prefect.context import get_run_context
from prefect.exceptions import MissingContextError, ObjectAlreadyExists, ObjectNotFound

logger = logging.getLogger(__name__)

_LOCK_PREFIX = "qdash-qubex-configure-box"
_LOCK_LIMIT = 1
_SLOT_DECAY_PER_SECOND = 0.0
_LEASE_DURATION_SECONDS = 600


def _lock_name(box_id: str) -> str:
    """Build a stable Prefect concurrency-limit name for a Qubex box."""
    readable_id = re.sub(r"[^A-Za-z0-9_.:-]+", "-", box_id).strip("-")[:48] or "box"
    digest = hashlib.sha256(box_id.encode()).hexdigest()[:12]
    return f"{_LOCK_PREFIX}-{readable_id}-{digest}"


def _ensure_limits(names: tuple[str, ...]) -> None:
    """Create and activate the managed one-slot limits before acquisition."""
    with cast("SyncPrefectClient", get_client(sync_client=True)) as client:
        for name in names:
            try:
                limit = client.read_global_concurrency_limit_by_name(name)
            except ObjectNotFound:
                try:
                    client.create_global_concurrency_limit(
                        GlobalConcurrencyLimitCreate(
                            name=name,
                            limit=_LOCK_LIMIT,
                            active=True,
                            slot_decay_per_second=_SLOT_DECAY_PER_SECOND,
                        )
                    )
                except ObjectAlreadyExists:
                    # Another worker created the same box limit after our read.
                    limit = client.read_global_concurrency_limit_by_name(name)
                else:
                    continue

            if (
                limit.limit != _LOCK_LIMIT
                or not limit.active
                or limit.slot_decay_per_second != _SLOT_DECAY_PER_SECOND
            ):
                client.update_global_concurrency_limit(
                    name,
                    GlobalConcurrencyLimitUpdate(
                        limit=_LOCK_LIMIT,
                        active=True,
                        slot_decay_per_second=_SLOT_DECAY_PER_SECOND,
                    ),
                )


@contextmanager
def configuration_push_lock(box_ids: Iterable[str]) -> Generator[None, None, None]:
    """Serialize Qubex configuration pushes that touch any common box."""
    normalized_box_ids = tuple(sorted(set(box_ids)))
    if not normalized_box_ids:
        yield
        return

    try:
        get_run_context()
    except MissingContextError:
        # Preserve direct/local task execution where Prefect coordination is unavailable.
        logger.debug(
            "Skipping Qubex configuration lock outside a Prefect run context: boxes=%s",
            normalized_box_ids,
        )
        yield
        return

    names = tuple(_lock_name(box_id) for box_id in normalized_box_ids)
    _ensure_limits(names)
    logger.info("Waiting for Qubex configuration lock: boxes=%s", normalized_box_ids)
    with concurrency(
        list(names),
        occupy=1,
        strict=True,
        lease_duration=_LEASE_DURATION_SECONDS,
        raise_on_lease_renewal_failure=True,
    ):
        logger.info("Acquired Qubex configuration lock: boxes=%s", normalized_box_ids)
        yield
