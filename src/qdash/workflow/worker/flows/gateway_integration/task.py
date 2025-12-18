import json
import logging
import os
from pathlib import Path
from typing import Any

import requests  # type: ignore[import-untyped]
from prefect import task
from pydantic import BaseModel, Field
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.initialize import initialize

# Get API URL from environment variable with default
API_PORT = os.getenv("API_PORT", "6004")
API_URL = f"http://api:{API_PORT}/api"


logging.basicConfig(level=logging.INFO)
logging.info(f"Using QDash API base URL: {API_URL}")


class FidelityCondition(BaseModel):
    """Condition for fidelity filtering."""

    min: float
    max: float
    is_within_24h: bool = True


class Condition(BaseModel):
    """Condition for filtering device topology."""

    coupling_fidelity: FidelityCondition
    qubit_fidelity: FidelityCondition
    readout_fidelity: FidelityCondition
    only_maximum_connected: bool = True


class DeviceTopologyRequest(BaseModel):
    """Request model for device topology."""

    name: str = "anemone"
    device_id: str = "anemone"
    qubits: list[str] = []
    exclude_couplings: list[str] = []
    condition: Condition = Field(
        default_factory=lambda: Condition(
            coupling_fidelity=FidelityCondition(min=0.7, max=1.0, is_within_24h=True),
            qubit_fidelity=FidelityCondition(min=0.9, max=1.0, is_within_24h=False),
            readout_fidelity=FidelityCondition(min=0.6, max=1.0, is_within_24h=True),
            only_maximum_connected=True,
        )
    )


# Headers for all requests
headers = {"accept": "application/json", "X-Username": "admin", "Content-Type": "application/json"}


@task
def generate_device_topology_request(
    request: DeviceTopologyRequest, save_path: Path
) -> DeviceTopologyRequest:
    """Generate and return the device topology request data."""
    logging.info("Generating device topology request data...")
    initialize()
    chip = ChipDocument.get_current_chip("admin")
    # Define request data using Pydantic model
    if chip is None:
        msg = "No current chip found in the database."
        raise ValueError(msg)
    for qid, qubit in chip.qubits.items():
        if qubit.get_qubit_frequency() is not None:
            request.qubits.append(qid)
    save_path = save_path / "device_topology_request.json"
    # Save request data to file
    with Path(save_path).open("w") as f:
        json.dump(request.model_dump(), f, indent=2)
    return request


@task
def post_device_topology(request: DeviceTopologyRequest, save_path: Path) -> dict[str, Any]:
    """Post device topology data and save response."""
    logging.info("Posting device topology data...")

    # Make POST request using hardcoded request_data
    response = requests.post(
        f"{API_URL}/device_topology", headers=headers, json=request.model_dump(), timeout=10
    )
    response.raise_for_status()
    # Save response to file
    save_path = save_path / "device_topology.json"
    with Path(save_path).open("w") as f:
        json.dump(response.json(), f, indent=2)

    return dict(response.json())


@task
def generate_topology_plot(topology_data: dict[str, Any], save_path: Path) -> None:
    """Generate device topology plot."""
    logging.info("Generating device topology plot...")

    # Update headers for image response
    plot_headers = headers.copy()
    plot_headers["accept"] = "*/*"

    # Make POST request
    response = requests.post(
        f"{API_URL}/device_topology/plot", headers=plot_headers, json=topology_data, timeout=10
    )
    response.raise_for_status()

    save_path = save_path / "device_topology.png"
    logging.info(f"Saving plot to {save_path}")
    # Save plot to file
    with Path(save_path).open("wb") as f:
        f.write(response.content)
