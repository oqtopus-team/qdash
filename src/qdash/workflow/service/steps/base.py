"""Base classes for calibration steps.

This module defines the abstract base classes for all step types.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from qdash.workflow.service.calib_service import CalibService
    from qdash.workflow.service.steps.pipeline import StepContext
    from qdash.workflow.service.targets import Target


@dataclass
class Step(ABC):
    """Abstract base class for calibration steps.

    Steps are composable units of work in a calibration pipeline.
    Each step declares its dependencies (requires) and outputs (provides).

    Subclasses must implement:
        - name: Step identifier
        - execute: Main execution logic
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Step name for identification."""
        ...

    @property
    def requires(self) -> set[str]:
        """Context keys this step requires from previous steps.

        Override to declare dependencies. Default: no requirements.
        """
        return set()

    @property
    def provides(self) -> set[str]:
        """Context keys this step provides.

        Override to declare outputs. Default: {self.name}.
        """
        return {self.name}

    @abstractmethod
    def execute(
        self,
        service: CalibService,
        targets: Target,
        ctx: StepContext,
    ) -> StepContext:
        """Execute the step.

        Args:
            service: CalibService instance (provides execute_task, etc.)
            targets: Target specification
            ctx: Current pipeline context

        Returns:
            Updated StepContext with results
        """
        ...


@dataclass
class CalibrationStep(Step):
    """Base class for steps that execute actual calibration on hardware.

    CalibrationSteps create execution history entries because they involve
    real hardware interaction and produce calibration data.

    Examples: OneQubitCheck, OneQubitFineTune, TwoQubitCalibration
    """

    pass


@dataclass
class TransformStep(Step):
    """Base class for steps that transform data without hardware execution.

    TransformSteps do NOT create execution history entries because they
    only filter, schedule, or transform existing data.

    Examples: FilterByMetric, FilterByStatus, GenerateCRSchedule
    """

    pass
