"""
Enhanced error handling and monitoring for Strands Slack Agent.
"""

import asyncio
import logging
import traceback
from datetime import datetime
from functools import wraps
from typing import Any, Dict

logger = logging.getLogger(__name__)


class AgentError(Exception):
    """Base exception for agent errors."""

    pass


class ToolExecutionError(AgentError):
    """Exception raised when tool execution fails."""

    def __init__(self, tool_name: str, error: Exception):
        self.tool_name = tool_name
        self.original_error = error
        super().__init__(f"Tool '{tool_name}' failed: {error}")


class DatabaseConnectionError(AgentError):
    """Exception raised when database operations fail."""

    pass


class SlackAPIError(AgentError):
    """Exception raised when Slack API operations fail."""

    pass


class MetricsCollector:
    """Collects metrics for monitoring agent performance."""

    def __init__(self):
        self.metrics = {
            "tool_executions": {},
            "errors": {},
            "response_times": [],
            "user_interactions": 0,
            "successful_responses": 0,
            "failed_responses": 0,
        }
        self.start_time = datetime.now()

    def record_tool_execution(self, tool_name: str, success: bool, duration_ms: float):
        """Record tool execution metrics."""
        if tool_name not in self.metrics["tool_executions"]:
            self.metrics["tool_executions"][tool_name] = {
                "success_count": 0,
                "error_count": 0,
                "avg_duration_ms": 0,
                "total_duration_ms": 0,
                "call_count": 0,
            }

        tool_metrics = self.metrics["tool_executions"][tool_name]
        tool_metrics["call_count"] += 1
        tool_metrics["total_duration_ms"] += duration_ms
        tool_metrics["avg_duration_ms"] = tool_metrics["total_duration_ms"] / tool_metrics["call_count"]

        if success:
            tool_metrics["success_count"] += 1
        else:
            tool_metrics["error_count"] += 1

    def record_error(self, error_type: str, details: str = ""):
        """Record error occurrence."""
        if error_type not in self.metrics["errors"]:
            self.metrics["errors"][error_type] = {"count": 0, "last_occurrence": None, "details": []}

        self.metrics["errors"][error_type]["count"] += 1
        self.metrics["errors"][error_type]["last_occurrence"] = datetime.now().isoformat()
        if details:
            self.metrics["errors"][error_type]["details"].append(details)

    def record_user_interaction(self, success: bool, response_time_ms: float):
        """Record user interaction metrics."""
        self.metrics["user_interactions"] += 1
        self.metrics["response_times"].append(response_time_ms)

        if success:
            self.metrics["successful_responses"] += 1
        else:
            self.metrics["failed_responses"] += 1

    def get_health_status(self) -> Dict[str, Any]:
        """Get current health status."""
        uptime = (datetime.now() - self.start_time).total_seconds()
        success_rate = self.metrics["successful_responses"] / max(self.metrics["user_interactions"], 1) * 100

        avg_response_time = sum(self.metrics["response_times"]) / max(len(self.metrics["response_times"]), 1)

        return {
            "status": "healthy" if success_rate > 80 else "degraded" if success_rate > 50 else "unhealthy",
            "uptime_seconds": uptime,
            "success_rate_percent": success_rate,
            "avg_response_time_ms": avg_response_time,
            "total_interactions": self.metrics["user_interactions"],
            "total_errors": sum(error["count"] for error in self.metrics["errors"].values()),
            "tool_health": {
                name: {
                    "success_rate": stats["success_count"] / max(stats["call_count"], 1) * 100,
                    "avg_duration_ms": stats["avg_duration_ms"],
                }
                for name, stats in self.metrics["tool_executions"].items()
            },
        }

    def log_status_report(self):
        """Log periodic status report."""
        health = self.get_health_status()
        logger.info(f"📊 Agent Health Report: {health['status'].upper()}")
        logger.info(f"  Uptime: {health['uptime_seconds']:.1f}s")
        logger.info(f"  Success Rate: {health['success_rate_percent']:.1f}%")
        logger.info(f"  Avg Response Time: {health['avg_response_time_ms']:.1f}ms")
        logger.info(f"  Total Interactions: {health['total_interactions']}")
        logger.info(f"  Total Errors: {health['total_errors']}")


# Global metrics collector instance
metrics = MetricsCollector()


def with_error_handling(func):
    """Decorator for enhanced error handling with metrics."""

    @wraps(func)
    async def wrapper(*args, **kwargs):
        start_time = datetime.now()
        tool_name = getattr(func, "_tool_name", func.__name__)

        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)

            # Record successful execution
            duration = (datetime.now() - start_time).total_seconds() * 1000
            metrics.record_tool_execution(tool_name, True, duration)

            logger.debug(f"✅ Tool '{tool_name}' executed successfully in {duration:.1f}ms")
            return result

        except Exception as e:
            # Record failed execution
            duration = (datetime.now() - start_time).total_seconds() * 1000
            metrics.record_tool_execution(tool_name, False, duration)
            metrics.record_error(f"tool_{tool_name}", str(e))

            logger.error(f"❌ Tool '{tool_name}' failed after {duration:.1f}ms: {e}")
            logger.debug(f"Stack trace: {traceback.format_exc()}")

            # Return user-friendly error message
            if "database" in str(e).lower() or "mongo" in str(e).lower():
                return "⚠️ データベース接続エラーが発生しました。管理者に連絡してください。"
            elif "timeout" in str(e).lower():
                return "⏱️ 処理がタイムアウトしました。しばらく待ってから再試行してください。"
            elif "permission" in str(e).lower() or "auth" in str(e).lower():
                return "🔒 認証エラーが発生しました。権限を確認してください。"
            else:
                return f"⚠️ エラーが発生しました: {tool_name}の実行に失敗しました。"

    return wrapper


def log_slack_event(event_type: str, channel: str, user: str, message: str):
    """Log Slack events for monitoring."""
    logger.info(f"📨 Slack Event: {event_type}")
    logger.info(f"  Channel: {channel}")
    logger.info(f"  User: {user}")
    logger.info(f"  Message: {message[:100]}...")


async def setup_periodic_health_check():
    """Setup periodic health check logging."""
    while True:
        try:
            await asyncio.sleep(300)  # 5 minutes
            metrics.log_status_report()
        except Exception as e:
            logger.error(f"Health check failed: {e}")


def handle_critical_error(error: Exception, context: str = ""):
    """Handle critical errors that might require intervention."""
    error_msg = f"🚨 CRITICAL ERROR in {context}: {error}"
    logger.critical(error_msg)
    logger.critical(f"Stack trace: {traceback.format_exc()}")

    # Record critical error
    metrics.record_error("critical_error", error_msg)

    # In production, this could trigger alerts (Slack, email, etc.)
    return "🚨 重大なエラーが発生しました。システム管理者に自動的に通知されました。"
