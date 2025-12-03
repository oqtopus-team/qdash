"""FlowSession factory module.

This module provides factory functions for creating FlowSession instances
with sensible defaults.
"""

from typing import TYPE_CHECKING

from qdash.workflow.flow.config import FlowSessionConfig

if TYPE_CHECKING:
    from qdash.workflow.flow.session import FlowSession


def create_flow_session(
    config: FlowSessionConfig,
) -> "FlowSession":
    """Create a FlowSession with the given configuration.

    This is the primary factory function for creating FlowSession instances.
    It provides a clean way to create sessions from immutable config objects.

    Args:
        config: FlowSession configuration

    Returns:
        Configured FlowSession instance

    Example:
        ```python
        config = FlowSessionConfig.create(
            username="alice",
            chip_id="chip_1",
            qids=["0", "1", "2"],
        )

        session = create_flow_session(config)
        ```
    """
    from qdash.workflow.flow.session import FlowSession

    return FlowSession(
        username=config.username,
        chip_id=config.chip_id,
        qids=list(config.qids),
        execution_id=config.execution_id,
        backend_name=config.backend_name,
        name=config.name,
        tags=list(config.tags) if config.tags else None,
        use_lock=config.use_lock,
        note=dict(config.note) if config.note else None,
        enable_github_pull=config.enable_github_pull,
        github_push_config=config.github_push_config,
        muxes=list(config.muxes) if config.muxes else None,
    )
