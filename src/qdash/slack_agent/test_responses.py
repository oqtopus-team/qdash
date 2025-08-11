#!/usr/bin/env python3.10
"""
Test improved Japanese responses.
"""

import asyncio
import logging
import os
from qdash.config import get_settings
from qdash.slack_agent.config_manager import get_current_model_config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_improved_responses():
    """Test improved Japanese responses."""
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
        
        # System prompt (improved)
        system_prompt = f"""あなたはQDash量子キャリブレーションシステムのSlackアシスタントです。

基本的な対応:
- 日本語で自然に返答してください
- 簡潔で親しみやすい口調で答えてください
- 挨拶には普通に挨拶で返してください

利用可能なツール:
- get_current_time: 現在時刻取得
- calculate: 数式計算

使用方針:
- 単純な挨拶や雑談には、ツールを使わず自然に返答してください

Model: {model_config.name}
"""
        
        # Create simple tools
        @tool
        async def get_current_time() -> str:
            """Get current time in JST timezone."""
            from datetime import datetime, timezone, timedelta
            jst = timezone(timedelta(hours=9))
            return datetime.now(tz=jst).strftime("%Y-%m-%d %H:%M:%S JST")
        
        @tool
        async def calculate(expression: str) -> float:
            """Calculate mathematical expression safely."""
            import ast
            import operator
            
            try:
                # Simple safe evaluation
                node = ast.parse(expression, mode='eval')
                return eval(compile(node, '<string>', 'eval'))
            except:
                return "計算エラー"
        
        # Create model configuration
        model_params = {
            "temperature": 0.3,  # Slightly higher for more natural responses
            "max_completion_tokens": 2000,
        }
        
        model = OpenAIModel(
            client_args={"api_key": api_key},
            model_id=model_config.name,
            params=model_params
        )
        
        # Create agent
        agent = Agent(
            model=model,
            system_prompt=system_prompt,
            tools=[get_current_time, calculate]
        )
        
        # Test various inputs
        test_cases = [
            "こんにちは",
            "おはよう！",
            "今何時ですか？",
            "2+3はいくつ？",
            "調子はどう？"
        ]
        
        logger.info("Testing improved responses:")
        for test_input in test_cases:
            logger.info(f"\n入力: {test_input}")
            result = await agent.invoke_async(test_input)
            response = str(result)
            logger.info(f"応答: {response}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Response test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Run response tests."""
    logger.info("🧪 Testing Improved Japanese Responses")
    
    success = await test_improved_responses()
    
    if success:
        logger.info("🎉 Response tests completed!")
    else:
        logger.error("❌ Response tests failed")
        
    return success

if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)