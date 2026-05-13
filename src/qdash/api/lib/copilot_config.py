"""Compatibility wrapper for shared copilot configuration."""

from qdash.common.copilot import settings as _config

AnalysisConfig = _config.AnalysisConfig
CopilotConfig = _config.CopilotConfig
EvaluationMetrics = _config.EvaluationMetrics
ModelConfig = _config.ModelConfig
ScoringThreshold = _config.ScoringThreshold
Suggestion = _config.Suggestion
clear_copilot_config_cache = _config.clear_copilot_config_cache
load_copilot_config = _config.load_copilot_config
