"""Topology API router for device topology configuration."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from qdash.common.topology_config import (
    list_topologies,
    load_topology,
)

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/list", summary="List available topologies", operation_id="listTopologies")
async def get_topology_list(size: int | None = None) -> dict[str, Any]:
    """List all available topology definitions.

    Args:
    ----
        size: Optional filter by number of qubits

    Returns:
    -------
        dict: List of topology summaries with id, name, and num_qubits

    """
    return {"topologies": list_topologies(size=size)}


@router.get("/{topology_id}", summary="Get topology by ID", operation_id="getTopologyById")
async def get_topology(topology_id: str) -> dict[str, Any]:
    """Get a specific topology definition.

    Args:
    ----
        topology_id: Topology identifier (e.g., "square-lattice-mux-64")

    Returns:
    -------
        dict: Complete topology definition with qubits and couplings

    """
    try:
        topology = load_topology(topology_id)
        return {"data": topology.model_dump()}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
