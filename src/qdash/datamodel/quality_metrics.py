"""Names of the quality metrics QDash records on a task result.

A task result's ``quality_metrics`` holds only what the workflow engine writes there. Today
that is the fit coefficient of determination ``r2``, copied from a task's ``RunResult.r2``
when the task reports one. A task's calibrated outputs, such as ``average_gate_fidelity`` of
``RandomizedBenchmarking``, are output parameters, not quality metrics.
"""

from __future__ import annotations

from typing import Final

QUALITY_METRIC_R2: Final = "r2"

# Every metric name the workflow engine may write into ``TaskModel.quality_metrics``.
RECORDED_QUALITY_METRICS: Final[frozenset[str]] = frozenset({QUALITY_METRIC_R2})
