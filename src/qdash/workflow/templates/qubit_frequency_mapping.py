"""Qubit frequency mapping from multiplexed resonator candidates.

This opt-in template detects the resonator candidates of each selected MUX and then
identifies each qubit's coarse frequency and resonator with CheckQubitFrequencyMapping.
It does not run amplitude or Chevron tasks and does not change the Bring-up template.

CheckQubitFrequencyMapping needs ``qubex.contrib.multiplexed_readout_qubit_spectroscopy``
from https://github.com/amachino/qubex/pull/472. Until that pull request merges, QDash
pins Qubex to its head commit; with a Qubex revision that lacks the helper, the mapping
task fails at run time with an error naming that prerequisite.

Example:
    qubit_frequency_mapping(
        username="alice",
        chip_id="16Q",
        mux_ids=[0, 1],
    )
"""

from typing import Any, Literal

from prefect import flow

from qdash.common.mux_mapping import canonical_qid, resolve_chip_mux_mapping
from qdash.workflow import TaskCall, sweep  # noqa: F401  # used by commented range overrides below
from qdash.workflow.service import CalibService
from qdash.workflow.service.calib_service import (
    on_flow_cancellation,
    on_flow_crashed,
    on_flow_failure,
)
from qdash.workflow.service.steps import BringUp
from qdash.workflow.service.targets import MuxTargets

QubitFrequencyMappingExecutionMode = Literal["sequential", "parallel_by_mux"]
"""Execution modes that never drive two qubits of one MUX at the same time.

Both run the qubits of a MUX one after another in local slot order, so the MUX
representative (slot 0) finishes CheckResonatorSpectroscopy, including the
distribution of its candidates to every qubit of the MUX, before any qubit of that
MUX runs CheckQubitFrequencyMapping. ``parallel_by_round`` can start a later slot of
a MUX before its representative and is not accepted.
"""

QUBIT_FREQUENCY_MAPPING_EXECUTION_MODES: tuple[QubitFrequencyMappingExecutionMode, ...] = (
    "sequential",
    "parallel_by_mux",
)

# Both calls publish their outputs: the mapping reads the candidates from the
# calibration parameters, and its own result is the readout and coarse qubit values.
QUBIT_FREQUENCY_MAPPING_TASKS: list[TaskCall] = [
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
]


@flow(
    on_cancellation=[on_flow_cancellation],
    on_failure=[on_flow_failure],
    on_crashed=[on_flow_crashed],
)
def qubit_frequency_mapping(
    username: str,
    chip_id: str,
    mux_ids: list[int] | None = None,
    exclude_qids: list[str] | None = None,
    qids: list[str] | None = None,
    execution_mode: QubitFrequencyMappingExecutionMode = "sequential",
    tags: list[str] | None = None,
    flow_name: str | None = None,
    project_id: str | None = None,
) -> Any:
    """Detect resonator candidates per MUX, then map each qubit to its resonator.

    For each selected MUX, CheckResonatorSpectroscopy runs once on the MUX
    representative (local slot 0) with ``detection_only`` and distributes the
    candidate set to every qubit of the MUX before the representative goes on.
    CheckQubitFrequencyMapping then runs for each selected qubit of the MUX, one
    after another. Each qubit's mapping is independent: QDash does not check that
    the selections of one MUX form a one-to-one mapping. A qubit fails without outputs
    unless its best-scoring candidate has quality level 3 or higher and an f01 moment
    at least ``min_score_ratio`` (default 2.0) times the runner-up's.

    Both calls set ``update_calibration_parameters`` to True. The mapping reads the
    candidates from the calibration parameters, so it cannot run on candidates that
    were not published. Requires a Qubex revision that includes
    https://github.com/amachino/qubex/pull/472.

    Args:
        username: User name (from UI)
        chip_id: Chip ID (from UI)
        mux_ids: MUX IDs to map (required)
        exclude_qids: Qubit IDs to skip. A MUX representative (local slot 0) cannot
            be excluded, because CheckResonatorSpectroscopy runs only on it.
        qids: Not used (for UI compatibility)
        execution_mode: How the qubits run (default: "sequential"):
            - "sequential": one MUX and one qubit at a time, so only one qubit is
              driven at a time
            - "parallel_by_mux": MUXes run in parallel within the scheduler's
              hardware stages; the qubits of one MUX run one after another
        tags: Tags recorded on the run
        flow_name: Flow name (auto-injected)
        project_id: Project ID (auto-injected)

    Returns:
        Pipeline results with the bring-up step outputs

    Raises:
        ValueError: If ``mux_ids`` is missing, ``execution_mode`` is not one of
            the accepted modes, or ``exclude_qids`` names a MUX representative.
    """
    if mux_ids is None:
        raise ValueError("mux_ids is required; select MUX targets before running this flow")
    if execution_mode not in QUBIT_FREQUENCY_MAPPING_EXECUTION_MODES:
        valid = ", ".join(QUBIT_FREQUENCY_MAPPING_EXECUTION_MODES)
        raise ValueError(
            f"Unknown execution_mode {execution_mode!r} for qubit frequency mapping. "
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
            tasks=QUBIT_FREQUENCY_MAPPING_TASKS,
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
    _reject_excluded_representatives(cal.project_id, chip_id, mux_ids, exclude_qids)
    return cal.run(targets, steps=steps)


def _reject_excluded_representatives(
    project_id: str, chip_id: str, mux_ids: list[int], exclude_qids: list[str]
) -> None:
    """Raise ValueError when an exclusion would skip a MUX's candidate detection.

    Without its representative, a MUX would run no CheckResonatorSpectroscopy, and
    its other qubits could map against candidates from an earlier run.
    """
    if not exclude_qids:
        return
    excluded = {canonical_qid(qid) for qid in exclude_qids}
    mapping = resolve_chip_mux_mapping(project_id, chip_id)
    representatives = [mapping.slots_of(mux_id).get(0) for mux_id in mapping.check_mux_ids(mux_ids)]
    blocked = [qid for qid in representatives if qid is not None and qid in excluded]
    if blocked:
        raise ValueError(
            f"exclude_qids contains MUX representative qubits {blocked}; "
            "CheckResonatorSpectroscopy runs only on local slot 0 of each MUX. "
            "Remove the MUX from mux_ids instead of excluding its representative."
        )
