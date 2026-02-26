"""Device topology router for QDash API."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from qdash.api.dependencies import get_device_topology_service
from qdash.api.lib.project import ProjectContext, get_project_context
from qdash.api.schemas.device_topology import (
    Device,
    DeviceTopologyRequest,
)
from qdash.api.services.device_topology_service import DeviceTopologyService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/device-topology",
    response_model=Device,
    summary="Get the device topology",
    description="Get the device topology.",
    operation_id="getDeviceTopology",
)
def get_device_topology(
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    request: DeviceTopologyRequest,
    service: Annotated[DeviceTopologyService, Depends(get_device_topology_service)],
) -> Device:
    """Get the quantum device topology with filtered qubits and couplings.

    Constructs a device topology based on calibration data, applying filters
    for qubit/coupling fidelity thresholds and optional time windows. Can
    optionally return only the largest connected component of the device.

    Parameters
    ----------
    ctx : ProjectContext
        Project context with user and project information
    request : DeviceTopologyRequest
        Request containing qubit list, device name/id, filtering conditions,
        and optional list of couplings to exclude
    service : DeviceTopologyService
        Injected device topology service

    Returns
    -------
    Device
        Device topology containing filtered qubits with positions, fidelities,
        lifetimes, gate durations, and couplings with their fidelities

    """
    logger.info(f"project: {ctx.project_id}, user: {ctx.user.username}")
    return service.build_device_topology(ctx.project_id, request)


@router.post(
    "/device-topology/plot",
    response_class=Response,
    summary="Get the device topology plot",
    description="Get the device topology as a PNG image.",
    operation_id="getDeviceTopologyPlot",
)
def get_device_topology_plot(
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    device: Device,
) -> Response:
    """Get the device topology as a PNG image.

    Args:
    ----
        ctx: Project context with user and project information
        device: Device topology data

    Returns:
    -------
        Response: PNG image of the device topology

    """
    logger.info(f"project: {ctx.project_id}, user: {ctx.user.username}")
    plot_bytes = DeviceTopologyService.generate_plot(device.model_dump())
    return Response(content=plot_bytes, media_type="image/png")
