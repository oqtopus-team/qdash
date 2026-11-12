"""Topology API router for device topology configuration."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from qdash.common.config.topology import (
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
        dict: Complete topology definition with qubits, couplings and the
        normalized ``muxes`` (MUX ID to member qubits in local slot order).
        Qubits that no MUX lists are standalone. Legacy ``mux`` templates are
        normalized too, and ``muxes_source`` says which format the template
        used, so every client renders the same membership the schedulers use.
        ``mux_slots`` maps each multiplexed qubit to its hardware slot; legacy
        slot gaps are preserved and can differ from normalized array indices.

    """
    try:
        topology = load_topology(topology_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        # Pydantic validation errors subclass ValueError: the template itself is broken.
        logger.warning("Invalid topology %s: %s", topology_id, e)
        raise HTTPException(status_code=422, detail=f"Invalid topology {topology_id}: {e}") from e
    data = topology.model_dump()
    data["mux_slots"] = topology.mux_slots()
    data["standalone_qubits"] = topology.standalone_qubits()
    return {"data": data}
