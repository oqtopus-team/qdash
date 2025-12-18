"""
Outlier detection service with inheritance-based design.

This module provides base and specialized outlier detectors for quantum calibration data.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Type

import numpy as np
import scipy.stats as stats

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


class OutlierDetector(ABC):
    """
    Abstract base class for outlier detection.

    Provides common functionality for detecting outliers in quantum calibration data.
    Subclasses should override specific methods to customize behavior.
    """

    def __init__(self) -> None:
        # Default statistical thresholds
        self.default_thresholds = {
            "modified_z_score": 3.5,
            "iqr_multiplier": 2.0,
            "z_score": 3.0,
            "grubbs_alpha": 0.05,
            "isolation_forest_contamination": 0.1,
            "mahalanobis_chi2_p": 0.001,
        }

    @abstractmethod
    def get_physical_bounds(self, parameter_name: str) -> Tuple[float, float]:
        """
        Get physical bounds for the parameter.

        Args:
            parameter_name: Name of the parameter

        Returns:
            Tuple of (min_bound, max_bound)
        """
        pass

    @abstractmethod
    def extract_parameter_values(self, data: Dict[str, Any], parameter_name: str) -> Dict[str, float]:
        """
        Extract parameter values from task results.

        Args:
            data: Raw task result data
            parameter_name: Parameter to extract

        Returns:
            Dictionary mapping qid to parameter value
        """
        pass

    def detect_outliers(
        self,
        data: Dict[str, Any],
        parameter_name: str,
        method: str = "combined",
        **kwargs: Any,
    ) -> OutlierResult:
        """
        Detect outliers in the data.

        Args:
            data: Dictionary mapping qid -> task_result
            parameter_name: Name of the parameter to analyze
            method: Detection method ('modified_z_score', 'iqr', 'physical_bounds', 'combined')
            **kwargs: Method-specific parameters

        Returns:
            OutlierResult with detection statistics
        """
        if not data:
            return OutlierResult(0, 0, 0, [], method, {}, [])

        # Extract values using subclass implementation
        extracted_values = self.extract_parameter_values(data, parameter_name)

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
            outlier_mask, violations = self._physical_bounds(values, parameter_name)
        elif method == "z_score":
            outlier_mask, violations = self._z_score_scipy(values, **kwargs)
        elif method == "combined":
            outlier_mask, violations = self._combined_method(values, parameter_name, **kwargs)
        else:
            raise ValueError(f"Unknown detection method: {method}")

        outlier_qids = [qids[i] for i in range(len(qids)) if outlier_mask[i]]

        # Log detection results
        if outlier_qids:
            logger.info(f"Detected {len(outlier_qids)} outliers in {parameter_name} data using {method}")
            logger.debug(f"Outlier QIDs: {outlier_qids}")

        return OutlierResult(
            original_count=len(data),
            filtered_count=len(data) - len(outlier_qids),
            outlier_count=len(outlier_qids),
            outlier_qids=outlier_qids,
            method_used=method,
            parameters=kwargs,
            physical_violations=violations,
        )

    def _modified_z_score(self, values: np.ndarray, threshold: Optional[float] = None) -> Tuple[np.ndarray, List[str]]:
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

    def _iqr_method(self, values: np.ndarray, multiplier: Optional[float] = None) -> Tuple[np.ndarray, List[str]]:
        """
        Interquartile Range (IQR) method for outlier detection.
        Robust to skewed distributions.
        """
        multiplier = multiplier or self.default_thresholds["iqr_multiplier"]

        q1 = np.percentile(values, 25)
        q3 = np.percentile(values, 75)
        iqr = q3 - q1

        lower_bound = q1 - multiplier * iqr
        upper_bound = q3 + multiplier * iqr

        outlier_mask = (values < lower_bound) | (values > upper_bound)
        violations = [f"IQR method with multiplier {multiplier}"]
        return outlier_mask, violations

    def _physical_bounds(self, values: np.ndarray, parameter_name: str) -> Tuple[np.ndarray, List[str]]:
        """Check physical bounds for the parameter."""
        min_bound, max_bound = self.get_physical_bounds(parameter_name)

        outlier_mask = (values < min_bound) | (values > max_bound)
        violations = []

        if np.any(values < min_bound):
            violations.append(f"Values below {min_bound}")
        if np.any(values > max_bound):
            violations.append(f"Values above {max_bound}")

        return outlier_mask, violations

    def _combined_method(self, values: np.ndarray, parameter_name: str, **kwargs: Any) -> Tuple[np.ndarray, List[str]]:
        """Combine physical bounds and statistical methods."""
        # Always check physical bounds first
        physical_outliers, physical_violations = self._physical_bounds(values, parameter_name)

        # Apply statistical method to remaining data
        non_physical_outliers = ~physical_outliers
        if np.sum(non_physical_outliers) > 3:  # Need minimum data points
            valid_values = values[non_physical_outliers]
            statistical_outliers, statistical_violations = self._modified_z_score(valid_values, **kwargs)

            # Map back to original indices
            full_statistical_mask = np.zeros(len(values), dtype=bool)
            full_statistical_mask[non_physical_outliers] = statistical_outliers

            combined_outliers = physical_outliers | full_statistical_mask
            combined_violations = physical_violations + statistical_violations
        else:
            combined_outliers = physical_outliers
            combined_violations = physical_violations

        return combined_outliers, combined_violations

    def _z_score_scipy(self, values: np.ndarray, threshold: Optional[float] = None) -> Tuple[np.ndarray, List[str]]:
        """Simple Z-score using scipy."""
        threshold = threshold or self.default_thresholds["z_score"]

        if len(values) < 3:
            return np.zeros(len(values), dtype=bool), []

        # Simple one-liner with scipy
        outlier_mask = np.abs(stats.zscore(values)) > threshold
        return outlier_mask, [f"Z-score > {threshold}"]


def extract_coherence_time_values(data: Dict[str, Any], parameter_name: str) -> Dict[str, float]:
    """Extract coherence time values from task results."""
    extracted = {}

    for qid, task_result in data.items():
        value = None

        # Handle different data structures
        if isinstance(task_result, dict):
            if "output_parameters" in task_result:
                param_value = task_result["output_parameters"].get(parameter_name)
                if param_value is not None:
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


def extract_fidelity_values(data: Dict[str, Any], parameter_name: str) -> Dict[str, float]:
    """Extract fidelity values from task results."""
    extracted = {}

    for qid, task_result in data.items():
        value = None

        # Handle different data structures
        if isinstance(task_result, dict):
            if "output_parameters" in task_result:
                param_value = task_result["output_parameters"].get(parameter_name)
                if param_value is not None:
                    if isinstance(param_value, dict):
                        value = float(param_value.get("value", param_value.get("mean", 0)))
                    else:
                        value = float(param_value)

        # Include all numeric values for outlier detection
        if value is not None and not np.isnan(value):
            extracted[qid] = value

    return extracted


class T2StarOutlierDetector(OutlierDetector):
    """Detector for T2* (Ramsey) measurements."""

    def get_physical_bounds(self, parameter_name: str) -> Tuple[float, float]:
        return (0.0, 1000.0)  # 0 to 1ms

    def extract_parameter_values(self, data: Dict[str, Any], parameter_name: str) -> Dict[str, float]:
        return extract_coherence_time_values(data, parameter_name)


class T2EchoOutlierDetector(OutlierDetector):
    """Detector for T2 echo measurements."""

    def get_physical_bounds(self, parameter_name: str) -> Tuple[float, float]:
        return (0.0, 2000.0)  # 0 to 2ms

    def extract_parameter_values(self, data: Dict[str, Any], parameter_name: str) -> Dict[str, float]:
        return extract_coherence_time_values(data, parameter_name)


class T1OutlierDetector(OutlierDetector):
    """Detector for T1 relaxation time measurements."""

    def get_physical_bounds(self, parameter_name: str) -> Tuple[float, float]:
        return (0.0, 10000.0)  # 0 to 10ms

    def extract_parameter_values(self, data: Dict[str, Any], parameter_name: str) -> Dict[str, float]:
        return extract_coherence_time_values(data, parameter_name)


class GateFidelityOutlierDetector(OutlierDetector):
    """Detector for gate fidelity measurements."""

    def get_physical_bounds(self, parameter_name: str) -> Tuple[float, float]:
        return (0.0, 1.0)  # 0 to 1 (100%)

    def extract_parameter_values(self, data: Dict[str, Any], parameter_name: str) -> Dict[str, float]:
        return extract_fidelity_values(data, parameter_name)


# Factory function to get appropriate detector
def get_outlier_detector(task_name: str) -> Optional[OutlierDetector]:
    """
    Factory function to get the appropriate outlier detector for a task.

    Args:
        task_name: Name of the task

    Returns:
        Appropriate OutlierDetector instance or None
    """
    detector_mapping: Dict[str, Type[OutlierDetector]] = {
        "CheckRamsey": T2StarOutlierDetector,
        "Ramsey": T2StarOutlierDetector,
        "T2Star": T2StarOutlierDetector,
        "CheckT2Echo": T2EchoOutlierDetector,
        "T2Echo": T2EchoOutlierDetector,
        "CheckT1": T1OutlierDetector,
        "T1": T1OutlierDetector,
        "X90InterleavedRandomizedBenchmarking": GateFidelityOutlierDetector,
        "X180InterleavedRandomizedBenchmarking": GateFidelityOutlierDetector,
        "ZX90InterleavedRandomizedBenchmarking": GateFidelityOutlierDetector,
        "RandomizedBenchmarking": GateFidelityOutlierDetector,
        "ReadoutClassification": GateFidelityOutlierDetector,
        "CheckBellStateTomography": GateFidelityOutlierDetector,
    }

    detector_class = detector_mapping.get(task_name)
    if detector_class:
        return detector_class()
    return None


def filter_task_results_for_outliers(
    task_results: Dict[str, Any], task_name: str, enable_filtering: bool = True, method: str = "combined"
) -> Tuple[Dict[str, Any], Optional[OutlierResult]]:
    """
    Filter task results to remove outliers based on task type.

    Args:
        task_results: Dictionary of QID -> task result
        task_name: Name of the task
        enable_filtering: Whether to apply filtering
        method: Detection method to use

    Returns:
        Tuple of (filtered_results, outlier_info)
    """
    if not enable_filtering:
        return task_results, None

    # Get appropriate detector
    detector = get_outlier_detector(task_name)
    if not detector:
        # No detector for this task type
        return task_results, None

    # Determine parameter name based on task
    parameter_mapping = {
        "CheckRamsey": "t2_star",
        "Ramsey": "t2_star",
        "T2Star": "t2_star",
        "CheckT2Echo": "t2_echo",
        "T2Echo": "t2_echo",
        "CheckT1": "t1",
        "T1": "t1",
        "X90InterleavedRandomizedBenchmarking": "x90_gate_fidelity",
        "X180InterleavedRandomizedBenchmarking": "x180_gate_fidelity",
        "ZX90InterleavedRandomizedBenchmarking": "zx90_gate_fidelity",
        "RandomizedBenchmarking": "average_gate_fidelity",
        "ReadoutClassification": "average_readout_fidelity",
        "CheckBellStateTomography": "bell_state_fidelity",
    }

    parameter_name = parameter_mapping.get(task_name)
    if not parameter_name:
        return task_results, None

    # Detect outliers
    outlier_result = detector.detect_outliers(task_results, parameter_name=parameter_name, method=method)

    # Filter out outliers
    filtered_results = {qid: result for qid, result in task_results.items() if qid not in outlier_result.outlier_qids}

    return filtered_results, outlier_result
