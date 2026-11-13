"""Shared Copilot package used by the API.

Package layout:

- ``runtime``: data loading for a chat about one task result
- ``config``: configuration models and loaders
- ``contracts``: request/response models shared across layers
- ``prompts`` / ``tooling`` / ``services``: implementation details grouped by role
- ``blocks``: the answer format rendered as markdown for issue and forum replies
"""

from qdash.copilot.blocks import blocks_to_markdown
from qdash.copilot.config import CopilotConfig, ModelConfig, load_copilot_config
from qdash.copilot.contracts import ChatRequest, TaskContext
from qdash.copilot.runtime import CopilotRuntime

__all__ = [
    "ChatRequest",
    "CopilotConfig",
    "CopilotRuntime",
    "ModelConfig",
    "TaskContext",
    "blocks_to_markdown",
    "load_copilot_config",
]
