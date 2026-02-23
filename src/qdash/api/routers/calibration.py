"""Calibration router for QDash API."""

from logging import getLogger
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from qdash.api.dependencies import get_calibration_service, get_seed_import_service
from qdash.api.lib.project import ProjectContext, get_project_context
from qdash.api.schemas.calibration import (
    CalibrationNoteResponse,
    SeedImportRequest,
    SeedImportResponse,
)
from qdash.api.services.calibration_service import CalibrationService
from qdash.api.services.seed_import_service import SeedImportService

router = APIRouter()
logger = getLogger("uvicorn.app")


@router.get(
    "/calibrations/note",
    response_model=CalibrationNoteResponse,
    summary="Get the calibration note",
    operation_id="getCalibrationNote",
)
def get_calibration_note(
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    calibration_service: Annotated[CalibrationService, Depends(get_calibration_service)],
) -> CalibrationNoteResponse:
    """Get the latest calibration note for the master task.

    Retrieves the most recent calibration note from the database, sorted by timestamp
    in descending order. The note contains metadata about calibration parameters
    and configuration.

    Parameters
    ----------
    ctx : ProjectContext
        Project context with user and project information
    calibration_service : CalibrationService
        Service for calibration operations

    Returns
    -------
    CalibrationNoteResponse
        The latest calibration note containing username, execution_id, task_id,
        note content, and timestamp

    Raises
    ------
    HTTPException
        404 if no calibration note is found

    """
    logger.info(f"project: {ctx.project_id}, user: {ctx.user.username}")
    note = calibration_service.get_latest_note(ctx.project_id)
    if note is None:
        raise HTTPException(status_code=404, detail="Calibration note not found")
    return note


@router.post(
    "/calibrations/seed-import",
    response_model=SeedImportResponse,
    summary="Import seed parameters from qubex or manual input",
    operation_id="importSeedParameters",
)
def import_seed_parameters(
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[SeedImportService, Depends(get_seed_import_service)],
    request: SeedImportRequest,
) -> SeedImportResponse:
    """Import initial calibration parameters from qubex params or manual input.

    This endpoint allows importing seed parameters that are typically loaded
    from qubex's params directory (e.g., qubit_frequency, readout_amplitude)
    into QDash's calibration database for tracking and provenance.

    Parameters
    ----------
    ctx : ProjectContext
        Project context with user and project information
    service : SeedImportService
        Service for seed import operations
    request : SeedImportRequest
        Import request specifying source, chip_id, and parameters

    Returns
    -------
    SeedImportResponse
        Results of the import operation including counts and individual results

    Examples
    --------
    Import from qubex params:
    ```json
    {
        "chip_id": "64Qv3",
        "source": "qubex_params",
        "parameters": ["qubit_frequency", "readout_amplitude"]
    }
    ```

    Manual import:
    ```json
    {
        "chip_id": "64Qv3",
        "source": "manual",
        "manual_data": {
            "qubit_frequency": {"Q00": 7.9, "Q01": 8.6}
        }
    }
    ```

    """
    logger.info(
        f"Seed import: project={ctx.project_id}, user={ctx.user.username}, "
        f"chip={request.chip_id}, source={request.source}"
    )
    return service.import_seeds(
        request=request,
        project_id=ctx.project_id,
        username=ctx.user.username,
    )


@router.get(
    "/calibrations/seed-parameters/{chip_id}",
    response_model=list[str],
    summary="Get available seed parameters for a chip",
    operation_id="getAvailableSeedParameters",
)
def get_available_seed_parameters(
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[SeedImportService, Depends(get_seed_import_service)],
    chip_id: str,
) -> list[str]:
    """Get list of available parameter files in qubex params directory.

    Parameters
    ----------
    ctx : ProjectContext
        Project context with user and project information
    service : SeedImportService
        Service for seed import operations
    chip_id : str
        Chip ID to check parameters for

    Returns
    -------
    list[str]
        List of available parameter names (e.g., ["qubit_frequency", "readout_amplitude"])

    """
    return service.get_available_parameters(chip_id)


@router.get(
    "/calibrations/seed-compare/{chip_id}",
    summary="Compare YAML seed values with QDash values",
    operation_id="compareSeedValues",
)
def compare_seed_values(
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[SeedImportService, Depends(get_seed_import_service)],
    chip_id: str,
    parameters: str | None = None,
) -> dict[str, Any]:
    """Compare seed parameter values from YAML files with current QDash values.

    This endpoint allows users to preview what will be imported and see
    the difference between YAML source values and current QDash values.

    Parameters
    ----------
    ctx : ProjectContext
        Project context with user and project information
    service : SeedImportService
        Service for seed import operations
    chip_id : str
        Chip ID to compare parameters for
    parameters : str | None
        Comma-separated list of parameters to compare (None = all available)

    Returns
    -------
    dict
        Comparison data with structure:
        {
            "chip_id": str,
            "parameters": {
                "param_name": {
                    "unit": str,
                    "qubits": {
                        "Q0": {
                            "yaml_value": float | None,
                            "qdash_value": float | None,
                            "status": "new" | "same" | "different"
                        }
                    }
                }
            }
        }

    """
    param_list = parameters.split(",") if parameters else None
    return service.compare_seed_values(
        chip_id=chip_id,
        project_id=ctx.project_id,
        username=ctx.user.username,
        parameters=param_list,
    )
