"""End-to-end GE, EF, and two-qubit characterization.

GE and EF refer to the ground-to-first-excited and first-to-second-excited transitions.
The pipeline runs in this order:

1. GE calibration and filtering (always).
2. Capture the JAZZ coupling schedule from GE-successful qubits (if JAZZ is enabled).
3. GE characterization (optional).
4. EF calibration, filtering, and characterization (optional).
5. Measure static ZZ and coupling strength using the captured schedule (optional).

Calibration stages stop the affected qubit after the first failed task. Characterization stages
record each measurement failure and continue with the remaining measurements, while still
stopping if their configuration task fails.

Edit the task lists below to change measurement order, and _build_task_parameters() to tune
sweeps, shots, pulse durations, and intervals.

Example:
    characterization(
        username="alice",
        chip_id="64Qv3",
        mux_ids=[0, 1, 2, 3],
    )
"""

import math
from typing import Any

from prefect import flow

from qdash.workflow import sweep
from qdash.workflow.service import CalibService
from qdash.workflow.service.calib_service import (
    on_flow_cancellation,
    on_flow_crashed,
    on_flow_failure,
)
from qdash.workflow.service.steps import (
    CustomOneQubit,
    CustomTwoQubit,
    FilterByStatus,
    GenerateCRSchedule,
    OneQubitCheck,
    OneQubitFineTune,
    Step,
)
from qdash.workflow.service.targets import MuxTargets, QubitTargets, Target

GE_CALIBRATION_TASKS: list[str] = [
    "CheckRabi",
    "CreateHPIPulse",
    "CreatePIPulse",
    "CreateDRAGHPIPulse",
    "CreateDRAGPIPulse",
    "ReadoutClassification",
]

GE_CHARACTERIZATION_TASKS: list[str] = [
    "CheckT1Average",
    "CheckT2EchoAverage",
    "CheckCKP",
    "CheckQuantumEfficiency",
    "CheckCPMGNoiseSpectroscopy",
    "CheckSpinLockSpectroscopy",
]

EF_CALIBRATION_TASKS: list[str] = [
    "CheckAdaptiveEFChevron",
    "CheckEFRabi",
    "CreateEFHPIPulse",
    "CreateEFPIPulse",
    "EFReadoutClassification",
]

EF_CHARACTERIZATION_TASKS: list[str] = [
    "CheckThermalExcitation",
    "CheckReadoutMIST",
    "CheckAdaptiveFHChevron",
]

TWO_QUBIT_CHARACTERIZATION_TASKS: list[str] = ["CheckCouplingStrength"]

SHORT_INTERVAL = 256 * 1024
STANDARD_INTERVAL = 384 * 1024
LONG_INTERVAL = 512 * 1024


