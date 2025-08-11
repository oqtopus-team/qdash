"""
Configuration management for Strands Slack Agent.
Handles model switching, feature flags, and runtime configuration.
"""

import json
import logging
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from qdash.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class ModelConfig:
    """Model configuration settings."""

    name: str
    provider: str  # "openai", "anthropic", "bedrock", etc.
    max_completion_tokens: int = 4000  # Updated from max_tokens
    temperature: float = 0.1
    timeout_seconds: int = 30
    fallback_model: Optional[str] = None
    # GPT-5 specific parameters
    verbosity: Optional[str] = "medium"  # "low", "medium", "high"
    reasoning_effort: Optional[str] = "medium"  # "minimal", "low", "medium", "high"


@dataclass
class AgentConfig:
    """Agent configuration settings."""

    max_steps: int = 10
    enable_streaming: bool = True
    enable_tool_parallel: bool = False
    response_format: str = "text"  # "text", "markdown", "json"
    user_message_prefix: str = ""
    system_message_suffix: str = ""


@dataclass
class FeatureFlags:
    """Feature flags for experimental features."""

    enable_web_search: bool = False
    enable_advanced_reasoning: bool = False
    enable_multimodal: bool = False
    enable_code_execution: bool = False
    enable_memory_persistence: bool = False


@dataclass
class StrandsAgentConfiguration:
    """Complete Strands agent configuration."""

    model: ModelConfig
    agent: AgentConfig
    features: FeatureFlags
    version: str = "1.0.0"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StrandsAgentConfiguration":
        """Create from dictionary."""
        return cls(
            model=ModelConfig(**data["model"]),
            agent=AgentConfig(**data["agent"]),
            features=FeatureFlags(**data["features"]),
            version=data.get("version", "1.0.0"),
        )


