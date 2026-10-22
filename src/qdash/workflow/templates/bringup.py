"""Bring-up calibration for MUX-level characterization.

This template configures selected MUXes, then runs MUX-level bring-up tasks like
resonator spectroscopy. Bring-up tasks are executed once per MUX, not per qubit.

Example:
    bringup(
        username="alice",
        chip_id="16Q",
        mux_ids=[0, 1, 2, 3],
    )
"""

from typing import Any

from prefect import flow

from qdash.workflow.service import CalibService
from qdash.workflow.service.calib_service import (
    on_flow_cancellation,
    on_flow_crashed,
    on_flow_failure,
)
from qdash.workflow.service.steps import BringUp, ConfigureAll
from qdash.workflow.service.targets import MuxTargets

BRINGUP_TASKS: list[str] = [
    "CheckResonatorSpectroscopy",
    "CheckQubitSpectroscopy",
    "CheckControlAmplitude",
    "CheckAdaptiveChevron",
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
    mode: str = "scheduled",
    tags: list[str] | None = None,
    flow_name: str | None = None,
    project_id: str | None = None,
) -> Any:
    """Bring-up calibration for MUX-level characterization.

    This flow first pushes the current configuration to the selected MUXes, then
    runs MUX-level tasks (e.g., CheckResonatorSpectroscopy) that characterize the
    entire MUX unit. Tasks are executed only for the representative qubit
    (qid % 4 == 0) of each MUX.

    Args:
        username: User name (from UI)
        chip_id: Chip ID (from UI)
        mux_ids: MUX IDs to calibrate (required)
        exclude_qids: Qubit IDs to exclude
        qids: Not used (for UI compatibility)
        mode: Execution mode:
            - "scheduled": Box-based parallelism with hardware constraints (default)
            - "serial": Fully sequential execution (one MUX at a time)
            - "synchronized": Step-based synchronized execution
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
        "readout_duration": {"value": 1024, "value_type": "int"},
        "interval": {"value": 150 * 1024, "value_type": "int"},
    }
    task_parameters: dict[str, dict[str, Any]] = {
        # Preserve task-specific acquisition settings instead of allowing shared
        # defaults to replace the values selected for bring-up measurements.
        "CheckResonatorSpectroscopy": {
            "run": {
                "shots": 1024,
                "interval": 0,
            },
        },
        "CheckQubitSpectroscopy": {
            "run": {
                "shots": 1024,
                "interval": 1024,
            },
        },
        "CheckControlAmplitude": {
            "run": {
                "shots": 8192,
            },
        },
        # Keep this explicit so users can see and tune the adaptive Chevron
        # acquisition condition directly from the workflow template.
        "CheckAdaptiveChevron": {
            "run": {
                "shots": 256,
            },
            # Calibration inputs normally come from the current calibration
            # parameters. Set a value here to override it for every qubit:
            # "input": {
            #     "coarse_control_amplitude": 0.05,
            # },
            # Set to False to keep the result as measurement history without
            # updating the current calibration parameters.
            # "update_calibration_parameters": False,
        },
        # resonator_assignment_order lists the four qid offsets within each MUX
        # in increasing resonator-frequency order. The default is [3, 0, 2, 1].
        # For 16Q, override it with [0, 3, 1, 2] because the order is
        # mux[0] < mux[3] < mux[1] < mux[2].
        #
        # CheckResonatorSpectroscopy uses the connected readout box's qubex default:
        # low band [5.75, 6.75, 0.002] GHz or high band [9.75, 10.75, 0.002] GHz.
        # Its qubex default power range is [-60, 5, 5] dB (stop is exclusive).
        # Leave each range unset to use its default, or add these keys to the "run"
        # entry of CheckResonatorSpectroscopy above to override it.
        #     "resonator_assignment_order": [0, 3, 1, 2],
        #     "frequency_range": [5.75, 6.75, 0.002],
        # CheckQubitSpectroscopy uses the connected control box's qubex default:
        # low band [3.0, 5.75, 0.005] GHz or high band [6.5, 9.75, 0.005] GHz.
        # Its qubex default power range is [-60, 0, 5] dB (stop is exclusive).
        # Leave frequency_range unset to use that default, or add these keys to the
        # "run" entry of CheckQubitSpectroscopy above to override it.
        #     "frequency_range": [3.0, 5.75, 0.005],
        #     "power_range": [-60, 0, 10],
    }
    steps = [
        ConfigureAll(),
        BringUp(mode=mode, tasks=BRINGUP_TASKS),
    ]

    cal = CalibService(
        username,
        chip_id,
        flow_name=flow_name,
        tags=tags,
        project_id=project_id,
        default_run_parameters=default_run_parameters,
        task_parameters=task_parameters,
    )
    return cal.run(targets, steps=steps)
