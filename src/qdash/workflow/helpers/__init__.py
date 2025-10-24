"""Workflow helper functions and utilities for Python Flow Editor."""

from qdash.workflow.helpers.flow_helpers import (
    FlowSession,
    execute_schedule,
    finish_calibration,
    generate_execution_id,
    get_session,
    init_calibration,
)
from qdash.workflow.helpers.parallel_helpers import calibrate_parallel, parallel_map

__all__ = [
    # === Session Management ===
    "FlowSession",
    "init_calibration",
    "get_session",
    "finish_calibration",
    "generate_execution_id",
    # === Parallel Execution (Recommended) ===
    "calibrate_parallel",  # True parallel execution across qubits using @task + submit
    "parallel_map",  # Generic parallel map for custom logic with Prefect UI visibility
    # === Schedule-based Execution ===
    "execute_schedule",  # Custom orchestration using SerialNode/ParallelNode/BatchNode
]
