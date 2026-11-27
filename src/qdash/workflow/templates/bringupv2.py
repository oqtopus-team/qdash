"""Bring-up v2: MUX-level bring-up with resonator-to-qubit mapping.

This template runs the Bring-up tasks with CheckResonatorQubitMapping after
resonator spectroscopy. Resonator spectroscopy assigns resonators to qubits from
an assumed frequency order; the mapping task then drives every qubit of the MUX
at high power while reading out at every resonator candidate, one pair at a
time, and writes only the readout settings it verifies. MUX-level tasks run once
per MUX, not per qubit.

Example:
    bringupv2(
        username="alice",
        chip_id="16Q",
        mux_ids=[0, 1, 2, 3],
    )
"""

from typing import Any

from qdash.calibration import (
    BringUp,
    MuxTargets,
    OneQubitExecutionMode,
    TaskCall,
    sweep,  # noqa: F401  # used by commented range overrides below
)
from qdash.workflow import CalibrationSession, calibration_flow, resolve_calib_context

# Each call keeps its task-specific acquisition settings, so the shared defaults
# do not replace the values selected for bring-up measurements.
BRINGUPV2_TASKS: list[TaskCall] = [
    TaskCall(
        name="CheckResonatorSpectroscopy",
        run={
            "shots": 1024,
            "interval": 0,
            # resonator_assignment_order lists the four qid offsets within each MUX
            # in increasing resonator-frequency order. The default is [3, 0, 2, 1].
            # Here the order is only a provisional assignment:
            # CheckResonatorQubitMapping measures the 4x4 mapping next and writes
            # the verified resonator to each qubit.
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
    # MUX-level 1D high-power mapping: each qubit x resonator candidate pair is
    # measured on its own, without multiplexing. A qubit whose response is
    # missing or ambiguous fails and keeps its provisional readout settings.
    TaskCall(
        name="CheckResonatorQubitMapping",
        run={
            # 0 dB is control amplitude 1.0.
            "drive_power": 0.0,
            # Coarse step for the broad high-power response. The drive range
            # defaults to the connected control box's qubex default band with this
            # step; uncomment to override it.
            "frequency_step": 0.020,
            # "frequency_range": sweep.arange(3.0, 5.75, 0.020),
            "shots": 512,
            "interval": 1024,
            # Decision thresholds; see the task's run parameter descriptions.
            # "min_response_score": 5.0,
            # "min_margin_ratio": 2.0,
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


@calibration_flow(session_name="Bring-up v2")
def bringupv2(
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
    """Bring-up calibration with resonator-to-qubit mapping.

    This flow runs MUX-level tasks (CheckResonatorSpectroscopy and
    CheckResonatorQubitMapping) that characterize the entire MUX unit, then the
    per-qubit spectroscopy and Chevron tasks. MUX-level tasks are executed only for
    the representative qubit (local slot 0) of each MUX.

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
        flow_name: Saved flow name QDash injects at launch; keep it in the signature
            and do not pass it on (session.run reads the launch name itself)
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
            tasks=BRINGUPV2_TASKS,
        )
    ]

    context = resolve_calib_context(username, chip_id, project_id=project_id)
    session = CalibrationSession.from_context(context)
    return session.run(
        targets=targets,
        steps=steps,
        default_run_parameters=default_run_parameters,
        tags=tags,
    )
