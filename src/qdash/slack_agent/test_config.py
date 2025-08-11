#!/usr/bin/env python3
"""
Test configuration loading and model setup.
"""

import os
import logging
from qdash.config import get_settings
from qdash.slack_agent.config_manager import get_current_model_config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_config_loading():
    """Test configuration loading from qdash.config."""
    try:
        settings = get_settings()
        logger.info("✅ QDash settings loaded successfully")
        
        # Check for OpenAI API key
        openai_key = getattr(settings, 'openai_api_key', None) or os.getenv("OPENAI_API_KEY")
        if openai_key:
            logger.info(f"✅ OpenAI API key found (length: {len(openai_key)})")
        else:
            logger.warning("⚠️ No OpenAI API key found")
            
        # Check model config
        model_config = get_current_model_config()
        logger.info(f"✅ Model config loaded: {model_config.name} ({model_config.provider})")
        logger.info(f"  - Max completion tokens: {model_config.max_completion_tokens}")
        logger.info(f"  - Temperature: {model_config.temperature}")
        
        if hasattr(model_config, 'verbosity'):
            logger.info(f"  - Verbosity: {model_config.verbosity}")
        if hasattr(model_config, 'reasoning_effort'):  
            logger.info(f"  - Reasoning effort: {model_config.reasoning_effort}")
            
        return True
        
    except Exception as e:
        logger.error(f"❌ Config loading failed: {e}")
        return False

def test_strands_import():
    """Test Strands import and basic functionality."""
    try:
        from strands import Agent, tool
        from strands.models.openai import OpenAIModel
        logger.info("✅ Strands imports successful")
        return True
    except ImportError as e:
        logger.error(f"❌ Strands import failed: {e}")
        return False

if __name__ == "__main__":
    logger.info("🧪 Testing configuration and imports...")
    
    config_ok = test_config_loading()
    strands_ok = test_strands_import()
    
    if config_ok and strands_ok:
        logger.info("🎉 All tests passed!")
    else:
        logger.error("❌ Some tests failed")
        
    exit(0 if (config_ok and strands_ok) else 1)