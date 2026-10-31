"""Box setup for selected MUXes with capture delay correction.

This template runs CorrectCaptureDelay once per MUX. The task centers the readout pulse in the
capture window and writes capture_delay.yaml, plus capture_delay_word.yaml on
QuEL-1. Its figures show the delay sweep before correction and the capture
after it. QuEL-1 and QuEL-3 chips are supported.

Run it first, before resonator spectroscopy: it uses a fixed readout tone and
does not require calibrated readout parameters. Later steps and flows start new
Qubex sessions that reload the params files, so they use the corrected delays.

Example:
    box_setup(
        username="alice",
        chip_id="64Qv3",
        mux_ids=[0, 1, 2, 3],
    )
"""

from typing import Any

from prefect import flow

from qdash.workflow import sweep
from qdash.workflow.service import CalibService
from qdash.workflow.service.calib_service import (
    on_flow_cancellation,
    on_flow_crashed,
    on_flow_failure,
)
from qdash.workflow.service.steps import BringUp
from qdash.workflow.service.targets import MuxTargets


@flow(
    on_cancellation=[on_flow_cancellation],
    on_failure=[on_flow_failure],
    on_crashed=[on_flow_crashed],
)
def box_setup(
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
    """Configure the selected MUXes and correct their QuEL-1 or QuEL-3 capture delays.

    Args:
        username: User name (from UI)
        chip_id: Chip ID (from UI)
        mux_ids: MUX IDs to correct (required)
        exclude_qids: Qubit IDs to exclude
        qids: Not used (for UI compatibility)
        mode: Execution mode:
            - "scheduled": Box-based parallelism with hardware constraints (default)
            - "serial": Fully sequential execution (one MUX at a time)
            - "synchronized": Step-based synchronized execution
        tags: Flow tags
        flow_name: Flow name (auto-injected)
        project_id: Project ID (auto-injected)

    Returns:
        Pipeline results with the corrected delays
    """
    if mux_ids is None:
        raise ValueError("mux_ids is required; select MUX targets before running this flow")
    if exclude_qids is None:
        exclude_qids = []

    targets = MuxTargets(mux_ids=mux_ids, exclude_qids=exclude_qids)

    task_parameters: dict[str, dict[str, Any]] = {
        "CorrectCaptureDelay": {
            "run": {
                # Fixed readout tone in GHz, away from the resonators. Leave unset to
                # use 0.25 GHz above the connected readout box's default resonator
                # spectroscopy range (11.0 GHz for the high band, 7.0 GHz for the low
                # band), or set it to a frequency inside the readout band.
                # "readout_frequency": 11.0,
                # QuEL-1: coarse sweep in 128 ns units with capture_delay_word fixed at 0.
                "delay_range": sweep.range(0, 19, 1),
                # QuEL-1: word sweep in 8 ns units at the chosen coarse delay (32 ns steps).
                "capture_delay_word_range": sweep.range(0, 16, 4),
                # QuEL-3: sweep in ns; every value must be a multiple of 0.8 ns.
                "capture_delay_ns_range": sweep.arange(0, 2432, 128),
                "shots": 1024,
            },
        },
    }
    steps = [BringUp(mode=mode, tasks=["CorrectCaptureDelay"])]

    cal = CalibService(
        username,
        chip_id,
        flow_name=flow_name,
        tags=tags,
        project_id=project_id,
        default_run_parameters={
            "readout_duration": 1024,
        },
        task_parameters=task_parameters,
    )
    return cal.run(targets, steps=steps)
