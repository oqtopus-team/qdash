"""Schema definitions for tag router."""

from pydantic import BaseModel


class Tag(BaseModel):
    """Response model for a tag."""

    name: str


class ListTagResponse(BaseModel):
    """Response model for a list of tags."""

    tags: list[Tag]
