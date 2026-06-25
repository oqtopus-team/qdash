"""Fake calibration tasks for testing without real quantum hardware.

These tasks simulate calibration workflows with realistic parameter dependencies,
enabling testing of provenance tracking and workflow execution.

Backend-Agnostic Task Names
---------------------------
All fake tasks use the SAME registered names as their qubex counterparts:
    - FakeCheckFineChevron registers as "CheckFineChevron"
    - FakeCheckRabi registers as "CheckRabi"
    - FakeCheckRamsey registers as "CheckRamsey"
    - FakeCheckT1 registers as "CheckT1"
    - FakeCheckT2Echo registers as "CheckT2Echo"
    - FakeRandomizedBenchmarking registers as "RandomizedBenchmarking"

This enables seamless backend switching:
    # Same task names work with any backend
    task_names = ["CheckFineChevron", "CheckRamsey", "CheckRabi", "CheckT1"]

    # Switch backend in config without changing task names
    config = CalibConfig(backend_name="fake", ...)  # for testing
    config = CalibConfig(backend_name="qubex", ...)  # for production

Dependency Graph:
    CheckFineChevron (entry point)
        ├── output: qubit_frequency, readout_frequency
        │
        ├──> CreateHPIPulse (calibrates half-pi pulse)
        │       ├── input: qubit_frequency
        │       └── output: hpi_amplitude, hpi_length
        │
        ├──> CheckRabi
        │       ├── input: qubit_frequency
        │       └── output: rabi_amplitude, rabi_frequency, rabi_phase, rabi_offset
        │
        ├──> CheckRamsey (refines frequency, measures T2*)
        │       ├── input: qubit_frequency, hpi_amplitude
        │       └── output: qubit_frequency (refined), t2_star, ramsey_frequency
        │
        ├──> CheckT1
        │       ├── input: qubit_frequency, hpi_amplitude
        │       └── output: t1
        │
        ├──> CheckT1Average
        │       ├── input: qubit_frequency, hpi_amplitude
        │       └── output: t1_average, t1_std
        │
        ├──> CheckT2Echo
        │       ├── input: qubit_frequency, hpi_amplitude
        │       └── output: t2_echo
        │
        └──> CheckT2EchoAverage
                ├── input: qubit_frequency, hpi_amplitude
                └── output: t2_echo_average, t2_echo_std

    RandomizedBenchmarking (depends on multiple)
        ├── input: qubit_frequency, rabi_amplitude, t1, t2_echo
        └── output: gate_fidelity, error_per_gate
"""

from qdash.workflow.calibtasks.active_protocols import generate_task_instances
from qdash.workflow.calibtasks.fake.base import FakeTask
from qdash.workflow.calibtasks.fake.fake_check_fine_chevron import FakeCheckFineChevron
from qdash.workflow.calibtasks.fake.fake_check_rabi import FakeCheckRabi
from qdash.workflow.calibtasks.fake.fake_check_ramsey import FakeCheckRamsey
from qdash.workflow.calibtasks.fake.fake_check_t1 import FakeCheckT1
from qdash.workflow.calibtasks.fake.fake_check_t1_average import FakeCheckT1Average
from qdash.workflow.calibtasks.fake.fake_check_t2_echo import FakeCheckT2Echo
from qdash.workflow.calibtasks.fake.fake_check_t2_echo_average import FakeCheckT2EchoAverage
from qdash.workflow.calibtasks.fake.fake_create_hpi_pulse import FakeCreateHPIPulse
from qdash.workflow.calibtasks.fake.fake_rabi import FakeRabi
from qdash.workflow.calibtasks.fake.fake_randomized_benchmarking import (
    FakeRandomizedBenchmarking,
)
from qdash.workflow.calibtasks.fake.legacy_fake_chevron_pattern import FakeChevronPattern

__all__ = [
    # Tasks with provenance dependencies
    "FakeCheckFineChevron",
    "FakeCheckRabi",
    "FakeCheckRamsey",
    "FakeCheckT1",
    "FakeCheckT1Average",
    "FakeCheckT2Echo",
    "FakeCheckT2EchoAverage",
    "FakeChevronPattern",  # legacy alias — UI selector only
    "FakeCreateHPIPulse",
    # Original fake task (simulator-based)
    "FakeRabi",
    "FakeRandomizedBenchmarking",
    # Base class
    "FakeTask",
    # Utility
    "generate_task_instances",
]


def _use_qubex_tasks_with_fake_backend() -> None:
    """Route fake backend task names to QUBEX task implementations.

    The fake backend now returns a QUBEX-compatible FakeExperiment, so running the
    production QUBEX task logic gives local fake executions the same behavior and
    result shape as hardware-backed runs, while still selecting backend="fake" in
    QDash templates and UI.
    """
    import qdash.workflow.calibtasks.qubex  # noqa: F401
    from qdash.workflow.calibtasks.base import BaseTask
    from qdash.workflow.calibtasks.fake.qubex_compat import FakeCheckFineChevron

    qubex_registry = BaseTask.registry.get("qubex", {})
    fake_registry = BaseTask.registry.setdefault("fake", {})
    fake_registry["CheckFineChevron"] = FakeCheckFineChevron
    for task_name in (
        "CheckRabi",
        "CreateHPIPulse",
        "CheckHPIPulse",
        "CreatePIPulse",
        "CheckPIPulse",
        "CheckRamsey",
        "CheckT1",
        "CheckT1Average",
        "CheckT2Echo",
        "CheckT2EchoAverage",
        "CreateDRAGHPIPulse",
        "CheckDRAGHPIPulse",
        "CreateDRAGPIPulse",
        "CheckDRAGPIPulse",
        "RandomizedBenchmarking",
    ):
        if task_name in qubex_registry:
            fake_registry[task_name] = qubex_registry[task_name]


_use_qubex_tasks_with_fake_backend()
