"""Bring-up calibration for MUX-level characterization.

This template runs MUX-level bring-up tasks like resonator spectroscopy.
Bring-up tasks are executed once per MUX, not per qubit.

Example:
    bringup(
        username="alice",
        chip_id="16Q",
        mux_ids=[0, 1, 2, 3],
    )
"""

from typing import Any

from prefect import flow

from qdash.datamodel.one_qubit_execution_mode import OneQubitExecutionMode
from qdash.workflow import TaskCall, sweep  # noqa: F401  # used by commented range overrides below
from qdash.workflow.service import CalibService
from qdash.workflow.service.calib_service import (
    on_flow_cancellation,
    on_flow_crashed,
    on_flow_failure,
)
from qdash.workflow.service.steps import BringUp
from qdash.workflow.service.targets import MuxTargets

# Each call keeps its task-specific acquisition settings, so the shared defaults
# do not replace the values selected for bring-up measurements.
BRINGUP_TASKS: list[TaskCall] = [
    TaskCall(
        name="CheckResonatorSpectroscopy",
        run={
            "shots": 1024,
            "interval": 0,
            # resonator_assignment_order lists the four qid offsets within each MUX
            # in increasing resonator-frequency order. The default is [3, 0, 2, 1].
            # For 16Q, override it with [0, 3, 1, 2] because the order is
            # mux[0] < mux[3] < mux[1] < mux[2].
            # "resonator_assignment_order": [0, 3, 1, 2],
            #
            # The frequency range defaults to the connected readout box's qubex
            # default: low band [5.75, 6.75, 0.002] GHz or high band
            # [9.75, 10.75, 0.002] GHz. The qubex default power range is
            # [-60, 5, 5] dB (stop is exclusive). Leave each range unset to use its
            # default, or uncomment to override it.
            # "frequency_range": sweep.arange(5.75, 6.75, 0.002),
        },
    ),
    TaskCall(
        name="CheckQubitSpectroscopy",
        run={
            "shots": 1024,
            "interval": 1024,
            # The frequency range defaults to the connected control box's qubex
            # default: low band [3.0, 5.75, 0.005] GHz or high band
            # [6.5, 9.75, 0.005] GHz. The qubex default power range is
            # [-60, 0, 5] dB (stop is exclusive). Leave each range unset to use its
            # default, or uncomment to override it.
            # "frequency_range": sweep.arange(3.0, 5.75, 0.005),
            # "power_range": sweep.arange(-60, 0, 10),
        },
    ),
    TaskCall(name="CheckControlAmplitude", run={"shots": 8192}),
    # Keep this explicit so users can see and tune the adaptive Chevron
    # acquisition condition directly from the workflow template.
    TaskCall(
        name="CheckAdaptiveChevron",
        run={"shots": 256},
        # Calibration inputs normally come from the current calibration
        # parameters. Set a value here to override it for every qubit:
        # input={"coarse_control_amplitude": 0.05},
        # Set to False to keep the result as measurement history without
        # updating the current calibration parameters.
        # update_calibration_parameters=False,
    ),
]


@flow(
    on_cancellation=[on_flow_cancellation],
    on_failure=[on_flow_failure],
    on_crashed=[on_flow_crashed],
)
def bringup(
    username: str,
    chip_id: str,
    mux_ids: list[int] | None = None,
    exclude_qids: list[str] | None = None,
    qids: list[str] | None = None,
    execution_mode: OneQubitExecutionMode = "parallel_by_mux",
    tags: list[str] | None = None,
    flow_name: str | None = None,
    project_id: str | None = None,
) -> Any:
    """Bring-up calibration for MUX-level characterization.

    This flow runs MUX-level tasks (e.g., CheckResonatorSpectroscopy) that
    characterize the entire MUX unit. Tasks are executed only for the representative qubit
    (local slot 0) of each MUX.

    Args:
        username: User name (from UI)
        chip_id: Chip ID (from UI)
        mux_ids: MUX IDs to calibrate (required)
        exclude_qids: Qubit IDs to exclude
        qids: Not used (for UI compatibility)
        execution_mode: How the one-qubit targets run (default: "parallel_by_mux"):
            - "parallel_by_mux": MUXes run in parallel within the scheduler's hardware
              stages; the qubits of one MUX run one after another
            - "parallel_by_round": the scheduler forms rounds of qubits from different
              MUXes; the next round starts after every qubit of the round has run
              all of its tasks
            - "sequential": one MUX and one qubit at a time
        flow_name: Flow name (auto-injected)
        project_id: Project ID (auto-injected)

    Returns:
        Pipeline results with bring-up step outputs
    """
    if mux_ids is None:
        raise ValueError("mux_ids is required; select MUX targets before running this flow")
    if exclude_qids is None:
        exclude_qids = []

    targets = MuxTargets(mux_ids=mux_ids, exclude_qids=exclude_qids)

    default_run_parameters: dict[str, Any] = {
        "readout_duration": 1024,
        "interval": 150 * 1024,
    }
    steps = [
        BringUp(
            execution_mode=execution_mode,
            tasks=BRINGUP_TASKS,
        )
    ]

    cal = CalibService(
        username,
        chip_id,
        flow_name=flow_name,
        tags=tags,
        project_id=project_id,
        default_run_parameters=default_run_parameters,
    )
    return cal.run(targets, steps=steps)
