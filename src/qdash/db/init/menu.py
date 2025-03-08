"""Menu initialization module."""

from qdash.db.init.initialize import initialize
from qdash.dbmodel.menu import MenuDocument


def init_menu(username: str) -> None:
    """Initialize menu document."""
    initialize()
    MenuDocument(
        name="OneQubitCheck",
        username=username,
        description="description",
        qids=[["28", "29", "30", "31"]],
        tasks=["CheckStatus", "DumpBox", "CheckNoise", "CheckRabi"],
        notify_bool=False,
        tags=["debug"],
        system_info={},
    ).insert()
