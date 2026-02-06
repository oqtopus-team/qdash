"""Default task lists for calibration workflows.

This module defines the standard task lists used across calibration workflows.
Import these lists instead of hardcoding task names in templates.

Task Lists:
    BRINGUP_TASKS: MUX-level bring-up tasks (resonator spectroscopy, etc.)
    CHECK_1Q_TASKS: Basic 1Q characterization (run first)
    FULL_1Q_TASKS_AFTER_CHECK: Advanced 1Q calibration (run after check)
    FULL_1Q_TASKS: Complete 1Q task list (CHECK + AFTER_CHECK)
    FULL_2Q_TASKS: Complete 2Q task list

Example:
    from qdash.workflow.service import CalibService
    from qdash.workflow.service.steps import CustomOneQubit, BringUp
    from qdash.workflow.service.tasks import CHECK_1Q_TASKS, BRINGUP_TASKS
    from qdash.workflow.service.targets import MuxTargets

    # Use in calibration
    cal = CalibService(username, chip_id)
    targets = MuxTargets([0, 1, 2, 3])
    results = cal.run(targets, steps=[BringUp(), CustomOneQubit(tasks=CHECK_1Q_TASKS)])
"""

# =============================================================================
# MUX-level Bring-up Task Lists
# =============================================================================

# Bring-up: Tasks for initial qubit characterization
# - MUX-level tasks (is_mux_level=True) run once per MUX for representative qubit
# - Qubit-level tasks run for each qubit individually
BRINGUP_TASKS: list[str] = [
    "CheckResonatorSpectroscopy",  # MUX-level: estimates resonator_frequency
    "CheckQubitSpectroscopy",  # Qubit-level: estimates qubit_frequency, anharmonicity
    "ChevronPattern",  # Qubit-level: estimates readout_amplitude
]


# =============================================================================
# 1-Qubit Task Lists
# =============================================================================

# 1Q Check: Basic characterization tasks (run first)
CHECK_1Q_TASKS: list[str] = [
    "CheckRabi",
    "CreateHPIPulse",
    "CheckHPIPulse",
    "CheckT1",
    "CheckT2Echo",
    "CheckRamsey",
]

# 1Q Full (after check): Advanced calibration tasks
FULL_1Q_TASKS_AFTER_CHECK: list[str] = [
    "CheckRabi",
    "CreateHPIPulse",
    "CheckHPIPulse",
    "CreatePIPulse",
    "CheckPIPulse",
    "CreateDRAGHPIPulse",
    "CheckDRAGHPIPulse",
    "CreateDRAGPIPulse",
    "CheckDRAGPIPulse",
    "ReadoutClassification",
    "RandomizedBenchmarking",
    "X90InterleavedRandomizedBenchmarking",
]

# Complete 1Q task list (CHECK + AFTER_CHECK)
FULL_1Q_TASKS: list[str] = CHECK_1Q_TASKS + FULL_1Q_TASKS_AFTER_CHECK


# =============================================================================
# 2-Qubit Task Lists
# =============================================================================

# Complete 2Q task list
FULL_2Q_TASKS: list[str] = [
    "CheckCrossResonance",
    "CreateZX90",
    "CheckZX90",
    "CheckBellState",
    "CheckBellStateTomography",
    "ZX90InterleavedRandomizedBenchmarking",
]
