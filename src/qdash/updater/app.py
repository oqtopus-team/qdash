"""FastAPI application for the privileged host-side updater."""

from fastapi import FastAPI, HTTPException, status

from qdash.updater.models import StartUpdateRequest, UpdateOperation, UpdateStatus
from qdash.updater.service import UpdateBlockedError, UpdaterService, UpdaterSettings

app = FastAPI(title="QDash Updater", docs_url=None, redoc_url=None, openapi_url=None)
service = UpdaterService(UpdaterSettings.from_env())


@app.get("/health")
def get_health() -> dict[str, str]:
    """Report updater process liveness without exposing privileged state."""
    return {"status": "ok"}


@app.get("/status", response_model=UpdateStatus)
async def get_status() -> UpdateStatus:
    """Return current and latest stable QDash versions."""
    return await service.get_status()


@app.post(
    "/updates",
    response_model=UpdateOperation,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_update(request: StartUpdateRequest) -> UpdateOperation:
    """Queue installation of the latest safe stable release."""
    try:
        return await service.start_update(request.expected_current_version)
    except UpdateBlockedError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@app.get(
    "/updates/{operation_id}",
    response_model=UpdateOperation,
)
def get_update(operation_id: str) -> UpdateOperation:
    """Return progress for an update operation."""
    operation = service.get_operation(operation_id)
    if operation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Update not found")
    return operation
