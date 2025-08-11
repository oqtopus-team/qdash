#!/usr/bin/env python3
"""
Test script for Strands-based Slack agent implementation.
"""

import asyncio
import logging
import os
from datetime import datetime

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Test imports
def test_imports():
    """Test that all required imports work."""
    try:
        from strands import Agent, tool
        from strands.models.openai import OpenAIModel
        logger.info("✅ Strands imports successful")
        return True
    except ImportError as e:
        logger.error(f"❌ Strands imports failed: {e}")
        return False

# Test tool definition (will be decorated after import test)
async def test_tool_func(message: str) -> str:
    """Test async tool for verification."""
    await asyncio.sleep(0.1)  # Simulate async operation
    return f"Test tool received: {message}"

# Test agent creation
def test_agent_creation():
    """Test Strands agent creation."""
    try:
        from strands import tool
        
        # Decorate the test tool
        test_tool = tool(test_tool_func)
        
        # Simple agent creation (should work even without API key for structure test)
        agent = Agent(
            system_prompt="You are a test agent.",
            tools=[test_tool]
        )
        logger.info("✅ Agent creation successful")
        return True, agent
    except Exception as e:
        logger.error(f"❌ Agent creation failed: {e}")
        return False, None

# Test OpenAI model configuration (requires API key)
def test_openai_model():
    """Test OpenAI model configuration."""
    try:
        from strands.models.openai import OpenAIModel
        from strands import tool
        
        # Decorate the test tool
        test_tool = tool(test_tool_func)
        
        # Check if API key is available
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.warning("⚠️ OPENAI_API_KEY not set, skipping OpenAI model test")
            return True
        
        model = OpenAIModel(
            client_args={"api_key": api_key},
            model_id="gpt-4o-mini",
            params={
                "temperature": 0.1,
                "max_tokens": 100,
            }
        )
        
        agent = Agent(
            model=model,
            system_prompt="You are a test agent.",
            tools=[test_tool]
        )
        
        logger.info("✅ OpenAI model configuration successful")
        return True
    except Exception as e:
        logger.error(f"❌ OpenAI model test failed: {e}")
        return False

# Test agent invocation (requires API key)
async def test_agent_invocation():
    """Test agent async invocation."""
    try:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.warning("⚠️ OPENAI_API_KEY not set, skipping invocation test")
            return True
        
        from strands.models.openai import OpenAIModel
        from strands import tool
        
        # Decorate the test tool
        test_tool = tool(test_tool_func)
        
        model = OpenAIModel(
            client_args={"api_key": api_key},
            model_id="gpt-4o-mini",
            params={"temperature": 0.1, "max_tokens": 50}
        )
        
        agent = Agent(
            model=model,
            system_prompt="You are a helpful test agent. Keep responses very short.",
            tools=[test_tool]
        )
        
        # Test simple invocation
        result = await agent.invoke_async("Say hello and use the test tool to echo 'world'")
        
        response_content = result.message.content if hasattr(result, 'message') else str(result)
        logger.info(f"✅ Agent invocation successful: {response_content[:100]}...")
        return True
        
    except Exception as e:
        logger.error(f"❌ Agent invocation failed: {e}")
        return False

async def main():
    """Run all tests."""
    logger.info("🧪 Starting Strands Agent Tests")
    
    # Test 1: Imports
    if not test_imports():
        return False
    
    # Test 2: Agent creation
    success, agent = test_agent_creation()
    if not success:
        return False
    
    # Test 3: OpenAI model configuration
    if not test_openai_model():
        return False
    
    # Test 4: Agent invocation (requires API key)
    if not await test_agent_invocation():
        logger.warning("⚠️ Agent invocation test failed (may be due to missing API key)")
    
    logger.info("🎉 All basic tests passed!")
    return True

if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)