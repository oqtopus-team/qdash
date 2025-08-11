#!/usr/bin/env python3.10
"""
Test Strands agent integration with corrected parameters.
"""

import asyncio
import logging
import os
from qdash.config import get_settings
from qdash.slack_agent.config_manager import get_current_model_config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_strands_agent_creation():
    """Test creating Strands agent with current configuration."""
    try:
        from strands import Agent, tool
        from strands.models.openai import OpenAIModel
        
        # Get model configuration
        model_config = get_current_model_config()
        settings = get_settings()
        
        # Get API key
        api_key = (getattr(settings, 'openai_api_key', None) or 
                  model_config.api_key or 
                  os.getenv("OPENAI_API_KEY"))
        
        if not api_key:
            logger.error("❌ No OpenAI API key available")
            return False
            
        # Create a simple test tool
        @tool
        async def test_tool(message: str) -> str:
            """Test tool for verification."""
            return f"Test tool received: {message}"
        
        # Create model configuration (only supported parameters)
        model_params = {
            "temperature": model_config.temperature,
            "max_completion_tokens": model_config.max_completion_tokens,
        }
        
        logger.info(f"Creating OpenAI model with params: {model_params}")
        
        model = OpenAIModel(
            client_args={"api_key": api_key},
            model_id=model_config.name,
            params=model_params
        )
        
        # Create agent
        agent = Agent(
            model=model,
            system_prompt="You are a test agent. Keep responses very brief.",
            tools=[test_tool]
        )
        
        logger.info("✅ Strands agent created successfully")
        
        # Test simple invocation (without tools)
        logger.info("Testing simple agent invocation...")
        result = await agent.invoke_async("Say hello in exactly 3 words.")
        
        # Debug the result structure
        logger.info(f"Result type: {type(result)}")
        logger.info(f"Result content: {result}")
        
        # Try to extract content safely
        if hasattr(result, 'message') and hasattr(result.message, 'content'):
            response_content = result.message.content
        elif isinstance(result, dict) and 'content' in result:
            response_content = result['content']
        elif isinstance(result, dict) and 'message' in result:
            response_content = result['message']
        else:
            response_content = str(result)
            
        logger.info(f"✅ Agent response: {response_content}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Strands agent test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Run integration tests."""
    logger.info("🧪 Starting Strands Integration Tests")
    
    success = await test_strands_agent_creation()
    
    if success:
        logger.info("🎉 All integration tests passed!")
    else:
        logger.error("❌ Integration tests failed")
        
    return success

if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)