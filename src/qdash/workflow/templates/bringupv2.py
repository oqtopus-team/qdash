"""Bring-up v2: map each qubit to its resonator, then calibrate its drive.

This opt-in template detects the resonator candidates of each selected MUX,
identifies each qubit's coarse frequency and resonator with
CheckQubitFrequencyMapping, and then runs CheckControlAmplitude and
CheckAdaptiveChevron on the published values. It does not change the Bring-up
template.

CheckQubitFrequencyMapping needs ``qubex.contrib.multiplexed_readout_qubit_spectroscopy``
from https://github.com/amachino/qubex/pull/472 with its ``readout_grouping``
argument, which the Qubex revision pinned in ``uv.lock`` provides. With a Qubex
revision that lacks either, the mapping task fails at run time with an error
naming that prerequisite.

Example:
    bringupv2(
        username="alice",
        chip_id="16Q",
        mux_ids=[0, 1],
    )
"""

from typing import Any, Literal

from prefect import flow

from qdash.workflow import TaskCall, sweep  # noqa: F401  # used by commented range overrides below
from qdash.workflow.service import CalibService
from qdash.workflow.service.calib_service import (
    on_flow_cancellation,
    on_flow_crashed,
    on_flow_failure,
)
from qdash.workflow.service.steps import BringUp
from qdash.workflow.service.targets import MuxTargets

BringUpV2ExecutionMode = Literal["sequential", "parallel_by_mux"]
"""Execution modes that never drive two qubits of one MUX at the same time.

Both run the qubits of a MUX one after another in local slot order, so the MUX
representative (slot 0) finishes CheckResonatorSpectroscopy, including the
distribution of its candidates to every qubit of the MUX, before any qubit of that
MUX runs CheckQubitFrequencyMapping. ``parallel_by_round`` can start a later slot of
a MUX before its representative and is not accepted.
"""

BRINGUPV2_EXECUTION_MODES: tuple[BringUpV2ExecutionMode, ...] = (
    "sequential",
    "parallel_by_mux",
)


@flow(
    on_cancellation=[on_flow_cancellation],
    on_failure=[on_flow_failure],
    on_crashed=[on_flow_crashed],
)
def bringupv2(
    username: str,
    chip_id: str,
    mux_ids: list[int] | None = None,
    exclude_qids: list[str] | None = None,
    qids: list[str] | None = None,
    execution_mode: BringUpV2ExecutionMode = "parallel_by_mux",
    tags: list[str] | None = None,
    flow_name: str | None = None,
    project_id: str | None = None,
) -> Any:
    """Map each qubit of the selected MUXes to its resonator, then calibrate its drive.

    For each selected MUX, CheckResonatorSpectroscopy runs once on the MUX
    representative (local slot 0) with ``detection_only`` and distributes the
    candidate set to every qubit of the MUX before the representative goes on.
    Each selected qubit of the MUX then runs, one after another,
    CheckQubitFrequencyMapping, CheckControlAmplitude, and CheckAdaptiveChevron.
    By default the MUXes of one hardware stage run in parallel, as in the Bring-up
    template; two qubits of one MUX are never driven at the same time.
    Each qubit's mapping is independent: QDash does not check that the selections
    of one MUX form a one-to-one mapping. A qubit's mapping fails without outputs
    unless its best-scoring candidate has quality level 3 or higher and an f01
    moment at least ``min_score_ratio`` (default 2.0) times the runner-up's; a
    failed call skips that qubit's later calls, so the amplitude and Chevron
    tasks never run on values the mapping did not publish in this run.

    CheckResonatorSpectroscopy and CheckQubitFrequencyMapping set
    ``update_calibration_parameters`` to True: the mapping reads the candidates
    from the calibration parameters, and CheckControlAmplitude reads the readout
    frequency and amplitude, control frequency, and coarse control amplitude the
    mapping publishes. CheckControlAmplitude and CheckAdaptiveChevron keep the
    acquisition settings of the Bring-up template. Requires a Qubex revision that
    includes https://github.com/amachino/qubex/pull/472 and the helper's
    ``readout_grouping`` argument.

    Args:
        username: User name (from UI)
        chip_id: Chip ID (from UI)
        mux_ids: MUX IDs to bring up (required)
        exclude_qids: Qubit IDs to skip, applied as in the Bring-up template.
            CheckResonatorSpectroscopy runs only on a MUX representative (local
            slot 0), so excluding one runs no detection for its MUX in this run.
            The other qubits of that MUX then map against the candidates
            CheckQubitFrequencyMapping accepts from the calibration parameters,
            which can be a set published by an earlier run; the task decides
            whether that set is still usable. Remove the MUX from ``mux_ids`` to
            skip it entirely.
        qids: Not used (for UI compatibility)
        execution_mode: How the qubits run (default: "parallel_by_mux", as in the
            Bring-up template):
            - "parallel_by_mux": MUXes run in parallel within the scheduler's
              hardware stages; the qubits of one MUX run one after another
            - "sequential": one MUX and one qubit at a time, so only one qubit is
              driven at a time
        tags: Tags recorded on the run
        flow_name: Flow name (auto-injected)
        project_id: Project ID (auto-injected)

    Returns:
        Pipeline results with the bring-up step outputs

    Raises:
        ValueError: If ``mux_ids`` is missing or ``execution_mode`` is not one of
            the accepted modes.
    """
    if mux_ids is None:
        raise ValueError("mux_ids is required; select MUX targets before running this flow")
    if execution_mode not in BRINGUPV2_EXECUTION_MODES:
        valid = ", ".join(BRINGUPV2_EXECUTION_MODES)
        raise ValueError(
            f"Unknown execution_mode {execution_mode!r} for Bring-up v2. "
            f"Valid execution modes: {valid}"
        )
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
            tasks=[
                # The detection and the mapping publish their outputs: the mapping reads the
                # candidates from the calibration parameters, and the later tasks read the
                # readout and coarse qubit values the mapping publishes.
                TaskCall(
                    name="CheckResonatorSpectroscopy",
                    run={
                        "shots": 1024,
                        "interval": 0,
                        # Publish the unassigned candidates of the MUX instead of assigning a
                        # resonator to each qubit; resonator_assignment_order is ignored.
                        "detection_only": True,
                        # The frequency range defaults to the connected readout box's qubex
                        # default: low band [5.75, 6.75, 0.002] GHz or high band
                        # [9.75, 10.75, 0.002] GHz. The qubex default power range is
                        # [-60, 5, 5] dB (stop is exclusive). Leave each range unset to use its
                        # default, or uncomment to override it.
                        # "frequency_range": sweep.arange(5.75, 6.75, 0.002),
                    },
                    update_calibration_parameters=True,
                ),
                TaskCall(
                    name="CheckQubitFrequencyMapping",
                    run={
                        "shots": 1024,
                        "interval": 1024,
                        # The drive frequency range defaults to the connected control box's
                        # qubex default: low band [3.0, 5.75, 0.005] GHz or high band
                        # [6.5, 9.75, 0.005] GHz. The power range defaults to [-60, 0, 5] dB
                        # (stop is exclusive). Readout uses the resonator candidates as carrier
                        # overrides. Leave each range unset to use its default, or uncomment to
                        # override it.
                        # "frequency_range": sweep.arange(3.0, 5.75, 0.005),
                        # "power_range": sweep.arange(-60, 0, 10),
                    },
                    update_calibration_parameters=True,
                ),
                # The same acquisition settings as the Bring-up template.
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
            ],
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
