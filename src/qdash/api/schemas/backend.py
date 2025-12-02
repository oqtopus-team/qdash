"""Schema definitions for backend router."""

from pydantic import BaseModel


class BackendResponseModel(BaseModel):
    """Response model for backend operations.

    Inherits from BackendModel and is used to format the response
    for backend-related API endpoints.
    """

    name: str
    username: str


class ListBackendsResponse(BaseModel):
    """Response model for listing all backends.

    Wraps list of backends for API consistency and future extensibility.
    """

    backends: list[BackendResponseModel]
