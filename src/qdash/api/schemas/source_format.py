"""Schemas for formatting Python source in the Workflow and metric script editors."""

from typing import Literal

from pydantic import BaseModel, Field

from qdash.api.lib.python_format import MAX_FORMAT_SOURCE_BYTES


class FormatSourceRequest(BaseModel):
    """Python source to format; nothing is saved or executed."""

    source: str = Field(
        ..., max_length=MAX_FORMAT_SOURCE_BYTES, description="Python source (≤ 512 KiB)"
    )


class FormatSourceDiagnostic(BaseModel):
    """Why the source could not be formatted."""

    message: str
    line: int | None = None
    column: int | None = None


class FormatSourceResponse(BaseModel):
    """The source formatted with Ruff, or the input unchanged when it cannot be parsed."""

    status: Literal["formatted", "unchanged", "syntax_error"] = Field(
        ...,
        description=(
            "formatted: source differs from the input; unchanged: the input is already"
            " formatted; syntax_error: the input cannot be parsed and is returned as given"
        ),
    )
    source: str = Field(..., description="Formatted source, or the input on a syntax error")
    diagnostic: FormatSourceDiagnostic | None = Field(
        default=None, description="Location of the syntax error that prevented formatting"
    )
