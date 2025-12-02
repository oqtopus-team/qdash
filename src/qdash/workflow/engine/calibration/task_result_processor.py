"""TaskResultProcessor for validating and processing task results.

This module provides the TaskResultProcessor class that handles
validation of task outputs, R² checks, and fidelity validation.
"""

import logging
from typing import Any

from qdash.datamodel.task import OutputParameterModel

logger = logging.getLogger(__name__)


class TaskResultProcessingError(Exception):
    """Exception raised when task result processing fails."""

    pass


class R2ValidationError(TaskResultProcessingError):
    """Exception raised when R² validation fails."""

    pass


class FidelityValidationError(TaskResultProcessingError):
    """Exception raised when fidelity validation fails."""

    pass


class TaskResultProcessor:
    """Processor for validating and processing task results.

    This class handles:
    - R² validation against thresholds
    - Fidelity validation for RB tasks
    - Output parameter filtering on validation failure

    """

    # Task names that have fidelity output and need validation
    FIDELITY_TASKS = frozenset([
        "RandomizedBenchmarking",
        "InterleavedRandomizedBenchmarking",
    ])

    def __init__(self, r2_threshold: float = 0.7) -> None:
        """Initialize TaskResultProcessor.

        Parameters
        ----------
        r2_threshold : float
            Default R² threshold for validation

        """
        self.r2_threshold = r2_threshold

    def validate_r2(
        self,
        r2: dict[str, float] | None,
        qid: str,
        threshold: float | None = None,
    ) -> bool:
        """Validate R² value against threshold.

        Parameters
        ----------
        r2 : dict[str, float] | None
            Dictionary mapping qid to R² values
        qid : str
            The qubit ID to check
        threshold : float | None
            Optional custom threshold (uses default if None)

        Returns
        -------
        bool
            True if R² is valid (above threshold), False otherwise

        Raises
        ------
        R2ValidationError
            If R² is below threshold

        """
        if r2 is None:
            return True

        if qid not in r2:
            return True

        r2_value = r2[qid]
        check_threshold = threshold if threshold is not None else self.r2_threshold

        if r2_value <= check_threshold:
            raise R2ValidationError(
                f"R² value too low for qid {qid}: {r2_value:.4f} <= {check_threshold}"
            )

        return True

    def validate_fidelity(
        self,
        output_parameters: dict[str, OutputParameterModel],
        task_name: str,
    ) -> bool:
        """Validate fidelity for RB tasks (must be <= 1.0).

        Parameters
        ----------
        output_parameters : dict[str, OutputParameterModel]
            The output parameters from the task
        task_name : str
            The name of the task

        Returns
        -------
        bool
            True if fidelity is valid

        Raises
        ------
        FidelityValidationError
            If fidelity exceeds 100%

        """
        if task_name not in self.FIDELITY_TASKS:
            return True

        fidelity_param = output_parameters.get("fidelity")
        if fidelity_param is None:
            return True

        fidelity_value = fidelity_param.value
        if fidelity_value > 1.0:
            raise FidelityValidationError(
                f"Fidelity exceeds 100% for {task_name}: {fidelity_value * 100:.2f}%"
            )

        return True

    def get_output_parameter_names(
        self, output_parameters: dict[str, OutputParameterModel]
    ) -> list[str]:
        """Get list of output parameter names.

        Parameters
        ----------
        output_parameters : dict[str, OutputParameterModel]
            The output parameters

        Returns
        -------
        list[str]
            List of parameter names

        """
        return list(output_parameters.keys())

    def filter_output_parameters_on_r2_failure(
        self,
        output_parameters: dict[str, OutputParameterModel],
    ) -> dict[str, OutputParameterModel]:
        """Filter out output parameters when R² validation fails.

        This is called when R² is too low - we don't want to save
        the unreliable calibration values.

        Parameters
        ----------
        output_parameters : dict[str, OutputParameterModel]
            The output parameters to filter

        Returns
        -------
        dict[str, OutputParameterModel]
            Empty dict (all parameters filtered out)

        """
        logger.warning(
            f"Filtering out {len(output_parameters)} output parameters due to low R²"
        )
        return {}

    def process_run_result(
        self,
        raw_result: Any,
        r2: dict[str, float] | None,
        qid: str,
        task_name: str,
        r2_threshold: float | None = None,
    ) -> dict[str, Any]:
        """Process a run result, validating R² values.

        Parameters
        ----------
        raw_result : Any
            The raw result from the task run
        r2 : dict[str, float] | None
            R² values per qid
        qid : str
            The qubit ID
        task_name : str
            The task name
        r2_threshold : float | None
            Custom R² threshold

        Returns
        -------
        dict[str, Any]
            Dictionary with processed result info

        Raises
        ------
        R2ValidationError
            If R² validation fails

        """
        result = {
            "raw_result": raw_result,
            "r2": r2,
            "r2_valid": True,
        }

        if r2 is not None and qid in r2:
            try:
                self.validate_r2(r2, qid, r2_threshold)
            except R2ValidationError:
                result["r2_valid"] = False
                raise

        return result

    def process_output_parameters(
        self,
        output_parameters: dict[str, OutputParameterModel],
        task_name: str,
        execution_id: str,
        task_id: str,
    ) -> dict[str, OutputParameterModel]:
        """Process output parameters, validating and attaching metadata.

        Parameters
        ----------
        output_parameters : dict[str, OutputParameterModel]
            The output parameters to process
        task_name : str
            The task name
        execution_id : str
            The execution ID to attach
        task_id : str
            The task ID to attach

        Returns
        -------
        dict[str, OutputParameterModel]
            Processed output parameters

        Raises
        ------
        FidelityValidationError
            If fidelity validation fails

        """
        # Validate fidelity for RB tasks
        self.validate_fidelity(output_parameters, task_name)

        # Attach execution_id and task_id to output parameters
        for param in output_parameters.values():
            param.execution_id = execution_id
            param.task_id = task_id

        return output_parameters