class ConfigurationManager:
    """Manages agent configuration with hot reloading."""

    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or self._get_default_config_path()
        self._config: Optional[StrandsAgentConfiguration] = None
        self._last_modified: float = 0
        self._load_config()

    def _get_default_config_path(self) -> str:
        """Get default configuration file path."""
        base_dir = Path(__file__).parent
        return str(base_dir / "config.json")

    def _load_config(self) -> None:
        """Load configuration from file."""
        try:
            if not os.path.exists(self.config_path):
                # Create default configuration
                self._create_default_config()

            # Check if file has been modified
            current_modified = os.path.getmtime(self.config_path)
            if current_modified <= self._last_modified and self._config is not None:
                return

            with open(self.config_path, encoding="utf-8") as f:
                data = json.load(f)

            self._config = StrandsAgentConfiguration.from_dict(data)
            self._last_modified = current_modified
            logger.info(f"✅ Configuration loaded from {self.config_path}")

        except Exception as e:
            logger.error(f"❌ Failed to load configuration: {e}")
            if self._config is None:
                # Fallback to default configuration
                self._config = self._get_default_configuration()
                logger.warning("Using default configuration as fallback")

    def _create_default_config(self) -> None:
        """Create default configuration file."""
        default_config = self._get_default_configuration()

        try:
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(default_config.to_dict(), f, indent=2, ensure_ascii=False)
            logger.info(f"📄 Default configuration created at {self.config_path}")
        except Exception as e:
            logger.error(f"❌ Failed to create default configuration: {e}")

    def _get_default_configuration(self) -> StrandsAgentConfiguration:
        """Get default configuration."""
        settings = get_settings()

        return StrandsAgentConfiguration(
            model=ModelConfig(
                name=getattr(settings, "openai_model", "gpt-5"),  # Default to GPT-5
                provider="openai",
                max_completion_tokens=4000,  # Updated parameter name
                temperature=0.3,
                timeout_seconds=30,
                fallback_model="gpt-4o-mini",
                # Note: verbosity and reasoning_effort not yet supported by current OpenAI client
            ),
            agent=AgentConfig(
                max_steps=10,
                enable_streaming=True,
                enable_tool_parallel=False,
                response_format="text",
                user_message_prefix="",
                system_message_suffix="重要: 常にツールを使用して実際のQDashデータにアクセスしてください。",
            ),
            features=FeatureFlags(
                enable_web_search=False,
                enable_advanced_reasoning=False,
                enable_multimodal=False,
                enable_code_execution=False,
                enable_memory_persistence=False,
            ),
        )

    def get_config(self) -> StrandsAgentConfiguration:
        """Get current configuration (with hot reload check)."""
        self._load_config()
        return self._config

    def update_model(self, model_name: str, provider: str = "openai") -> None:
        """Update model configuration."""
        config = self.get_config()
        config.model.name = model_name
        config.model.provider = provider
        self._save_config(config)
        logger.info(f"🔄 Model updated to {model_name} ({provider})")

    def toggle_feature(self, feature_name: str, enabled: bool) -> None:
        """Toggle feature flag."""
        config = self.get_config()
        if hasattr(config.features, feature_name):
            setattr(config.features, feature_name, enabled)
            self._save_config(config)
            logger.info(f"🎛️ Feature {feature_name} {'enabled' if enabled else 'disabled'}")
        else:
            logger.warning(f"⚠️ Unknown feature: {feature_name}")

    def update_agent_settings(self, **kwargs) -> None:
        """Update agent settings."""
        config = self.get_config()
        for key, value in kwargs.items():
            if hasattr(config.agent, key):
                setattr(config.agent, key, value)
                logger.info(f"🔧 Agent setting {key} updated to {value}")
        self._save_config(config)

    def _save_config(self, config: StrandsAgentConfiguration) -> None:
        """Save configuration to file."""
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(config.to_dict(), f, indent=2, ensure_ascii=False)
            self._config = config
            self._last_modified = os.path.getmtime(self.config_path)
            logger.info("💾 Configuration saved successfully")
        except Exception as e:
            logger.error(f"❌ Failed to save configuration: {e}")

    def get_model_configs(self) -> Dict[str, ModelConfig]:
        """Get predefined model configurations."""
        return {
            # GPT-5 family (will be enabled when OpenAI client supports these models)
            "gpt-5": ModelConfig(
                name="gpt-5", provider="openai", max_completion_tokens=4000, temperature=0.3, timeout_seconds=30
            ),
            "gpt-5-mini": ModelConfig(
                name="gpt-5-mini", provider="openai", max_completion_tokens=4000, temperature=0.3, timeout_seconds=20
            ),
            "gpt-5-nano": ModelConfig(
                name="gpt-5-nano", provider="openai", max_completion_tokens=2000, temperature=0.3, timeout_seconds=15
            ),
            "gpt-5-chat-latest": ModelConfig(
                name="gpt-5-chat-latest",
                provider="openai",
                max_completion_tokens=4000,
                temperature=0.3,
                timeout_seconds=25,
            ),
            # GPT-4 family
            "gpt-4o": ModelConfig(
                name="gpt-4o", provider="openai", max_completion_tokens=4000, temperature=0.3, timeout_seconds=30
            ),
            "gpt-4o-mini": ModelConfig(
                name="gpt-4o-mini", provider="openai", max_completion_tokens=4000, temperature=0.3, timeout_seconds=20
            ),
            "gpt-4-turbo": ModelConfig(
                name="gpt-4-turbo", provider="openai", max_completion_tokens=4000, temperature=0.3, timeout_seconds=30
            ),
            # Claude family
            "claude-3-5-sonnet": ModelConfig(
                name="claude-3-5-sonnet-20241022",
                provider="anthropic",
                max_completion_tokens=4000,
                temperature=0.3,
                timeout_seconds=30,
            ),
            "claude-3-haiku": ModelConfig(
                name="claude-3-haiku-20240307",
                provider="anthropic",
                max_completion_tokens=4000,
                temperature=0.3,
                timeout_seconds=15,
            ),
        }

    def switch_model(self, model_key: str) -> bool:
        """Switch to predefined model configuration."""
        available_models = self.get_model_configs()

        if model_key not in available_models:
            logger.error(f"❌ Unknown model: {model_key}")
            logger.info(f"Available models: {list(available_models.keys())}")
            return False

        model_config = available_models[model_key]
        config = self.get_config()
        config.model = model_config
        self._save_config(config)

        logger.info(f"🔄 Switched to model: {model_config.name} ({model_config.provider})")
        return True

    def get_health_info(self) -> Dict[str, Any]:
        """Get configuration health information."""
        config = self.get_config()
        return {
            "config_path": self.config_path,
            "config_exists": os.path.exists(self.config_path),
            "last_modified": self._last_modified,
            "current_model": f"{config.model.name} ({config.model.provider})",
            "features_enabled": [name for name, value in asdict(config.features).items() if value],
            "version": config.version,
        }


# Global configuration manager instance
config_manager = ConfigurationManager()


def get_current_model_config() -> ModelConfig:
    """Get current model configuration."""
    return config_manager.get_config().model


def get_current_agent_config() -> AgentConfig:
    """Get current agent configuration."""
    return config_manager.get_config().agent


def get_current_features() -> FeatureFlags:
    """Get current feature flags."""
    return config_manager.get_config().features


def is_feature_enabled(feature_name: str) -> bool:
    """Check if a feature is enabled."""
    features = get_current_features()
    return getattr(features, feature_name, False)
