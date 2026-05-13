"""Compatibility wrapper for the shared copilot agent implementation."""

from qdash.common.copilot import agent as _agent

AGENT_TOOLS = _agent.AGENT_TOOLS
blocks_to_markdown = _agent.blocks_to_markdown
run_analysis = _agent.run_analysis
run_chat = _agent.run_chat
_build_client = _agent._build_client
_build_llm_summary = _agent._build_llm_summary
_legacy_to_blocks = _agent._legacy_to_blocks
_parse_response = _agent._parse_response
_run_chat_completions = _agent._run_chat_completions
_wrap_tool_executors = _agent._wrap_tool_executors
