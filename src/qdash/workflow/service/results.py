"""Typed result classes for calibration steps.

This module defines typed result objects that provide a clear interface
between calibration steps. Each step produces a specific result type,
making dependencies explicit and enabling type checking.

Result classes are intentionally backend-agnostic. The Step implementations
are responsible for constructing these objects from backend-specific data.

Example:
    from qdash.workflow.service.results import OneQubitResult, QubitCalibData

    result = OneQubitResult()
    result.add_qubit("Q00", QubitCalibData(
        status="success",
        x90_fidelity=0.95,
        t1=50.0,
    ))

    # Type-safe access
    fidelity = result.get_fidelity("Q00")  # float | None
    successful = result.successful_qids()  # list[str]
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

# =============================================================================
# Base Result Types
# =============================================================================


@dataclass
class QubitCalibData:
    """Calibration data for a single qubit.

    Attributes:
        status: Calibration status ("success" or "failed")
        metrics: Named metrics extracted from calibration (e.g., {"x90_fidelity": 0.95})
        raw: Raw backend-specific results
    """

    status: Literal["success", "failed"] = "failed"
    metrics: dict[str, float] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

    def get_metric(self, name: str) -> float | None:
        """Get a metric by name."""
        return self.metrics.get(name)


@dataclass
class CouplingCalibData:
    """Calibration data for a coupling pair.

    Attributes:
        status: Calibration status ("success" or "failed")
        metrics: Named metrics extracted from calibration (e.g., {"zx90_fidelity": 0.92})
        raw: Raw backend-specific results
    """

    status: Literal["success", "failed"] = "failed"
    metrics: dict[str, float] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

    def get_metric(self, name: str) -> float | None:
        """Get a metric by name."""
        return self.metrics.get(name)


# =============================================================================
# Step Result Classes
# =============================================================================


@dataclass
class OneQubitResult:
    """Result from a 1-qubit calibration step.

    Provides typed access to qubit calibration data with helper methods
    for filtering and querying results.

    Attributes:
        qubits: Mapping from qubit ID to calibration data
    """

    qubits: dict[str, QubitCalibData] = field(default_factory=dict)

    def add_qubit(self, qid: str, data: QubitCalibData) -> None:
        """Add calibration data for a qubit."""
        self.qubits[qid] = data

    def get_qubit(self, qid: str) -> QubitCalibData | None:
        """Get calibration data for a qubit."""
        return self.qubits.get(qid)

    def get_metric(self, qid: str, metric_name: str) -> float | None:
        """Get a specific metric for a qubit."""
        data = self.qubits.get(qid)
        return data.get_metric(metric_name) if data else None

    def get_status(self, qid: str) -> Literal["success", "failed"] | None:
        """Get calibration status for a qubit."""
        data = self.qubits.get(qid)
        return data.status if data else None

    def successful_qids(self) -> list[str]:
        """Get list of qubit IDs with successful calibration."""
        return sorted(qid for qid, data in self.qubits.items() if data.status == "success")

    def failed_qids(self) -> list[str]:
        """Get list of qubit IDs with failed calibration."""
        return sorted(qid for qid, data in self.qubits.items() if data.status == "failed")

    def filter_by_metric(self, metric_name: str, threshold: float) -> list[str]:
        """Get qubit IDs where metric meets threshold.

        Args:
            metric_name: Name of the metric to filter by
            threshold: Minimum value for the metric

        Returns:
            List of qubit IDs with metric >= threshold
        """
        return sorted(
            qid
            for qid, data in self.qubits.items()
            if data.get_metric(metric_name) is not None
            and data.get_metric(metric_name) >= threshold  # type: ignore[operator]
        )

    def all_qids(self) -> list[str]:
        """Get all qubit IDs."""
        return sorted(self.qubits.keys())


@dataclass
class TwoQubitResult:
    """Result from a 2-qubit calibration step.

    Attributes:
        couplings: Mapping from coupling ID (e.g., "Q00-Q01") to calibration data
    """

    couplings: dict[str, CouplingCalibData] = field(default_factory=dict)

    def add_coupling(self, coupling_id: str, data: CouplingCalibData) -> None:
        """Add calibration data for a coupling."""
        self.couplings[coupling_id] = data

    def get_coupling(self, coupling_id: str) -> CouplingCalibData | None:
        """Get calibration data for a coupling."""
        return self.couplings.get(coupling_id)

    def successful_couplings(self) -> list[str]:
        """Get list of coupling IDs with successful calibration."""
        return sorted(cid for cid, data in self.couplings.items() if data.status == "success")

    def failed_couplings(self) -> list[str]:
        """Get list of coupling IDs with failed calibration."""
        return sorted(cid for cid, data in self.couplings.items() if data.status == "failed")

    def filter_by_metric(self, metric_name: str, threshold: float) -> list[str]:
        """Get coupling IDs where metric meets threshold.

        Args:
            metric_name: Name of the metric to filter by
            threshold: Minimum value for the metric

        Returns:
            List of coupling IDs with metric >= threshold
        """
        return sorted(
            cid
            for cid, data in self.couplings.items()
            if data.get_metric(metric_name) is not None
            and data.get_metric(metric_name) >= threshold  # type: ignore[operator]
        )

    def all_couplings(self) -> list[str]:
        """Get all coupling IDs."""
        return sorted(self.couplings.keys())


@dataclass
class FilterResult:
    """Result from a filter step.

    Attributes:
        input_qids: Qubit IDs before filtering
        output_qids: Qubit IDs after filtering
        filter_criteria: Description of filter applied
    """

    input_qids: list[str] = field(default_factory=list)
    output_qids: list[str] = field(default_factory=list)
    filter_criteria: str = ""

    @property
    def filtered_out(self) -> list[str]:
        """Qubits that were filtered out."""
        return sorted(set(self.input_qids) - set(self.output_qids))

    @property
    def pass_rate(self) -> float:
        """Percentage of qubits that passed the filter."""
        if not self.input_qids:
            return 0.0
        return len(self.output_qids) / len(self.input_qids)


@dataclass
class SkewCheckResult:
    """Result from skew check step.

    Attributes:
        mux_skews: Mapping from MUX ID to skew value
        passed: Whether skew is within acceptable range
        raw: Raw backend-specific results
    """

    mux_skews: dict[int, float] = field(default_factory=dict)
    passed: bool = True
    raw: dict[str, Any] = field(default_factory=dict)