@flow(
    on_cancellation=[on_flow_cancellation],
    on_failure=[on_flow_failure],
    on_crashed=[on_flow_crashed],
)
def characterization(
    username: str,
    chip_id: str,
    mux_ids: list[int] | None = None,
    exclude_qids: list[str] | None = None,
    qids: list[str] | None = None,
    run_ge_characterization: bool = True,
    run_ef_characterization: bool = True,
    run_jazz: bool = True,
    max_parallel_ops: int = 10,
    inverse: bool = False,
    tags: list[str] | None = None,
    flow_name: str | None = None,
    project_id: str | None = None,
) -> Any:
    """Calibrate the selected qubits and run the requested characterization stages.

    Args:
        username: User name supplied by QDash.
        chip_id: Chip to calibrate.
        mux_ids: MUX targets; takes precedence over qids when supplied.
        exclude_qids: Qubits to remove from the MUX selection.
        qids: Individual targets when mux_ids is not supplied.
        run_ge_characterization: Measure GE properties after the required GE calibration.
        run_ef_characterization: Calibrate EF, then characterize EF-successful qubits.
        run_jazz: Measure static ZZ and coupling strength for GE-successful pairs after the
            optional EF work. EF failures do not remove pairs.
        max_parallel_ops: Maximum coupling pairs in each JAZZ schedule group.
        inverse: Reverse the CR direction used to select JAZZ coupling pairs.
        tags: Tags applied to execution history.
        flow_name: Flow name supplied by QDash.
        project_id: Project ID supplied by QDash.
    """
    # Validate the requested stages and resolve targets.
    if not any((run_ge_characterization, run_ef_characterization, run_jazz)):
        raise ValueError("at least one characterization stage must be enabled")

    targets: Target
    if mux_ids is not None:
        targets = MuxTargets(mux_ids=mux_ids, exclude_qids=exclude_qids or [])
    elif qids is not None:
        targets = QubitTargets(qids=qids)
    else:
        raise ValueError("mux_ids or qids is required; select targets before running this flow")

    # EF characterization includes FH Chevron, so its sessions need GE/EF/FH targets.
    configure_task = "ConfigureEF" if run_ef_characterization else "Configure"

    # 1. GE calibration: retain only qubits whose calibration succeeded.
    # Every CalibrationStep owns an isolated Qubex session. Keep configuration in each task list
    # that needs GE/EF/FH targets instead of relying on a previous step's in-memory Experiment.
    steps: list[Step] = [
        OneQubitCheck(
            mode="synchronized",
            tasks=[configure_task, *GE_CALIBRATION_TASKS],
        ),
        FilterByStatus(),
    ]

    # 2. Capture JAZZ pairs before any EF filtering changes candidate_qids.
    if run_jazz:
        steps.append(GenerateCRSchedule(max_parallel_ops=max_parallel_ops, inverse=inverse))

    # 3. GE characterization: continue measurements unless configuration fails.
    if run_ge_characterization:
        steps.append(
            CustomOneQubit(
                step_name="ge_characterization",
                tasks=[configure_task, *GE_CHARACTERIZATION_TASKS],
                mode="synchronized",
                continue_on_failure=True,
                stop_on_failure_tasks=(configure_task,),
            )
        )

    # 4. EF calibration gates EF characterization, but leaves the saved JAZZ pairs intact.
    if run_ef_characterization:
        steps.extend(
            [
                OneQubitFineTune(
                    mode="synchronized",
                    tasks=["ConfigureEF", *EF_CALIBRATION_TASKS],
                ),
                FilterByStatus(),
                CustomOneQubit(
                    step_name="ef_characterization",
                    tasks=["ConfigureEF", *EF_CHARACTERIZATION_TASKS],
                    mode="synchronized",
                    continue_on_failure=True,
                    stop_on_failure_tasks=("ConfigureEF",),
                ),
            ]
        )

    # 5. JAZZ consumes the GE schedule, even if no qubits survived EF calibration.
    if run_jazz:
        steps.append(
            CustomTwoQubit(
                step_name="jazz_characterization",
                tasks=TWO_QUBIT_CHARACTERIZATION_TASKS,
                max_parallel_ops=max_parallel_ops,
                continue_on_failure=True,
            )
        )

    cal = CalibService(
        username,
        chip_id,
        flow_name=flow_name,
        tags=tags,
        project_id=project_id,
        task_parameters=_build_task_parameters(),
        default_run_parameters={
            "readout_duration": 1024,
            "interval": STANDARD_INTERVAL,
        },
    )
    return cal.run(targets, steps=steps)


