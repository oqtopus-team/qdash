"""Compatibility wrapper for the shared copilot data service."""

from qdash.common.copilot import data_facade as _data_service

CopilotDataService = _data_service.CopilotDataService
FALLBACK_QUERY_LIMIT = _data_service.FALLBACK_QUERY_LIMIT
