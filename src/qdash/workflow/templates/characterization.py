"""End-to-end GE, EF, and two-qubit characterization.

GE and EF refer to the ground-to-first-excited and first-to-second-excited transitions.
The pipeline runs in this order:

1. Configure all selected MUXes once (always).
2. GE calibration and filtering (always).
3. Capture the coupling schedule from GE-successful qubits (if enabled).
4. GE characterization (optional).
5. EF calibration, filtering, and characterization (optional).
6. Coupling characterization with JAZZ using the captured schedule (optional).

The selected MUXes are configured once before calibration. Calibration stages stop the affected
qubit after the first failed task, while characterization stages record each measurement failure
and continue with the remaining measurements.

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
    ConfigureAll,
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

COUPLING_CHARACTERIZATION_TASKS: list[str] = ["CheckCouplingStrength"]

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
    run_coupling_characterization: bool = True,
    max_parallel_couplings: int = 10,
    reverse_coupling_direction: bool = False,
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
        run_coupling_characterization: Run JAZZ for GE-successful pairs after optional EF work.
            Static ZZ is always measured. Coupling strength is calculated when QDash contains
            calibrated anharmonicities for both qubits. EF failures do not remove scheduled pairs.
        max_parallel_couplings: Maximum coupling pairs in each schedule group.
        reverse_coupling_direction: Reverse the CR direction used to select coupling pairs.
        tags: Tags applied to execution history.
        flow_name: Flow name supplied by QDash.
        project_id: Project ID supplied by QDash.
    """
    if not any((run_ge_characterization, run_ef_characterization, run_coupling_characterization)):
        raise ValueError("at least one characterization stage must be enabled")

    targets: Target
    if mux_ids is not None:
        targets = MuxTargets(mux_ids=mux_ids, exclude_qids=exclude_qids or [])
    elif qids is not None:
        targets = QubitTargets(qids=qids)
    else:
        raise ValueError("mux_ids or qids is required; select targets before running this flow")

    enabled_tasks = [*GE_CALIBRATION_TASKS]
    if run_ge_characterization:
        enabled_tasks.extend(GE_CHARACTERIZATION_TASKS)
    if run_ef_characterization:
        enabled_tasks.extend((*EF_CALIBRATION_TASKS, *EF_CHARACTERIZATION_TASKS))
    if run_coupling_characterization:
        enabled_tasks.extend(COUPLING_CHARACTERIZATION_TASKS)

    # FH Chevron requires the GE/EF/FH layout. GE and JAZZ remain available in it,
    # so the full workflow can keep one configuration from start to finish.
    configuration_mode = "ge-ef-fh" if "CheckAdaptiveFHChevron" in enabled_tasks else "ge-cr-cr"

    # Configure the selected MUXes once; isolated workers inherit the same logical layout.
    steps: list[Step] = [
        ConfigureAll(),
        # 2. GE calibration: retain only qubits whose calibration succeeded.
        OneQubitCheck(
            mode="synchronized",
            tasks=GE_CALIBRATION_TASKS,
        ),
        FilterByStatus(),
    ]

    # 3. Capture coupling pairs before any EF filtering changes candidate_qids.
    if run_coupling_characterization:
        steps.append(
            GenerateCRSchedule(
                max_parallel_ops=max_parallel_couplings,
                inverse=reverse_coupling_direction,
            )
        )

    # 4. GE characterization: record failures and continue independent measurements.
    if run_ge_characterization:
        steps.append(
            CustomOneQubit(
                step_name="ge_characterization",
                tasks=GE_CHARACTERIZATION_TASKS,
                mode="synchronized",
                continue_on_failure=True,
            )
        )

    # 5. EF calibration, filtering, and characterization.
    if run_ef_characterization:
        steps.extend(
            [
                OneQubitFineTune(
                    mode="synchronized",
                    tasks=EF_CALIBRATION_TASKS,
                ),
                FilterByStatus(),
                CustomOneQubit(
                    step_name="ef_characterization",
                    tasks=EF_CHARACTERIZATION_TASKS,
                    mode="synchronized",
                    continue_on_failure=True,
                ),
            ]
        )

    # 6. Coupling characterization using the saved GE schedule.
    if run_coupling_characterization:
        steps.append(
            CustomTwoQubit(
                step_name="coupling_characterization",
                tasks=COUPLING_CHARACTERIZATION_TASKS,
                max_parallel_ops=max_parallel_couplings,
                continue_on_failure=True,
            )
        )

    cal = CalibService(
        username,
        chip_id,
        flow_name=flow_name,
        tags=tags,
        project_id=project_id,
        task_parameters=_build_task_parameters(configuration_mode),
        configuration_mode=configuration_mode,
        default_run_parameters={
            "readout_duration": 1024,
            "interval": STANDARD_INTERVAL,
        },
    )
    return cal.run(targets, steps=steps)


def _build_task_parameters(configuration_mode: str) -> dict[str, dict[str, Any]]:
    """Create editable task defaults grouped in pipeline order for each flow run.

    Tune sweeps, shots, durations, and intervals for the device under test.
    Time values are in ns and frequency values are in GHz.
    """
    return {
        # Push the full selected-MUX layout once before any calibration stage.
        "ConfigureAll": {
            "run": {"configuration_mode": configuration_mode},
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
        # Coupling characterization
        "CheckCouplingStrength": {
            "run": {
                "time_range": sweep.arange(0, 20_001, 400),
                "shots": 1024,
                "interval": STANDARD_INTERVAL,
            },
        },
    }