def _build_task_parameters() -> dict[str, dict[str, Any]]:
    """Create editable task defaults grouped in pipeline order for each flow run.

    Tune sweeps, shots, durations, and intervals for the device under test.
    Time values are in ns and frequency values are in GHz.
    """
    return {
        # Session configuration
        "Configure": {
            "run": {"configuration_mode": "ge-cr-cr"},
        },
        "ConfigureEF": {
            # FH Chevron is part of EF characterization, so the FH layout is required.
            "run": {"configuration_mode": "ge-ef-fh"},
        },
        # GE calibration
        "CheckRabi": {
            "run": {
                "time_range": sweep.range(0, 401, 8),
                "shots": 2048,
                "interval": SHORT_INTERVAL,
            },
        },
        "CreateHPIPulse": {
            "run": {
                "hpi_duration": 32,
                "shots": 2048,
                "interval": SHORT_INTERVAL,
            },
        },
        "CreatePIPulse": {
            "run": {
                "pi_duration": 32,
                "shots": 2048,
                "interval": SHORT_INTERVAL,
            },
        },
        "CreateDRAGHPIPulse": {
            "run": {
                "drag_hpi_duration": 16,
                "shots": 2048,
                "interval": STANDARD_INTERVAL,
            },
        },
        "CreateDRAGPIPulse": {
            "run": {
                "drag_pi_duration": 24,
                "shots": 2048,
                "interval": STANDARD_INTERVAL,
            },
        },
        "ReadoutClassification": {
            "run": {"shots": 2048, "interval": LONG_INTERVAL},
        },
        # GE characterization
        "CheckT1Average": {
            "run": {
                "time_range": sweep.logspace(math.log10(100), math.log10(500_000), 51),
                "shots": 1024,
                "interval": STANDARD_INTERVAL,
                "n_runs": 8,
            },
        },
        "CheckT2EchoAverage": {
            "run": {
                "time_range": sweep.logspace(math.log10(300), math.log10(100_000), 51),
                "shots": 1024,
                "interval": STANDARD_INTERVAL,
                "n_runs": 8,
            },
        },
        "CheckCKP": {
            "run": {
                # Set qubit_detuning_range/resonator_detuning_range to explicit lists
                # here when the Qubex target-specific defaults are not appropriate.
                "shots": 1024,
                "interval": STANDARD_INTERVAL,
                "target_min_qubit_detuning": -0.02,
            },
        },
        "CheckQuantumEfficiency": {
            "run": {
                # Add amplitude_range=[...] to replace Qubex's target-specific sweep.
                "shots": 1024,
                "interval": STANDARD_INTERVAL,
            },
        },
        "CheckCPMGNoiseSpectroscopy": {
            "run": {
                "frequency_range": sweep.linspace(0.0005, 0.004, 20),
                "time_range": sweep.logspace(math.log10(200.0), math.log10(200_000.0), 31),
                "shots": 1024,
                "interval": STANDARD_INTERVAL,
                "pi_pulse_pattern": "++++",
            },
        },
        "CheckSpinLockSpectroscopy": {
            "run": {
                "spin_lock_frequency_range": sweep.linspace(0.004, 0.1, 25),
                # Add duration_range=[...] to replace the T1/T2-derived sweep.
                "shots": 1024,
                "interval": STANDARD_INTERVAL,
            },
        },
        # EF calibration
        "CheckAdaptiveEFChevron": {
            "run": {
                "detuning_range": sweep.linspace(-0.05, 0.05, 41),
                "time_range": sweep.range(0, 257, 8),
                "shots": 256,
                "interval": SHORT_INTERVAL,
                "minimum_peak_background_rms_ratio": 5.0,
            },
        },
        "CheckEFRabi": {
            "run": {
                "time_range": sweep.range(0, 401, 8),
                "shots": 2048,
                "interval": SHORT_INTERVAL,
            },
        },
        "CreateEFHPIPulse": {
            "run": {
                "ef_hpi_duration": 32,
                "shots": 2048,
                "interval": SHORT_INTERVAL,
            },
        },
        "CreateEFPIPulse": {
            "run": {
                "ef_pi_duration": 32,
                "shots": 2048,
                "interval": SHORT_INTERVAL,
            },
        },
        "EFReadoutClassification": {
            "run": {"shots": 2048, "interval": LONG_INTERVAL},
        },
        # EF characterization
        "CheckThermalExcitation": {
            "run": {"shots": 256 * 1024, "interval": LONG_INTERVAL},
        },
        "CheckReadoutMIST": {
            "run": {
                "cycle_gap": 0.0,
                "measure_reference": True,
                "shots": 4096,
                "calibration_shots": 8192,
                "interval": LONG_INTERVAL,
            },
        },
        "CheckAdaptiveFHChevron": {
            "run": {
                "detuning_range": sweep.linspace(-0.05, 0.05, 41),
                "time_range": sweep.range(0, 257, 8),
                "shots": 256,
                "interval": STANDARD_INTERVAL,
                "minimum_peak_background_rms_ratio": 5.0,
            },
        },
        # JAZZ characterization
        "CheckCouplingStrength": {
            "run": {
                "time_range": sweep.arange(0, 20_001, 400),
                "shots": 1024,
                "interval": STANDARD_INTERVAL,
            },
        },
    }
