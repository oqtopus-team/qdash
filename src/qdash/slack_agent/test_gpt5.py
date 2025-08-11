#!/usr/bin/env python3.10
"""
Test GPT-5 availability with different approaches.
"""

import asyncio
import logging
import os
from qdash.config import get_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_direct_openai_gpt5():
    """Test GPT-5 with direct OpenAI client."""
    try:
        from openai import OpenAI
        
        settings = get_settings()
        api_key = getattr(settings, 'openai_api_key', None) or os.getenv("OPENAI_API_KEY")
        
        if not api_key:
            logger.error("❌ No OpenAI API key available")
            return False
            
        client = OpenAI(
            api_key=api_key,
            timeout=30.0,
            max_retries=3
        )
        
        # Test with responses.create() (GPT-5 preferred method)
        logger.info("Testing GPT-5 with responses.create()...")
        try:
            response = client.responses.create(
                model="gpt-5",
                input="Say hello in Japanese",
                reasoning={"effort": "minimal"}
            )
            content = getattr(response, 'output_text', str(response))
            logger.info(f"✅ GPT-5 responses.create() success: {content}")
            return True
        except Exception as e:
            logger.warning(f"⚠️ responses.create() failed: {e}")
        
        # Fallback: Test with chat.completions.create()
        logger.info("Testing GPT-5 with chat.completions.create()...")
        try:
            response = client.chat.completions.create(
                model="gpt-5",
                messages=[{"role": "user", "content": "Say hello in Japanese"}],
                max_completion_tokens=100,
                temperature=0.3
            )
            content = response.choices[0].message.content
            logger.info(f"✅ GPT-5 chat.completions success: {content}")
            return True
        except Exception as e:
            logger.warning(f"⚠️ chat.completions failed: {e}")
            
        return False
        
    except Exception as e:
        logger.error(f"❌ Direct OpenAI test failed: {e}")
        return False

async def test_strands_gpt5():
    """Test GPT-5 with Strands (may not work yet)."""
    try:
        from strands import Agent
        from strands.models.openai import OpenAIModel
        
        settings = get_settings()
        api_key = getattr(settings, 'openai_api_key', None) or os.getenv("OPENAI_API_KEY")
        
        if not api_key:
            logger.error("❌ No OpenAI API key available")
            return False
        
        logger.info("Testing GPT-5 with Strands...")
        
        # Try to create Strands agent with GPT-5
        model = OpenAIModel(
            client_args={
                "api_key": api_key,
                "timeout": 30.0,
                "max_retries": 3,
            },
            model_id="gpt-5",
            params={
                "temperature": 0.3,
                "max_completion_tokens": 100,
            }
        )
        
        agent = Agent(
            model=model,
            system_prompt="You are a helpful assistant. Respond in Japanese.",
        )
        
        result = await agent.invoke_async("Say hello")
        logger.info(f"✅ Strands GPT-5 success: {result}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Strands GPT-5 test failed: {e}")
        return False

async def main():
    """Run GPT-5 tests."""
    logger.info("🧪 Testing GPT-5 Availability")
    
    # Test direct OpenAI approach
    direct_success = await test_direct_openai_gpt5()
    
    # Test Strands approach
    strands_success = await test_strands_gpt5()
    
    if direct_success:
        logger.info("✅ GPT-5 is available via direct OpenAI client")
    if strands_success:
        logger.info("✅ GPT-5 works with Strands")
    
    if not direct_success and not strands_success:
        logger.error("❌ GPT-5 is not available with current setup")
    
    return direct_success or strands_success

if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)