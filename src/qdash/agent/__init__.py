"""Shared Agent package used by the API.

Package layout:

- ``runtime``: data loading for a chat about one task result
- ``config``: configuration models and loaders
- ``contracts``: request/response models shared across layers
- ``prompts`` / ``tooling`` / ``services``: implementation details grouped by role
- ``blocks``: the answer format rendered as markdown for issue and forum replies
"""

from qdash.agent.blocks import blocks_to_markdown
from qdash.agent.config import AgentConfig, ModelConfig, load_agent_config
from qdash.agent.contracts import ChatRequest, TaskContext
from qdash.agent.runtime import AgentRuntime

__all__ = [
    "AgentConfig",
    "AgentRuntime",
    "ChatRequest",
    "ModelConfig",
    "TaskContext",
    "blocks_to_markdown",
    "load_agent_config",
]
