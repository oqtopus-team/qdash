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

from qdash.datamodel.task_call import TaskCallResult

# =============================================================================
# Base Result Types
# =============================================================================


def normalize_metric_value(parameter: Any) -> float | None:
    """Normalize a task output parameter into a numeric workflow metric.

    Task outputs can cross a Prefect process boundary as serialized dictionaries,
    while in-process execution returns ``ParameterModel``-like objects. Raw numeric
    values are also accepted for backwards compatibility.
    """
    if parameter is None:
        return None
    if isinstance(parameter, dict):
        parameter = parameter.get("value")
    elif hasattr(parameter, "value"):
        parameter = parameter.value
    if parameter is None:
        return None
    try:
        return float(parameter)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Metric value must be numeric, got {parameter!r}") from exc


class _CallAccess:
    """Ordered call results of one target, read from its raw step result."""

    raw: dict[str, Any]

    @property
    def calls(self) -> list[TaskCallResult]:
        """Every call of the step on this target, in call order."""
        entries = self.raw.get("calls")
        if not isinstance(entries, list):
            return []
        return [
            TaskCallResult.model_validate(entry) for entry in entries if isinstance(entry, dict)
        ]

    def call(self, call_id: str) -> TaskCallResult | None:
        """The result of one call by its call_id, or None if the step has no such call."""
        return next((call for call in self.calls if call.call_id == call_id), None)

    def calls_of(self, task_name: str) -> list[TaskCallResult]:
        """Every call of one task, in call order."""
        return [call for call in self.calls if call.name == task_name]

    def latest_call(self, task_name: str) -> TaskCallResult | None:
        """The last call of a task in the step, whatever its status."""
        calls = self.calls_of(task_name)
        return calls[-1] if calls else None

    def call_metric(self, call_id: str, name: str) -> float | None:
        """An output parameter of one call, or None when the call did not succeed.

        A failed or skipped call yields None even if an earlier call of the same
        task produced the parameter.
        """
        call = self.call(call_id)
        if call is None or call.status != "success":
            return None
        return normalize_metric_value(call.output.get(name))


@dataclass
class QubitCalibData(_CallAccess):
    """Calibration data for a single qubit.

    Attributes:
        status: Calibration status ("success" or "failed")
        metrics: Named metrics extracted from calibration (e.g., {"x90_fidelity": 0.95})
        raw: Raw backend-specific results, including the ordered ``calls``
    """

    status: Literal["success", "failed"] = "failed"
    metrics: dict[str, float] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

    def get_metric(self, name: str) -> float | None:
        """Get a metric by name."""
        return self.metrics.get(name)


@dataclass
class CouplingCalibData(_CallAccess):
    """Calibration data for a coupling pair.

    Attributes:
        status: Calibration status ("success" or "failed")
        metrics: Named metrics extracted from calibration (e.g., {"zx90_fidelity": 0.92})
        raw: Raw backend-specific results, including the ordered ``calls``
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
        step_id: The step that produced the result, when known
    """

    qubits: dict[str, QubitCalibData] = field(default_factory=dict)
    step_id: str = ""

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
            if (value := data.get_metric(metric_name)) is not None and value >= threshold
        )

    def all_qids(self) -> list[str]:
        """Get all qubit IDs."""
        return sorted(self.qubits.keys())

    def call_succeeded_qids(self, call_id: str) -> list[str]:
        """Qubit IDs on which one call succeeded."""
        return sorted(
            qid
            for qid, data in self.qubits.items()
            if (call := data.call(call_id)) is not None and call.status == "success"
        )

    def filter_by_call_metric(self, call_id: str, metric_name: str, threshold: float) -> list[str]:
        """Qubit IDs where one call's output parameter meets the threshold.

        Qubits whose call failed, was skipped, or lacks the parameter are left out;
        there is no fallback to another call of the same task.
        """
        return sorted(
            qid
            for qid, data in self.qubits.items()
            if (value := data.call_metric(call_id, metric_name)) is not None and value >= threshold
        )


@dataclass
class TwoQubitResult:
    """Result from a 2-qubit calibration step.

    Attributes:
        couplings: Mapping from coupling ID (e.g., "Q00-Q01") to calibration data
        step_id: The step that produced the result, when known
    """

    couplings: dict[str, CouplingCalibData] = field(default_factory=dict)
    step_id: str = ""

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
            if (value := data.get_metric(metric_name)) is not None and value >= threshold
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


# =============================================================================
# Builders
# =============================================================================


def build_one_qubit_result(
    raw_results: dict[str, Any],
    step_id: str,
    extract_metrics: Any = None,
) -> OneQubitResult:
    """Build a typed result from strategy output (stage -> qid -> target result)."""
    result = OneQubitResult(step_id=step_id)
    for stage_data in raw_results.values():
        if not isinstance(stage_data, dict):
            continue
        for qid, raw in stage_data.items():
            if not isinstance(raw, dict):
                continue
            result.add_qubit(
                qid,
                QubitCalibData(
                    status="success" if raw.get("status") == "success" else "failed",
                    metrics=extract_metrics(raw) if extract_metrics is not None else {},
                    raw=raw,
                ),
            )
    return result


def build_two_qubit_result(
    raw_results: dict[str, Any],
    step_id: str,
    extract_metrics: Any = None,
) -> TwoQubitResult:
    """Build a typed result from coupling output (coupling_id -> target result)."""
    result = TwoQubitResult(step_id=step_id)
    for coupling_id, raw in raw_results.items():
        if isinstance(raw, dict):
            result.add_coupling(
                coupling_id,
                CouplingCalibData(
                    status="success" if raw.get("status") == "success" else "failed",
                    metrics=extract_metrics(raw) if extract_metrics is not None else {},
                    raw=raw,
                ),
            )
    return result
