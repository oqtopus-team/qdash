"""Filter steps for calibration pipelines.

This module defines transform steps that filter candidate qubits:
- FilterByMetric: Filter by a named metric threshold
- FilterByStatus: Filter by calibration success status
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from prefect import get_run_logger

from qdash.workflow.service.results import FilterResult
from qdash.workflow.service.steps.base import TransformStep

if TYPE_CHECKING:
    from qdash.workflow.service.calib_service import CalibService
    from qdash.workflow.service.steps.pipeline import StepContext
    from qdash.workflow.service.targets import Target


@dataclass
class FilterByMetric(TransformStep):
    """Filter qubits by a named metric threshold.

    This step filters `ctx.candidate_qids` to only include qubits
    that meet the metric threshold from the latest 1-qubit result.

    Requires: one_qubit_check or one_qubit_fine_tune
    Provides: filter result appended to ctx.filters
    """

    metric: str = "x90_fidelity"
    threshold: float = 0.9

    @property
    def name(self) -> str:
        return f"filter_by_{self.metric}"

    @property
    def requires(self) -> set[str]:
        return {"one_qubit_check"} | {"one_qubit_fine_tune"}

    @property
    def provides(self) -> set[str]:
        return {"candidate_qids"}

    def execute(
        self,
        service: "CalibService",
        targets: "Target",
        ctx: "StepContext",
    ) -> "StepContext":
        """Filter candidate qubits by metric threshold."""
        logger = get_run_logger()

        result = ctx.get_latest_one_qubit_result()
        if result is None:
            logger.warning(f"[{self.name}] No 1-qubit results found, keeping all candidates")
            return ctx

        input_qids = ctx.candidate_qids.copy()
        output_qids = result.filter_by_metric(self.metric, self.threshold)

        # Intersect with current candidates
        output_qids = sorted(set(output_qids) & set(input_qids))

        logger.info(
            f"[{self.name}] Filtered {len(input_qids)} -> {len(output_qids)} qubits "
            f"({self.metric} >= {self.threshold})"
        )

        ctx.candidate_qids = output_qids
        ctx.filters.append(
            FilterResult(
                input_qids=input_qids,
                output_qids=output_qids,
                filter_criteria=f"{self.metric} >= {self.threshold}",
            )
        )
        return ctx


@dataclass
class FilterByStatus(TransformStep):
    """Filter qubits by calibration status.

    Keeps only qubits that have "success" status in the latest result.

    Requires: one_qubit_check or one_qubit_fine_tune
    Provides: candidate_qids
    """

    @property
    def name(self) -> str:
        return "filter_by_status"

    @property
    def requires(self) -> set[str]:
        return {"one_qubit_check"} | {"one_qubit_fine_tune"}

    @property
    def provides(self) -> set[str]:
        return {"candidate_qids"}

    def execute(
        self,
        service: "CalibService",
        targets: "Target",
        ctx: "StepContext",
    ) -> "StepContext":
        """Filter candidate qubits by success status."""
        logger = get_run_logger()

        result = ctx.get_latest_one_qubit_result()
        if result is None:
            logger.warning(f"[{self.name}] No 1-qubit results found")
            return ctx

        input_qids = ctx.candidate_qids.copy()
        output_qids = result.successful_qids()

        # Intersect with current candidates
        output_qids = sorted(set(output_qids) & set(input_qids))

        logger.info(f"[{self.name}] Filtered {len(input_qids)} -> {len(output_qids)} qubits")

        ctx.candidate_qids = output_qids
        ctx.filters.append(
            FilterResult(
                input_qids=input_qids,
                output_qids=output_qids,
                filter_criteria="status == success",
            )
        )
        return ctx
