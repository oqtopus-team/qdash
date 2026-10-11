"""Pydantic models for Copilot prompt-builder boundaries."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from qdash.copilot.contracts import TaskContext


class TaskChatPromptOptions(BaseModel):
    """Normalized inputs for rendering the prompt of a chat about one task result."""

    context: TaskContext
    language_instruction: str
    has_expected_images: bool = False
    has_experiment_image: bool = False


def _rebuild_models() -> None:
    from qdash.copilot.contracts import TaskContext as _TaskContext

    TaskChatPromptOptions.model_rebuild(_types_namespace={"TaskContext": _TaskContext})


_rebuild_models()
