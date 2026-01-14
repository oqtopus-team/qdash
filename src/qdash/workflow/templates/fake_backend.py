"""Fake backend calibration flow template.

Template for testing calibration workflows without real quantum hardware.
Demonstrates how to switch between backends using CalibService.

Backend Switching:
    - backend_name="fake": Use simulated measurements (no hardware required)
    - backend_name="qubex": Use real quantum hardware via qubex library
    - backend_name=None: Use default from config/backend.yaml

Available Fake Tasks (same names as qubex for seamless switching):
    - ChevronPattern: Entry point, outputs qubit_frequency, readout_frequency
    - CreateHPIPulse: Depends on qubit_frequency, outputs hpi_amplitude, hpi_length
    - CheckRabi: Depends on qubit_frequency
    - CheckRamsey: Depends on qubit_frequency, hpi_amplitude
    - CheckT1: Depends on qubit_frequency, hpi_amplitude
    - CheckT2Echo: Depends on qubit_frequency, hpi_amplitude
    - RandomizedBenchmarking: Depends on qubit_frequency, rabi_amplitude, t1, t2_echo

Example:
    # Test with fake backend (default tasks)
    fake_calibration(
        username="alice",
        chip_id="64Qv3",
        qids=["0", "1"],
        backend_name="fake",
    )

    # Test provenance chain with all tasks
    fake_calibration(
        username="alice",
        chip_id="64Qv3",
        qids=["0", "1"],
        backend_name="fake",
        tasks=["ChevronPattern", "CheckRabi", "CheckT1", "CheckT2Echo", "RandomizedBenchmarking"],
    )

    # Switch to production (qubex)
    fake_calibration(
        username="alice",
        chip_id="64Qv3",
        qids=["0", "1"],
        backend_name="qubex",
    )
"""

from typing import Any

from prefect import flow
from qdash.workflow.service import CalibService
from qdash.workflow.service.steps import CustomOneQubit
from qdash.workflow.service.targets import QubitTargets


@flow
def fake_calibration(
    username: str,
    chip_id: str,
    qids: list[str] | None = None,
    tasks: list[str] | None = None,
    backend_name: str | None = None,
    flow_name: str | None = None,
    project_id: str | None = None,
) -> Any:
    """Calibration flow with backend switching support.

    Args:
        username: User name (from UI)
        chip_id: Chip ID (from UI)
        qids: Qubit IDs to calibrate (default: ["0", "1", "2", "3"])
        tasks: Task names to run. Default: ["ChevronPattern", "CheckRabi", "CheckT1", "CheckT2Echo"]
               For full provenance test, add "RandomizedBenchmarking".
        backend_name: Backend to use ("fake" for testing, "qubex" for production,
                      None for default from backend.yaml)
        flow_name: Flow name (auto-injected)
        project_id: Project ID (auto-injected)

    Returns:
        Pipeline results
    """
    if qids is None:
        qids = ["0", "1", "2", "3"]

    if tasks is None:
        tasks = [
            "ChevronPattern",
            "CreateHPIPulse",
            "CheckRabi",
            "CheckT1",
            "CheckT2Echo",
        ]

    targets = QubitTargets(qids=qids)
    steps = [
        CustomOneQubit(step_name="calibration", tasks=tasks),
    ]

    cal = CalibService(
        username,
        chip_id,
        backend_name=backend_name,
        flow_name=flow_name,
        project_id=project_id,
    )
    return cal.run(targets, steps=steps)
