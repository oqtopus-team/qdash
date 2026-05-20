"""Shared Copilot package used by the API and workflow worker.

Package layout:

- ``agent``: public LLM-agent entrypoint
- ``runtime``: public data/runtime entrypoint
- ``config``: configuration models and loaders
- ``contracts``: request/response models shared across layers
- ``prompts`` / ``tooling`` / ``services``: implementation details grouped by role
"""

from qdash.copilot.agent import blocks_to_markdown, run_analysis, run_chat
from qdash.copilot.config import CopilotConfig, ModelConfig, load_copilot_config
from qdash.copilot.contracts import AnalysisResponse, ChatRequest, TaskAnalysisContext
from qdash.copilot.runtime import CopilotRuntime

__all__ = [
    "AnalysisResponse",
    "ChatRequest",
    "CopilotConfig",
    "CopilotRuntime",
    "ModelConfig",
    "TaskAnalysisContext",
    "blocks_to_markdown",
    "load_copilot_config",
    "run_analysis",
    "run_chat",
]
