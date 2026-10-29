"""End-to-end GE, EF, and two-qubit characterization.

Calibration stages stop the affected qubit after the first failed task. Characterization stages
record each measurement failure and continue with the remaining measurements, while still
stopping if their configuration task fails. The JAZZ schedule is generated from the GE-calibrated
qubits before EF filtering, but JAZZ itself runs after any requested EF characterization.

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

TWO_QUBIT_CHARACTERIZATION_TASKS: list[str] = ["CheckJAZZ"]

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

    JAZZ runs after any requested EF work, but does not require EF calibration. Its coupling
    schedule is based on GE calibration success, so an EF calibration failure does not remove a
    pair from JAZZ. Anharmonicity-dependent outputs may be omitted when EF data is unavailable.
    """
    if not any((run_ge_characterization, run_ef_characterization, run_jazz)):
        raise ValueError("at least one characterization stage must be enabled")

    targets: Target
    if mux_ids is not None:
        targets = MuxTargets(mux_ids=mux_ids, exclude_qids=exclude_qids or [])
    elif qids is not None:
        targets = QubitTargets(qids=qids)
    else:
        raise ValueError("mux_ids or qids is required; select targets before running this flow")

    configure_task = "ConfigureEF" if run_ef_characterization else "Configure"

    # Every CalibrationStep owns an isolated Qubex session. Keep configuration in each task list
    # that needs GE/EF/FH targets instead of relying on a previous step's in-memory Experiment.
    steps: list[Step] = [
        OneQubitCheck(
            mode="synchronized",
            tasks=[configure_task, *GE_CALIBRATION_TASKS],
        ),
        FilterByStatus(),
    ]

    # Snapshot the JAZZ schedule now. Later EF filtering must not remove GE-successful pairs.
    if run_jazz:
        steps.append(GenerateCRSchedule(max_parallel_ops=max_parallel_ops, inverse=inverse))

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

    if run_ef_characterization:
        steps.extend(
            [
                OneQubitFineTune(
                    mode="synchronized",
                    tasks=["ConfigureEF", *EF_CALIBRATION_TASKS],
                ),
                FilterByStatus(),
            ]
        )

    if run_ef_characterization:
        steps.append(
            CustomOneQubit(
                step_name="ef_characterization",
                tasks=["ConfigureEF", *EF_CHARACTERIZATION_TASKS],
                mode="synchronized",
                continue_on_failure=True,
                stop_on_failure_tasks=("ConfigureEF",),
            )
        )

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
        # Keep the main editable knobs visible here. These values are initial template defaults;
        # tune the sweeps, shots, durations, and intervals for the device under test.
        task_parameters={
            "Configure": {
                "run": {"configuration_mode": "ge-cr-cr"},
            },
            "ConfigureEF": {
                # FH Chevron is part of EF characterization, so the FH layout is required.
                "run": {"configuration_mode": "ge-ef-fh"},
            },
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
            "CheckJAZZ": {
                "run": {
                    "time_range": sweep.arange(0, 20_001, 400),
                    "shots": 1024,
                    "interval": STANDARD_INTERVAL,
                },
            },
        },
        default_run_parameters={
            "readout_duration": 1024,
            "interval": STANDARD_INTERVAL,
        },
    )
    return cal.run(targets, steps=steps)
