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

from qdash.workflow import TaskCall
from qdash.workflow.service import CalibService
from qdash.workflow.service.calib_service import (
    on_flow_cancellation,
    on_flow_crashed,
    on_flow_failure,
)
from qdash.workflow.service.steps import CustomOneQubit
from qdash.workflow.service.targets import MuxTargets, QubitTargets, Target

ConfigurationMode = Literal["ge-ef-cr", "ge-ef-fh"]


def ef_calibration_tasks(configuration_mode: ConfigurationMode) -> list[TaskCall]:
    """Build the EF calibration calls for one flow run.

    ConfigureEF takes the run's configuration mode, so the list is built per run
    instead of shared as a module constant.
    """
    return [
        TaskCall(name="ConfigureEF", run={"configuration_mode": configuration_mode}),
        TaskCall(name="CheckRabi"),
        TaskCall(name="CreateHPIPulse", run={"hpi_duration": 32}),
        TaskCall(name="CheckAdaptiveEFChevron", run={"shots": 256}),
        TaskCall(name="CheckEFRabi"),
        TaskCall(name="CreateEFHPIPulse", run={"ef_hpi_duration": 32}),
        TaskCall(name="CreateEFPIPulse", run={"ef_pi_duration": 32}),
        TaskCall(name="EFReadoutClassification"),
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
    configuration_mode: ConfigurationMode = "ge-ef-cr",
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
            tasks=ef_calibration_tasks(configuration_mode),
            mode="synchronized",
        )
    ]

    cal = CalibService(
        username,
        chip_id,
        flow_name=flow_name,
        tags=tags,
        project_id=project_id,
        default_run_parameters={
            "readout_duration": 1024,
            "interval": 150 * 1024,
        },
    )
    return cal.run(targets, steps=steps)
