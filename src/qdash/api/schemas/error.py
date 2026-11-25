"""Error response schemas for API endpoints."""

from __future__ import (
    annotations,
)

from fastapi import HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


class ErrorResponse(JSONResponse):
    """Base class for error responses."""


class InternalServerError(HTTPException):
    """Internal server error exception.

    Use this to raise a 500 error from within endpoint handlers.
    """

    def __init__(self, detail: str):
        super().__init__(status_code=500, detail=detail)


class Detail(BaseModel):
    """A simple message response.

    Args:
    ----
        BaseModel: The base class for Pydantic models.

    Attributes:
    ----------
        message (str): The message to return.

    """

    detail: str


class OperationErrorDetail(Detail):
    """Error body of a failed operation.

    ``detail`` is a message safe to show users. An unexpected failure also carries ``code``,
    naming the failed operation, and ``error_id``, the ID under which the server logged the
    cause; endpoints that do not report one yet return ``detail`` alone.
    """

    code: str | None = Field(
        default=None,
        description="Stable code of the failed operation, e.g. file_read_failed",
    )
    error_id: str | None = Field(
        default=None,
        description="Opaque ID of the server log entry recording the cause",
    )


class BadRequestResponse(ErrorResponse):
    """Represents a response for a bad request.

    Args:
    ----
        detail (str): The detailed error message.

    Attributes:
    ----------
        status_code (int): The HTTP status code for the response.
        content (dict): The content of the response.

    """

    def __init__(
        self,
        detail: str,
    ):
        super().__init__(
            status_code=400,
            content={"detail": detail},
        )


class InternalServerErrorResponse(ErrorResponse):
    """Represents an internal server error response.

    Args:
    ----
        detail (str): The error message or details of the internal server error.

    Attributes:
    ----------
        status_code (int): The HTTP status code for the internal server error response.
        content (dict): The content of the internal server error response, containing the error detail.

    """

    def __init__(
        self,
        detail: str,
    ):
        super().__init__(
            status_code=500,
            content={"detail": detail},
        )


class NotFoundErrorResponse(ErrorResponse):
    """Represents an error response for a resource not found.

    Args:
    ----
        detail (str): The detailed error message.

    Attributes:
    ----------
        status_code (int): The HTTP status code of the error response.
        content (dict): The content of the error response.

    """

    def __init__(
        self,
        detail: str,
    ):
        super().__init__(
            status_code=404,
            content={"detail": detail},
        )


class ConflictErrorResponse(ErrorResponse):
    """Represents an error response for a conflict (HTTP status code 409).

    Args:
    ----
        detail (str): The detailed error message.

    Attributes:
    ----------
        status_code (int): The HTTP status code for the error response (409).
        content (dict): The content of the error response, containing the detail message.

    """

    def __init__(
        self,
        detail: str,
    ):
        super().__init__(
            status_code=409,
            content={"detail": detail},
        )
