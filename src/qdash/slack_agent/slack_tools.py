from typing import Any

from qdash.slack_agent.agent import Tool, ToolParameter


class SlackTools:
    """Slack-specific tools that require client access."""

    def __init__(self, slack_client) -> None:
        self.slack_client = slack_client

    async def get_thread_history(self, channel_id: str, thread_ts: str) -> dict[str, Any]:
        """Get Slack thread history."""
        try:
            result = await self.slack_client.conversations_replies(
                channel=channel_id, ts=thread_ts, limit=50
            )

            messages = [
                {
                    "user": msg.get("user", "unknown"),
                    "text": msg.get("text", ""),
                    "ts": msg.get("ts", ""),
                    "type": msg.get("type", "message"),
                }
                for msg in result.get("messages", [])
            ]

            return {
                "channel_id": channel_id,
                "thread_ts": thread_ts,
                "message_count": len(messages),
                "messages": messages,
            }
        except Exception as e:
            return {"error": f"Failed to get thread history: {e!s}"}

    def get_tools(self) -> list[Tool]:
        """Get Slack tools."""
        return [
            Tool(
                name="get_thread_history",
                description="Get conversation history from a Slack thread",
                parameters=ToolParameter(
                    properties={
                        "channel_id": {"type": "string", "description": "Slack channel ID"},
                        "thread_ts": {"type": "string", "description": "Thread timestamp"},
                    },
                    required=["channel_id", "thread_ts"],
                ),
                function=self.get_thread_history,
            )
        ]
