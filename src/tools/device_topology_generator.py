import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

import requests
from pydantic import BaseModel, Field

# Get API URL from environment variable with default
API_URL = os.getenv("QDASH_API_URL", "http://localhost:6004/api")


logging.basicConfig(level=logging.INFO)
logging.info(f"Using QDash API base URL: {API_URL}")


class FidelityCondition(BaseModel):
    """Model for fidelity conditions with min and max values."""

    min: float = Field(ge=0.0, le=1.0)
    max: float = Field(ge=0.0, le=1.0)


class TopologyCondition(BaseModel):
    """Model for device topology conditions."""

    coupling_fidelity: FidelityCondition
    qubit_fidelity: FidelityCondition
    only_maximum_connected: bool


class DeviceTopologyRequest(BaseModel):
    """Model for device topology request data."""

    name: str
    device_id: str
    qubits: list[str]
    exclude_couplings: list[str]
    condition: TopologyCondition


# Define request data using Pydantic model
request_data = DeviceTopologyRequest(
    name="anemone",
    device_id="anemone",
    qubits=[
        "0",
        "1",
        "2",
        "3",
        "4",
        "5",
        "6",
        "7",
        "8",
        "9",
        "10",
        "11",
        "12",
        "13",
        "14",
        "15",
        "16",
        "17",
        "18",
        "19",
        "20",
        "21",
        "22",
        "23",
        "24",
        "25",
        "26",
        "27",
        "28",
        "29",
        "30",
        "31",
        "32",
        "33",
        "34",
        "35",
        "36",
        "37",
        "38",
        "39",
        "40",
        "41",
        "42",
        "43",
        "44",
        "45",
        "46",
        "47",
        "48",
        "49",
        "50",
        "51",
        "52",
        "53",
        "54",
        "55",
        "56",
        "57",
        "58",
        "59",
        "60",
        "61",
        "62",
        "63",
    ],
    exclude_couplings=[],
    condition=TopologyCondition(
        coupling_fidelity=FidelityCondition(min=0.3, max=1.0),
        qubit_fidelity=FidelityCondition(min=0.9, max=1.0),
        only_maximum_connected=True,
    ),
)


# Headers for all requests
headers = {"accept": "application/json", "X-Username": "admin", "Content-Type": "application/json"}


def post_device_topology() -> dict[str, Any]:
    """Post device topology data and save response."""
    logging.info("Posting device topology data...")

    # Make POST request using hardcoded request_data
    response = requests.post(
        f"{API_URL}/device_topology", headers=headers, json=request_data.model_dump(), timeout=10
    )
    response.raise_for_status()
    # Save response to file
    with Path("./device_topology.json").open("w") as f:
        json.dump(response.json(), f, indent=2)

    return dict(response.json())


def generate_topology_plot(topology_data: dict[str, Any]) -> None:
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

    # Save plot to file
    with Path("./device_topology.png").open("wb") as f:
        f.write(response.content)


def main() -> None:
    """Post topology data and generate plot."""
    try:
        # Post topology data and get response
        topology_data = post_device_topology()

        # Generate and save plot
        generate_topology_plot(topology_data)

        logging.info("Process complete. 'device_topology.png' has been created.")
        sys.exit(1)
    except Exception as e:
        logging.error(f"Unexpected error: {e!s}")
        sys.exit(1)


if __name__ == "__main__":
    main()
