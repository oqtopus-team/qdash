"""Schema definitions for execution router."""

from pydantic import BaseModel


class ExecutionLockStatusResponse(BaseModel):
    """Response model for the fetch_execution_lock_status endpoint."""

    lock: bool
