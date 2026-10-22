"""Minimal GE pulse setup followed by EF-transition calibration.

This flow does not require pre-calibrated GE Rabi, HPI, or DRAG pulses. It starts
from an existing GE control frequency and readout frequency/amplitude, calibrates
the GE Rabi and HPI pulse, then calibrates the EF frequency, pulses, and three-state
readout classifier in the same synchronized Qubex session.

CheckEFRabi currently lets Qubex select the GE preparation pulse. Existing GE PI
or DRAG pulses can take precedence over the HPI calibrated by this flow, so the
recorded HPI inputs alone do not fully determine the EF Rabi preparation pulse.

Example:
    ef_calibration(username="alice", chip_id="64Qv3", qids=["0", "1"])
"""

from typing import Any, Literal

from prefect import flow

from qdash.workflow.service import CalibService
from qdash.workflow.service.calib_service import (
    on_flow_cancellation,
    on_flow_crashed,
    on_flow_failure,
)
from qdash.workflow.service.steps import CustomOneQubit
from qdash.workflow.service.targets import MuxTargets, QubitTargets, Target

EF_CALIBRATION_TASKS: list[str] = [
    "ConfigureEF",
    "CheckRabi",
    "CreateHPIPulse",
    "CheckAdaptiveEFChevron",
    "CheckEFRabi",
    "CreateEFHPIPulse",
    "CreateEFPIPulse",
    "EFReadoutClassification",
]


@flow(
    on_cancellation=[on_flow_cancellation],
    on_failure=[on_flow_failure],
    on_crashed=[on_flow_crashed],
)
def ef_calibration(
    username: str,
    chip_id: str,
    mux_ids: list[int] | None = None,
    exclude_qids: list[str] | None = None,
    qids: list[str] | None = None,
    configuration_mode: Literal["ge-ef-cr", "ge-ef-fh"] = "ge-ef-cr",
    tags: list[str] | None = None,
    flow_name: str | None = None,
    project_id: str | None = None,
) -> Any:
    """Build the minimum GE pulse context and run the complete EF calibration.

    Args:
        username: User name (from UI)
        chip_id: Chip ID (from UI)
        mux_ids: MUX IDs to calibrate using MUX-based scheduling
        exclude_qids: Qubit IDs to exclude when using mux_ids
        qids: Qubit IDs to calibrate when mux_ids is not set
        configuration_mode: EF control layout, either ge-ef-cr or ge-ef-fh
        tags: Flow tags
        flow_name: Flow name (auto-injected)
        project_id: Project ID (auto-injected)

    Returns:
        Pipeline results with EF calibration output
    """
    targets: Target
    if mux_ids is not None:
        targets = MuxTargets(mux_ids=mux_ids, exclude_qids=exclude_qids or [])
    elif qids is not None:
        targets = QubitTargets(qids=qids)
    else:
        raise ValueError("mux_ids or qids is required; select targets before running this flow")

    steps = [
        CustomOneQubit(
            step_name="ef_calibration",
            tasks=EF_CALIBRATION_TASKS,
            mode="synchronized",
        )
    ]

    cal = CalibService(
        username,
        chip_id,
        flow_name=flow_name,
        tags=tags,
        project_id=project_id,
        task_parameters={
            "ConfigureEF": {
                "run": {
                    "configuration_mode": {"value": configuration_mode, "value_type": "str"},
                },
            },
            "CreateHPIPulse": {
                "run": {
                    "hpi_duration": {"value": 32, "value_type": "int"},
                },
            },
            "CheckAdaptiveEFChevron": {
                "run": {
                    "shots": {"value": 256, "value_type": "int"},
                },
            },
            "CreateEFHPIPulse": {
                "run": {
                    "ef_hpi_duration": {"value": 32, "value_type": "int"},
                },
            },
            "CreateEFPIPulse": {
                "run": {
                    "ef_pi_duration": {"value": 32, "value_type": "int"},
                },
            },
        },
        default_run_parameters={
            "readout_duration": {"value": 1024, "value_type": "int"},
            "interval": {"value": 150 * 1024, "value_type": "int"},
        },
    )
    return cal.run(targets, steps=steps)
