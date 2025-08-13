"""
Response processing service for API endpoints.

This service handles post-processing of API responses, including outlier filtering.
"""

import logging
from typing import Any, Dict

from qdash.api.services.outlier_detection import filter_task_results_for_outliers

logger = logging.getLogger(__name__)


class ResponseProcessor:
    """Service for processing API responses with optional outlier filtering."""
    
    def __init__(self):
        # Tasks are now determined by the detector factory
        pass
    
    def process_task_response(
        self, 
        response: Any, 
        task_name: str,
        enable_outlier_filtering: bool = True
    ) -> Any:
        """
        Process task response with automatic outlier filtering if applicable.
        
        Args:
            response: The response object to process
            task_name: Name of the task
            enable_outlier_filtering: Whether to apply outlier filtering
            
        Returns:
            Processed response object
        """
        if not enable_outlier_filtering:
            return response
        
        if not hasattr(response, 'result') or not response.result:
            return response
        
        # Apply outlier filtering
        filtered_results = self._apply_outlier_filtering(response.result, task_name)
        
        # Update response with filtered results
        response.result = filtered_results
        return response
    
    def _apply_outlier_filtering(self, results: Dict[str, Any], task_name: str) -> Dict[str, Any]:
        """Apply outlier filtering to task results."""
        # Convert Task objects to dict for outlier detection
        task_dict = {}
        for qid, task in results.items():
            if hasattr(task, 'output_parameters') and task.output_parameters:
                task_dict[qid] = {"output_parameters": task.output_parameters}
        
        if not task_dict:
            return results
        
        # Apply outlier detection using new inheritance-based design
        filtered_task_dict, outlier_result = filter_task_results_for_outliers(
            task_dict, 
            task_name, 
            enable_filtering=True,
            method="combined"
        )
        
        # If no outlier detection was applied (task not supported), return original
        if outlier_result is None:
            return results
        
        if outlier_result.outlier_count > 0:
            logger.info(f"Applying automatic outlier filtering for {task_name}")
            # Remove outliers from results - silent data correction
            filtered_results = results.copy()
            for outlier_qid in outlier_result.outlier_qids:
                if outlier_qid in filtered_results:
                    logger.info(f"Automatically filtered outlier QID: {outlier_qid} (silent data correction)")
                    del filtered_results[outlier_qid]
            return filtered_results
        
        return results


# Global instance for use across routers
response_processor = ResponseProcessor()