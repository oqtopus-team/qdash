"""
Outlier detection service for quantum calibration data.

This service provides defensive outlier filtering to protect against
contaminated data that may have bypassed calibration-time validation.
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class OutlierResult:
    """Result of outlier detection analysis."""

    original_count: int
    filtered_count: int
    outlier_count: int
    outlier_qids: List[str]
    method_used: str
    parameters: Dict[str, Any]
    physical_violations: List[str]


class T2StarOutlierDetector:
    """
    Specialized outlier detection for T2* coherence time data.

    Designed as a defensive layer against database contamination from
    anomalous calibration results that bypassed initial validation.
    """

    def __init__(self):
        # Physical constraints for T2* in microseconds
        self.physical_bounds = {
            "t2_star_min": 0.1,  # 100ns minimum (physical lower bound)
            "t2_star_max": 1000.0,  # 1ms maximum (generous upper bound)
        }

        # Statistical thresholds
        self.default_thresholds = {
            "modified_z_score": 3.5,  # Conservative threshold
            "iqr_multiplier": 2.0,  # More conservative than 1.5
        }

    def detect_outliers(
        self,
        data: Dict[str, Union[float, Dict[str, Any]]],
        parameter_name: str = "t2_star",
        method: str = "combined",
        **kwargs,
    ) -> OutlierResult:
        """
        Detect outliers in T2* coherence time data.

        Args:
            data: Dictionary mapping qid -> task_result or value
            parameter_name: Name of the parameter to analyze
            method: Detection method ('modified_z_score', 'iqr', 'physical_bounds', 'combined')
            **kwargs: Method-specific parameters

        Returns:
            OutlierResult with detection statistics and outlier identification
        """
        if not data:
            return OutlierResult(0, 0, 0, [], method, {}, [])

        # Extract T2* values from task results or direct values
        extracted_values = self._extract_t2_star_values(data, parameter_name)

        if not extracted_values:
            logger.warning(f"No valid {parameter_name} values found in data")
            return OutlierResult(len(data), 0, 0, [], method, {}, [])

        values = np.array(list(extracted_values.values()))
        qids = list(extracted_values.keys())

        # Apply detection method
        if method == "modified_z_score":
            outlier_mask, violations = self._modified_z_score(values, **kwargs)
        elif method == "iqr":
            outlier_mask, violations = self._iqr_method(values, **kwargs)
        elif method == "physical_bounds":
            outlier_mask, violations = self._physical_bounds(values)
        elif method == "combined":
            outlier_mask, violations = self._combined_method(values, **kwargs)
        else:
            raise ValueError(f"Unknown detection method: {method}")

        outlier_qids = [qids[i] for i in range(len(qids)) if outlier_mask[i]]

        # Log detection results for monitoring
        if outlier_qids:
            logger.info(f"Detected {len(outlier_qids)} outliers in {parameter_name} data using {method}")
            logger.debug(f"Outlier QIDs: {outlier_qids}")

        return OutlierResult(
            original_count=len(data),
            filtered_count=len(extracted_values) - np.sum(outlier_mask),
            outlier_count=np.sum(outlier_mask),
            outlier_qids=outlier_qids,
            method_used=method,
            parameters=kwargs,
            physical_violations=violations,
        )

    def _extract_t2_star_values(
        self, data: Dict[str, Union[float, Dict[str, Any]]], parameter_name: str
    ) -> Dict[str, float]:
        """Extract T2* values from various data structures."""
        extracted = {}

        for qid, item in data.items():
            value = None

            # Handle direct numeric values
            if isinstance(item, (int, float)):
                value = float(item)

            # Handle task result structures
            elif isinstance(item, dict):
                # Try different common structures
                if "output_parameters" in item and item["output_parameters"]:
                    param_value = item["output_parameters"].get(parameter_name)
                    if param_value is not None:
                        # Handle nested value structures
                        if isinstance(param_value, dict):
                            if "value" in param_value:
                                value = float(param_value["value"])
                            elif "mean" in param_value:
                                value = float(param_value["mean"])
                            elif "result" in param_value:
                                value = float(param_value["result"])
                        else:
                            value = float(param_value)

                # Direct parameter access
                elif parameter_name in item:
                    param_value = item[parameter_name]
                    if isinstance(param_value, dict):
                        value = float(param_value.get("value", param_value.get("mean", 0)))
                    else:
                        value = float(param_value)

            # Validate and convert to microseconds if needed
            if value is not None and not np.isnan(value) and value > 0:
                # Convert from seconds to microseconds if value seems to be in seconds
                if value < 0.01:  # Likely in seconds
                    value = value * 1e6
                extracted[qid] = value

        return extracted

    def _modified_z_score(self, values: np.ndarray, threshold: Optional[float] = None) -> tuple[np.ndarray, List[str]]:
        """
        Modified Z-score using Median Absolute Deviation (MAD).
        More robust than standard Z-score for non-normal distributions.
        """
        threshold = threshold or self.default_thresholds["modified_z_score"]

        median = np.median(values)
        mad = np.median(np.abs(values - median))

        if mad == 0:
            # All values are identical, no outliers
            return np.zeros(len(values), dtype=bool), []

        modified_z_scores = 0.6745 * (values - median) / mad
        outlier_mask = np.abs(modified_z_scores) > threshold

        violations = [f"Modified Z-score > {threshold}"]
        return outlier_mask, violations

    def _iqr_method(self, values: np.ndarray, multiplier: Optional[float] = None) -> tuple[np.ndarray, List[str]]:
        """Interquartile Range (IQR) based outlier detection."""
        multiplier = multiplier or self.default_thresholds["iqr_multiplier"]

        Q1 = np.percentile(values, 25)
        Q3 = np.percentile(values, 75)
        IQR = Q3 - Q1

        if IQR == 0:
            # No variation, no outliers
            return np.zeros(len(values), dtype=bool), []

        lower_bound = Q1 - multiplier * IQR
        upper_bound = Q3 + multiplier * IQR

        outlier_mask = (values < lower_bound) | (values > upper_bound)
        violations = [f"IQR method with multiplier {multiplier}"]
        return outlier_mask, violations

    def _physical_bounds(self, values: np.ndarray) -> tuple[np.ndarray, List[str]]:
        """Remove physically impossible T2* values."""
        min_bound = self.physical_bounds["t2_star_min"]
        max_bound = self.physical_bounds["t2_star_max"]

        outlier_mask = (values < min_bound) | (values > max_bound)
        violations = []

        if np.any(values < min_bound):
            violations.append(f"Values below {min_bound}μs")
        if np.any(values > max_bound):
            violations.append(f"Values above {max_bound}μs")

        return outlier_mask, violations

    def _combined_method(self, values: np.ndarray, **kwargs) -> tuple[np.ndarray, List[str]]:
        """Combine physical bounds and statistical methods for robust detection."""
        # Always check physical bounds first
        physical_outliers, physical_violations = self._physical_bounds(values)

        # Apply statistical method to remaining data
        non_physical_outliers = ~physical_outliers
        if np.sum(non_physical_outliers) > 3:  # Need minimum data points for statistics
            statistical_values = values[non_physical_outliers]
            statistical_outliers, stat_violations = self._modified_z_score(statistical_values, kwargs.get("threshold"))

            # Map statistical outliers back to original indices
            full_statistical_outliers = np.zeros(len(values), dtype=bool)
            full_statistical_outliers[non_physical_outliers] = statistical_outliers
        else:
            full_statistical_outliers = np.zeros(len(values), dtype=bool)
            stat_violations = []

        combined_outliers = physical_outliers | full_statistical_outliers
        all_violations = physical_violations + stat_violations

        return combined_outliers, all_violations


def filter_task_results_for_outliers(
    task_results: Dict[str, Any], task_name: str, enable_filtering: bool = True, method: str = "combined"
) -> tuple[Dict[str, Any], Optional[OutlierResult]]:
    """
    Filter task results to remove outliers based on task type.

    This is the main entry point for defensive outlier filtering in API responses.

    Args:
        task_results: Dictionary of QID -> task result
        task_name: Name of the task (determines parameter to check)
        enable_filtering: Whether to apply filtering
        method: Detection method to use

    Returns:
        Tuple of (filtered_results, outlier_info)
    """
    if not enable_filtering:
        return task_results, None

    # Determine parameter based on task name
    parameter_mapping = {
        "CheckRamsey": "t2_star",
        "Ramsey": "t2_star",
        "T2Star": "t2_star",
        # Add other mappings as needed
    }

    parameter_name = parameter_mapping.get(task_name)
    if not parameter_name:
        # Task doesn't have outlier-prone parameters, return as-is
        return task_results, None

    detector = T2StarOutlierDetector()
    outlier_result = detector.detect_outliers(task_results, parameter_name=parameter_name, method=method)

    # Filter out outliers from results
    filtered_results = {qid: result for qid, result in task_results.items() if qid not in outlier_result.outlier_qids}

    logger.info(
        f"Outlier filtering for {task_name}: "
        f"{outlier_result.outlier_count}/{outlier_result.original_count} outliers removed"
    )

    return filtered_results, outlier_result
