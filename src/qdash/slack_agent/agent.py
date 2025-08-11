"""
Strands-based Slack agent implementation for QDash quantum calibration system.
This is the full migration to Strands Agents SDK.
"""

import asyncio
import logging
import os
import statistics
from datetime import datetime
from typing import Any

import pendulum
from pydantic import BaseModel
from qdash.config import get_settings
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.initialize import initialize
from qdash.slack_agent.config_manager import get_current_model_config
from qdash.slack_agent.error_handlers import (
    handle_critical_error,
    log_slack_event,
    metrics,
    setup_periodic_health_check,
    with_error_handling,
)
from qdash.slack_agent.models import SlackEvent
from slack_bolt.adapter.socket_mode.aiohttp import AsyncSocketModeHandler
from slack_bolt.async_app import AsyncApp

# Import Strands Agents SDK
try:
    from strands import Agent, tool
    from strands.models.openai import OpenAIModel

    STRANDS_AVAILABLE = True
    print("✅ Strands Agents SDK imported successfully")
except ImportError as e:
    print(f"❌ Strands Agents SDK not available: {e}")
    STRANDS_AVAILABLE = False

    # Fallback tool decorator
    def tool(func):
        """Fallback tool decorator when Strands is not available."""
        func._is_tool = True
        func._tool_name = func.__name__
        return func


# Initialize database
initialize()

settings = get_settings()

# Enhanced logging configuration

log_dir = os.path.dirname(os.path.abspath(__file__))
log_file = os.path.join(log_dir, "log", "agent.log")

# Ensure log directory exists
os.makedirs(os.path.dirname(log_file), exist_ok=True)

logging.basicConfig(
    level=getattr(logging, settings.log_level, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler(log_file, encoding="utf-8")],
)
logger = logging.getLogger(__name__)

# Slack App initialization with error handling
try:
    app = AsyncApp(token=settings.slack_bot_token)
    logger.info("✅ Slack app initialized successfully")
except Exception as e:
    logger.error(f"❌ Failed to initialize Slack app: {e}")
    raise


@tool
@with_error_handling
async def get_current_time() -> str:
    """Get current time in JST timezone."""
    from datetime import timedelta, timezone

    jst = timezone(timedelta(hours=9))
    return datetime.now(tz=jst).strftime("%Y-%m-%d %H:%M:%S JST")


@tool
@with_error_handling
async def calculate(expression: str) -> float:
    """Calculate mathematical expression safely."""
    try:
        import ast
        import operator

        # Validate expression safety
        if any(dangerous in expression for dangerous in ["import", "__", "exec", "eval"]):
            raise ValueError("Potentially dangerous expression detected")

        # Parse and evaluate safely using a controlled evaluator
        def safe_eval(node):
            if isinstance(node, ast.Expression):
                return safe_eval(node.body)
            elif isinstance(node, ast.Constant):  # Python 3.8+
                return node.value
            elif isinstance(node, ast.Num):  # For older Python versions
                return node.n
            elif isinstance(node, ast.BinOp):
                ops = {
                    ast.Add: operator.add,
                    ast.Sub: operator.sub,
                    ast.Mult: operator.mul,
                    ast.Div: operator.truediv,
                    ast.Pow: operator.pow,
                    ast.Mod: operator.mod,
                    ast.FloorDiv: operator.floordiv,
                }
                if type(node.op) not in ops:
                    raise ValueError(f"Unsupported operation: {type(node.op)}")
                return ops[type(node.op)](safe_eval(node.left), safe_eval(node.right))
            elif isinstance(node, ast.UnaryOp):
                ops = {ast.UAdd: operator.pos, ast.USub: operator.neg}
                if type(node.op) not in ops:
                    raise ValueError(f"Unsupported unary operation: {type(node.op)}")
                return ops[type(node.op)](safe_eval(node.operand))
            else:
                raise ValueError(f"Unsupported node type: {type(node)}")

        node = ast.parse(expression, mode="eval")
        result = safe_eval(node)
        return float(result)

    except Exception as e:
        raise ValueError(f"Calculation error: {e!s}")


@tool
@with_error_handling
async def get_string_length(text: str) -> int:
    """Get string length."""
    if not isinstance(text, str):
        raise ValueError("Input must be a string")
    return len(text)


@tool
@with_error_handling
async def get_current_chip(username: str = "admin") -> str:
    """Get current quantum chip ID for a user."""
    try:
        chip = ChipDocument.get_current_chip(username)
        if chip:
            logger.info(f"Retrieved current chip for user {username}: {chip.chip_id}")
            return str(chip.chip_id)
        logger.warning(f"No current chip found for user {username}")
        return f"No current chip found for user {username}"
    except Exception as e:
        logger.error(f"Database error retrieving current chip for {username}: {e}")
        raise


class ChipParameterInfo(BaseModel):
    """Chip parameter information model."""

    chip_id: str
    username: str
    qubit_count: int
    qubit_parameters: dict[str, dict[str, Any]]
    coupling_parameters: dict[str, dict[str, Any]]
    statistics: dict[str, Any]


@tool
async def get_chip_parameters(
    chip_id: str | None = None,
    username: str = "admin",
    calculate_stats: bool = True,
    within_24hrs: bool = False,
) -> dict[str, Any]:
    """Get quantum chip parameter information including fidelity statistics.

    Args:
        chip_id: Chip ID to get parameters for (if None, uses current chip)
        username: Username to filter by (default: "admin")
        calculate_stats: Whether to calculate statistics like median fidelity
        within_24hrs: Whether to only include parameters from last 24 hours

    Returns:
        Chip parameter information including fidelity data
    """
    # Get current chip if not specified
    if chip_id is None:
        current_chip = ChipDocument.get_current_chip(username)
        if current_chip:
            chip_id = current_chip.chip_id
        else:
            return {"error": f"No current chip found for user {username} and no chip_id specified"}

    # Get chip document
    chip = ChipDocument.find_one({"chip_id": chip_id, "username": username}).run()
    if not chip:
        return {"error": f"Chip {chip_id} not found for user {username}"}

    # Field mapping based on chip_report implementation
    qubit_field_map = {
        "bare_frequency": "qubit_frequency",
        "t1": "t1",
        "t2_echo": "t2_echo",
        "t2_star": "t2_star",
        "average_readout_fidelity": "average_readout_fidelity",
        "x90_gate_fidelity": "x90_gate_fidelity",
        "x180_gate_fidelity": "x180_gate_fidelity",
    }

    coupling_field_map = {
        "static_zz_interaction": "static_zz_interaction",
        "qubit_qubit_coupling_strength": "qubit_qubit_coupling_strength",
        "zx90_gate_fidelity": "zx90_gate_fidelity",
        "bell_state_fidelity": "bell_state_fidelity",
    }

    # Filter by time if requested
    cutoff_time = None
    if within_24hrs:
        cutoff_time = pendulum.now("Asia/Tokyo").subtract(hours=24)

    # Extract qubit parameters
    qubit_params = {}
    readout_fidelities = []
    x90_gate_fidelities = []
    x180_gate_fidelities = []

    for qid, qubit_model in chip.qubits.items():
        params = {}
        if qubit_model.data and isinstance(qubit_model.data, dict):
            for param_name, param_data in qubit_model.data.items():
                if isinstance(param_data, dict) and "value" in param_data:
                    # Check time filter
                    include_param = True
                    if within_24hrs and "calibrated_at" in param_data:
                        try:
                            calibrated_at = pendulum.parse(param_data["calibrated_at"], tz="Asia/Tokyo")
                            include_param = calibrated_at >= cutoff_time
                        except Exception:
                            include_param = False

                    if include_param:
                        display_name = qubit_field_map.get(param_name, param_name)
                        value = param_data.get("value")

                        # Convert time units (us -> ns) for t1, t2 parameters
                        if display_name.startswith("t") and value is not None:
                            value = value * 1e3  # us -> ns

                        params[display_name] = {
                            "value": value,
                            "unit": param_data.get("unit", ""),
                            "calibrated_at": param_data.get("calibrated_at", ""),
                        }

                        # Collect fidelity values for statistics
                        if isinstance(value, (int, float)) and 0 <= value <= 1:
                            if display_name == "average_readout_fidelity":
                                readout_fidelities.append(value)
                            elif display_name == "x90_gate_fidelity":
                                x90_gate_fidelities.append(value)
                            elif display_name == "x180_gate_fidelity":
                                x180_gate_fidelities.append(value)
        qubit_params[qid] = params

    # Extract coupling parameters
    coupling_params = {}
    zx90_gate_fidelities = []
    bell_state_fidelities = []

    for coupling_id, coupling_model in chip.couplings.items():
        params = {}
        if coupling_model.data and isinstance(coupling_model.data, dict):
            for param_name, param_data in coupling_model.data.items():
                if isinstance(param_data, dict) and "value" in param_data:
                    # Check time filter
                    include_param = True
                    if within_24hrs and "calibrated_at" in param_data:
                        try:
                            calibrated_at = pendulum.parse(param_data["calibrated_at"], tz="Asia/Tokyo")
                            include_param = calibrated_at >= cutoff_time
                        except Exception:
                            include_param = False

                    if include_param:
                        display_name = coupling_field_map.get(param_name, param_name)
                        value = param_data.get("value")

                        # Validate fidelity values
                        if "fidelity" in display_name and value is not None and value > 1.0:
                            value = None

                        params[display_name] = {
                            "value": value,
                            "unit": param_data.get("unit", ""),
                            "calibrated_at": param_data.get("calibrated_at", ""),
                        }

                        # Collect fidelity values for statistics
                        if isinstance(value, (int, float)) and 0 <= value <= 1:
                            if display_name == "zx90_gate_fidelity":
                                zx90_gate_fidelities.append(value)
                            elif display_name == "bell_state_fidelity":
                                bell_state_fidelities.append(value)
        coupling_params[coupling_id] = params

    # Calculate statistics
    stats = {}
    if calculate_stats:

        def calc_stats(values):
            if values:
                return {
                    "count": len(values),
                    "mean": round(statistics.mean(values), 6),
                    "median": round(statistics.median(values), 6),
                    "min": round(min(values), 6),
                    "max": round(max(values), 6),
                    "stdev": round(statistics.stdev(values), 6) if len(values) > 1 else 0,
                }
            return None

        if readout_fidelities:
            stats["readout_fidelity"] = calc_stats(readout_fidelities)
        if x90_gate_fidelities:
            stats["x90_gate_fidelity"] = calc_stats(x90_gate_fidelities)
        if x180_gate_fidelities:
            stats["x180_gate_fidelity"] = calc_stats(x180_gate_fidelities)
        if zx90_gate_fidelities:
            stats["zx90_gate_fidelity"] = calc_stats(zx90_gate_fidelities)
        if bell_state_fidelities:
            stats["bell_state_fidelity"] = calc_stats(bell_state_fidelities)

    result = ChipParameterInfo(
        chip_id=chip_id,
        username=username,
        qubit_count=len(chip.qubits),
        qubit_parameters=qubit_params,
        coupling_parameters=coupling_params,
        statistics=stats,
    )

    return result.model_dump()


def format_chip_parameters_for_slack(parameters: dict[str, Any]) -> str:
    """Format chip parameters for readable Slack output."""
    if "error" in parameters:
        return f"Error: {parameters['error']}"

    chip_id = parameters.get("chip_id", "Unknown")
    username = parameters.get("username", "Unknown")
    qubit_count = parameters.get("qubit_count", 0)

    lines = [
        f"**Chip Parameters for {chip_id}** (User: {username})",
        f"Total Qubits: {qubit_count}",
        "",
    ]

    # Statistics section
    stats = parameters.get("statistics", {})
    if stats:
        lines.append("**Fidelity Statistics:**")

        if "readout_fidelity" in stats:
            rf = stats["readout_fidelity"]
            lines.extend(
                [
                    "• **Readout Fidelity:**",
                    f"  - Measurements: {rf['count']}",
                    f"  - Median: **{rf['median']:.1%}** ({rf['median']:.3f})",
                    f"  - Mean: {rf['mean']:.1%} ({rf['mean']:.3f})",
                    f"  - Range: {rf['min']:.1%} - {rf['max']:.1%}",
                    "",
                ]
            )

        if "x90_gate_fidelity" in stats:
            x90f = stats["x90_gate_fidelity"]
            lines.extend(
                [
                    "• **X90 Gate Fidelity:**",
                    f"  - Measurements: {x90f['count']}",
                    f"  - Median: **{x90f['median']:.1%}** ({x90f['median']:.3f})",
                    f"  - Mean: {x90f['mean']:.1%} ({x90f['mean']:.3f})",
                    f"  - Range: {x90f['min']:.1%} - {x90f['max']:.1%}",
                    "",
                ]
            )

        if "x180_gate_fidelity" in stats:
            x180f = stats["x180_gate_fidelity"]
            lines.extend(
                [
                    "• **X180 Gate Fidelity:**",
                    f"  - Measurements: {x180f['count']}",
                    f"  - Median: **{x180f['median']:.1%}** ({x180f['median']:.3f})",
                    f"  - Mean: {x180f['mean']:.1%} ({x180f['mean']:.3f})",
                    f"  - Range: {x180f['min']:.1%} - {x180f['max']:.1%}",
                    "",
                ]
            )
    else:
        lines.append("No fidelity statistics available")

    # Data availability
    qubit_params = parameters.get("qubit_parameters", {})
    coupling_params = parameters.get("coupling_parameters", {})

    qubits_with_data = sum(1 for params in qubit_params.values() if params)
    couplings_with_data = sum(1 for params in coupling_params.values() if params)

    lines.extend(
        [
            "**Data Availability:**",
            f"• Qubits with calibration data: {qubits_with_data}/{len(qubit_params)}",
            f"• Couplings with calibration data: {couplings_with_data}/{len(coupling_params)}",
        ]
    )

    return "\n".join(lines)


# Global agent cache for thread-based context management
_agent_cache: dict[str, Agent] = {}
_agent_cache_lock = asyncio.Lock()

# Current thread context for passing to tools
_current_thread_context: dict[str, Any] = {}


def get_thread_key(channel_id: str, thread_ts: str | None, user_id: str) -> str:
    """Generate a unique key for thread-based agent caching with strict separation."""
    if thread_ts:
        # Thread-based conversations: each thread gets its own agent
        return f"thread:{channel_id}:{thread_ts}"
    else:
        # Non-threaded messages: each message gets completely isolated context
        # Use timestamp to ensure no context bleeding between separate messages
        import time

        timestamp = int(time.time() * 1000)
        return f"single:{channel_id}:{user_id}:{timestamp}"


async def get_or_create_thread_agent(
    channel_id: str, thread_ts: str | None, user_id: str, username: str = "admin"
) -> Agent:
    """Get or create a Strands agent for a specific Slack thread with context management."""
    thread_key = get_thread_key(channel_id, thread_ts, user_id)

    async with _agent_cache_lock:
        if thread_key in _agent_cache:
            logger.info(f"🔄 Reusing existing agent for thread: {thread_key} (preserving context)")
            return _agent_cache[thread_key]

        logger.info(f"🆕 Creating new agent for thread: {thread_key} (fresh context)")

        # Create new agent with conversation management
        model_config = get_current_model_config()

        # System instructions optimized for thread context
        system_prompt = f"""あなたはQDash量子キャリブレーションシステムのSlackアシスタントです。

このスレッドでのSlackユーザー: (ID: {user_id})
QDashユーザー名: 各操作時に明示的に指定が必要

**重要なセッション管理:**
- このエージェントは特定のSlackスレッド専用です（Thread Key: {thread_key}）
- 他のスレッドやチャンネルでの会話は一切記憶していません
- スレッドが変わると完全に新しいセッションとして動作します
- このスレッド内でのみ会話履歴を記憶し、コンテクストを保持してください

基本的な対応:
- 日本語で自然に返答してください
- 簡潔で親しみやすい口調で答えてください
- 前回の会話内容を覚えて、継続性のある対話を心がけてください
- 同じ質問を繰り返された場合は「先ほどお答えしましたが...」のように言及してください

利用可能なツール:
- get_chip_parameters_formatted: チップのフィデリティ統計とパラメータ取得
- get_current_chip: 現在のチップID取得
- generate_chip_report: フルチップレポート(YAML+PDF)生成とSlack送信（現在のスレッドに送信、カットオフ時間指定可能）

- get_current_time: 現在時刻取得
- calculate: 数式計算
- get_string_length: 文字列長取得

ユーザー名の取り扱い:
- QDashユーザー名は**必ず明示的に指定**してもらいます
- Slackユーザー情報からの自動推測は行いません
- ユーザー名が指定されていない場合、必ずユーザーに確認してください

使用方針:

**自然な表現の理解:**
- 「orangekame3のレポートをください」→ orangekame3でチップレポート生成
- 「orangekame3の過去48時間のレポートを生成して」→ orangekame3で48時間のチップレポート生成
- 「johnのフィデリティを見たい」→ johnでチップパラメータ取得
- 「aliceの現在のチップは？」→ aliceで現在チップID取得
- 「admin でレポート作って」→ adminでチップレポート生成（cutoff_hours=24）
- 「admin の12時間レポート作って」→ adminでチップレポート生成（cutoff_hours=12）

**パターン認識:**
1. **ユーザー名 + の + 操作**: 「{{ユーザー名}}の{{操作}}」形式を認識
2. **操作キーワード**:
   - レポート/チップレポート → generate_chip_report
   - フィデリティ/パラメータ → get_chip_parameters_formatted
   - チップID/現在のチップ → get_current_chip
3. **ユーザー名抽出**: メッセージから英数字のユーザー名を識別

**応答方針:**
- 1回のメッセージでユーザー名と操作の両方が特定できる場合は即座に実行
- どちらか一方が不明確な場合のみ確認
- 冗長な確認は避け、できるだけ自然で効率的な対話を心がける
- extract_username_and_action関数でメッセージを解析し、自然な表現を理解する
- この関数はユーザー名、アクション、時間指定（cutoff_hours）を抽出します

**🚨 重要: レポート生成の即座実行**
「orangekame3の過去48時間のレポートを生成して」のようなメッセージの場合:
→ 他のツールを使わず、即座にgenerate_chip_report(username="orangekame3", cutoff_hours=48)を実行
→ get_current_chipやget_chip_parametersは不要です

4. フィデリティやチップに関する質問: get_chip_parameters_formatted を使用
5. "最新のchip id"に関する質問: get_current_chip を使用
6. "チップレポート"や"レポート生成"の依頼: 🚨 **即座に** generate_chip_report を使用
   **絶対ルール**: ユーザー名とレポート依頼が明確な場合、他のツールを使わずに直接generate_chip_reportを実行
   **重要**: このスレッドのチャンネルID="{channel_id}", スレッドTS="{thread_ts if thread_ts else ''}"
   
   **時間指定の処理**:
   - ユーザーメッセージから時間を抽出（例: "48時間", "12h", "過去24時間"など）
   - 抽出した時間をcutoff_hoursパラメータに設定
   - 時間指定がない場合はデフォルト24時間を使用
   
   generate_chip_reportを呼ぶ際は必ずこれらの値を使用:
   generate_chip_report(username="指定されたユーザー名", slack_channel="{channel_id}", slack_thread_ts="{thread_ts if thread_ts else ''}", cutoff_hours=48)
   
   **時間指定の理解:**
   - 「過去48時間のレポート」「48時間のレポート」→ cutoff_hours=48
   - 「12hのレポート」「12時間レポート」→ cutoff_hours=12  
   - 時間指定がない場合はcutoff_hours=24（デフォルト）
   - extract_username_and_action関数で時間も抽出してください
7. 単純な挨拶や雑談には、ツールを使わず自然に返答してください

**❌ 禁止事項:**
- レポート生成依頼でget_current_chipを先に呼ぶこと
- レポート生成前にフィデリティを確認すること  
- 「現在のチップIDを取得する必要があります」のような余計な前置き

**✅ 正しい処理:**
「orangekame3の過去48時間のレポートを生成して」
→ 即座に: generate_chip_report(username="orangekame3", cutoff_hours=48, slack_channel="{channel_id}", slack_thread_ts="{thread_ts}")

Model: {model_config.name}
Thread: {thread_key}
"""

        # Prepare tools list
        tools = [
            get_current_time,
            calculate,
            get_string_length,
            get_current_chip,
            get_chip_parameters_formatted,
            get_thread_history,
            generate_chip_report,
        ]

        # Configure conversation manager for thread context
        from strands.agent.conversation_manager import SlidingWindowConversationManager

        conversation_manager = SlidingWindowConversationManager(
            window_size=20,  # Keep last 20 messages for good context
            should_truncate_results=True,  # Truncate large tool results
        )

        # Initialize agent state with user information
        initial_state = {
            "user_id": user_id,
            "username": username,
            "channel_id": channel_id,
            "thread_ts": thread_ts,
            "created_at": pendulum.now("Asia/Tokyo").isoformat(),
            "interaction_count": 0,
        }

        if STRANDS_AVAILABLE:
            # Configure model based on provider
            if model_config.provider == "openai":
                # Get API key from environment variable only (security requirement)
                api_key = os.getenv("OPENAI_API_KEY")
                if not api_key:
                    raise ValueError("OPENAI_API_KEY environment variable is required for security")

                # Create OpenAI model configuration
                model_params = {
                    "temperature": model_config.temperature,
                    "max_completion_tokens": model_config.max_completion_tokens,
                }

                model = OpenAIModel(
                    client_args={
                        "api_key": api_key,
                        "timeout": 30.0,
                        "max_retries": 3,
                    },
                    model_id=model_config.name,
                    params=model_params,
                )

                # Create Strands Agent with full context management
                agent = Agent(
                    model=model,
                    system_prompt=system_prompt,
                    tools=tools,
                    conversation_manager=conversation_manager,
                    state=initial_state,
                )
                logger.info(f"✅ Thread agent created with OpenAI model: {model_config.name}")
            else:
                # For other providers
                agent = Agent(
                    system_prompt=system_prompt,
                    tools=tools,
                    conversation_manager=conversation_manager,
                    state=initial_state,
                )
                logger.info("✅ Thread agent created with default configuration")
        else:
            logger.error("❌ Strands SDK is not available")
            raise ImportError("Strands Agents SDK is required")

        # Cache the agent for this thread
        _agent_cache[thread_key] = agent

        # Clean up old cached agents (keep only last 30 threads for better isolation)
        if len(_agent_cache) > 30:
            # Remove oldest entries to prevent memory buildup and ensure fresh contexts
            oldest_keys = list(_agent_cache.keys())[:-30]
            for old_key in oldest_keys:
                del _agent_cache[old_key]
                logger.info(f"🗑️ Cleaned up old thread agent: {old_key}")
            logger.info(f"📊 Agent cache size after cleanup: {len(_agent_cache)}")

        return agent


async def update_agent_state(agent: Agent, interaction_type: str = "message"):
    """Update agent state with interaction metadata."""
    current_count = agent.state.get("interaction_count") or 0
    agent.state.set("interaction_count", current_count + 1)
    agent.state.set("last_interaction", pendulum.now("Asia/Tokyo").isoformat())
    agent.state.set("last_interaction_type", interaction_type)


def cleanup_agent_cache():
    """Cleanup function for agent cache (can be called periodically)."""
    global _agent_cache
    logger.info(f"🧹 Cleaning up agent cache. Current size: {len(_agent_cache)}")
    _agent_cache.clear()


async def require_explicit_username(specified_username: str | None = None) -> str:
    """Always require explicit username specification.

    Args:
        specified_username: Username explicitly specified by user

    Returns:
        Validated QDash username

    Raises:
        ValueError: When no username is specified
    """
    if specified_username:
        logger.info(f"Using explicitly specified username: {specified_username}")
        return specified_username
    else:
        error_msg = """QDashユーザー名を明示的に指定してください。
                    例：「ユーザー名 john でチップレポートを生成して」"""
        logger.info(f"Username validation failed: {error_msg}")
        raise ValueError(error_msg)


async def get_validated_qdash_username(user_id: str, specified_username: str | None = None) -> str:
    """Get validated QDash username - always requires explicit specification.

    Args:
        user_id: Slack user ID (not used for automatic mapping)
        specified_username: Username explicitly specified by user

    Returns:
        Validated QDash username

    Raises:
        ValueError: When no username is specified
    """
    return await require_explicit_username(specified_username)


def extract_username_and_action(message: str) -> tuple[str | None, str | None, int | None]:
    """Extract username, action, and cutoff hours from natural user messages.

    Args:
        message: User message text

    Returns:
        Tuple of (username, action, cutoff_hours) or (None, None, None) if not found
    """
    import re

    message = message.lower().strip()
    
    # Extract cutoff hours from message
    cutoff_hours = None
    hour_patterns = [
        r'過去(\d+)時間',
        r'(\d+)時間',  
        r'(\d+)h',
        r'(\d+)hr',
        r'(\d+)hrs'
    ]
    
    for pattern in hour_patterns:
        match = re.search(pattern, message)
        if match:
            cutoff_hours = int(match.group(1))
            break

    # Pattern 1: "{username}の{action}" - Japanese possessive
    pattern1 = r"(\w+)の(レポート|フィデリティ|パラメータ|チップ)"
    match1 = re.search(pattern1, message)
    if match1:
        username = match1.group(1)
        action_word = match1.group(2)

        # Map action words to actions
        action_map = {"レポート": "report", "フィデリティ": "fidelity", "パラメータ": "parameters", "チップ": "chip"}
        action = action_map.get(action_word)
        return username, action, cutoff_hours

    # Pattern 2: "{username} で {action}" - Japanese particle "de"
    pattern2 = r"(\w+)\s*で.*(レポート|フィデリティ|パラメータ|チップ)"
    match2 = re.search(pattern2, message)
    if match2:
        username = match2.group(1)
        action_word = match2.group(2)
        action_map = {"レポート": "report", "フィデリティ": "fidelity", "パラメータ": "parameters", "チップ": "chip"}
        action = action_map.get(action_word, "unknown")
        return username, action, cutoff_hours

    # Pattern 3: General report/レポート keywords
    if "レポート" in message or "report" in message:
        # Look for username patterns (alphanumeric sequences)
        username_pattern = r"\b([a-zA-Z0-9_]+)\b"
        usernames = re.findall(username_pattern, message)
        # Filter out common words
        excluded_words = {"で", "を", "の", "に", "と", "が", "は", "bot", "test", "qdash", "レポート", "report"}
        potential_usernames = [u for u in usernames if u.lower() not in excluded_words and len(u) > 2]
        if potential_usernames:
            return potential_usernames[0], "report"

    return None, None, None


@tool
@with_error_handling
async def generate_chip_report(
    username: str = "admin", slack_channel: str = "", slack_thread_ts: str = "", cutoff_hours: int = 24
) -> dict[str, Any]:
    """Generate full chip report (YAML + PDF) using Prefect workflow and send to Slack.

    Args:
        username: Username for the operation (default: "admin")
        slack_channel: Slack channel ID to send results to
        slack_thread_ts: Slack thread timestamp to reply to
        cutoff_hours: Time window in hours for recent data filtering (default: 24)

    Returns:
        Dictionary with flow run information
    """
    try:
        from prefect.client.orchestration import PrefectClient
        from qdash.config import get_settings

        settings = get_settings()

        # Get Slack context from global thread context if not provided
        global _current_thread_context
        if not slack_channel:
            slack_channel = _current_thread_context.get("channel_id", "")
        if not slack_thread_ts:
            slack_thread_ts = _current_thread_context.get("thread_ts", "")
        logger.info(f"Using Slack context - channel: {slack_channel}, thread: {slack_thread_ts}")
        logger.info(f"Global context: {_current_thread_context}")

        logger.info(
            f"Starting chip report generation for user: {username}, channel: {slack_channel}, thread: {slack_thread_ts}"
        )

        # Use the correct internal port for prefect-server
        prefect_url = settings.prefect_api_url

        # Fix the port issue: prefect-server runs on port 4200 internally
        if "prefect-server:2003" in prefect_url:
            prefect_url = prefect_url.replace("prefect-server:2003", "prefect-server:4200")
            logger.info(f"Corrected Prefect URL to: {prefect_url}")

        client = PrefectClient(api="http://prefect-server:4200/api")

        # Get the chip-report deployment
        try:
            # First, try to get all deployments for debugging
            deployment = await client.read_deployment_by_name(f"chip-report/qiqb-dev-chip-report")
            parameters = {
                "username": username,
                "slack_channel": slack_channel,  # Always include, even if empty
                "slack_thread_ts": slack_thread_ts,  # Always include, even if empty
                "cutoff_hours": cutoff_hours,  # Time window for recent data
            }

            logger.info(f"Flow parameters being sent: {parameters}")
            flow_run = await client.create_flow_run_from_deployment(deployment.id, parameters=parameters)
        except Exception as e:
            logger.error(f"Failed to find chip-report deployment: {e}")
            raise ValueError(
                "Deployment 'chip-report/qiqb-dev-chip-report' not found. Please check the deployment name."
            )

        logger.info(f"Started chip report flow run: {flow_run.id}")

        return {
            "status": "started",
            "flow_run_id": str(flow_run.id),
            "deployment_name": deployment.name,
            "username": username,
            "message": f"""チップレポート生成を開始しました (ユーザー: {username})
フローID: {flow_run.id}

レポートが完成するとSlackスレッドにYAMLとPDFファイルが送信されます。""",
        }

    except ImportError:
        logger.error("Prefect client not available")
        return {
            "error": "Prefect client not available in this environment",
            "suggestion": "Please ensure Prefect is installed and configured",
        }
    except Exception as e:
        logger.error(f"Failed to generate chip report: {e}")
        return {"error": f"Failed to generate chip report: {e!s}", "username": username}








@tool
@with_error_handling
async def get_chip_parameters_formatted(
    chip_id: str | None = None,
    username: str = "admin",
    calculate_stats: bool = True,
    within_24hrs: bool = False,
) -> str:
    """Get quantum chip fidelity statistics with Slack-friendly formatting."""
    try:
        logger.info(f"Fetching chip parameters: chip_id={chip_id}, username={username}")
        raw_params = await get_chip_parameters(chip_id, username, calculate_stats, within_24hrs)
        formatted_result = format_chip_parameters_for_slack(raw_params)
        logger.info(f"Successfully formatted chip parameters ({len(formatted_result)} chars)")
        return formatted_result
    except Exception as e:
        logger.error(f"Failed to get formatted chip parameters: {e}")
        raise


@tool
@with_error_handling
async def get_thread_history(channel_id: str, thread_ts: str) -> dict[str, Any]:
    """Get Slack conversation history from a thread."""
    try:
        logger.info(f"Fetching thread history: channel={channel_id}, thread={thread_ts}")
        result = await app.client.conversations_replies(channel=channel_id, ts=thread_ts, limit=50)

        messages = [
            {
                "user": msg.get("user", "unknown"),
                "text": msg.get("text", ""),
                "ts": msg.get("ts", ""),
                "type": msg.get("type", "message"),
            }
            for msg in result.get("messages", [])
        ]

        logger.info(f"Retrieved {len(messages)} messages from thread")
        return {
            "channel_id": channel_id,
            "thread_ts": thread_ts,
            "message_count": len(messages),
            "messages": messages,
        }
    except Exception as e:
        logger.error(f"Slack API error fetching thread history: {e}")
        return {"error": f"Failed to get thread history: {e!s}"}


@app.event("app_mention")
async def handle_mention(event, say, client) -> None:
    """Handle bot mention events using Strands agent with thread-based context management."""
    start_time = datetime.now()

    try:
        # Parse event into Pydantic model
        slack_event = SlackEvent(**event)
        clean_message = slack_event.clean_text

        # Log Slack event
        log_slack_event("app_mention", slack_event.channel, slack_event.user, clean_message)

        # Use a placeholder username for agent creation - actual username will be requested per tool
        qdash_username = "未指定"

        # Get or create thread-specific agent with conversation history
        # For replies, use the actual thread_ts; for new messages, use the message ts as the thread
        thread_ts = slack_event.thread_ts or slack_event.ts

        # Set global thread context for tools to access
        # Always use ts for the thread context (this is where replies should go)
        global _current_thread_context
        _current_thread_context = {
            "channel_id": slack_event.channel,
            "thread_ts": slack_event.ts,  # Always use the message ts for replies
            "user_id": slack_event.user,
        }
        logger.info(
            f"Set thread context: channel={slack_event.channel}, thread={slack_event.ts} (will reply to this message)"
        )

        agent = await get_or_create_thread_agent(
            channel_id=slack_event.channel,
            thread_ts=thread_ts,  # Use the actual thread_ts value
            user_id=slack_event.user,
            username=qdash_username,  # Use dynamically obtained username
        )

        await say(text="🤔 考え中...", thread_ts=thread_ts)

        try:
            # Update agent state with current interaction
            await update_agent_state(agent, "mention")

            # Execute agent with user message - agent maintains conversation history
            user_message = clean_message

            # Use invoke_async for Strands Agent - conversation history is maintained automatically
            result = await agent.invoke_async(user_message)

            # Extract the message content from the result (Strands AgentResult format)
            response_text = str(result) if result else "返答を生成できませんでした"

            # Log conversation context for debugging
            interaction_count = agent.state.get("interaction_count") or 0
            message_count = len(agent.messages) if hasattr(agent, "messages") else 0

            logger.info(f"💬 Thread context: {interaction_count} interactions, {message_count} messages")

            # Send final result
            await say(text=response_text, thread_ts=thread_ts)

            # Record successful interaction
            duration_ms = (datetime.now() - start_time).total_seconds() * 1000
            metrics.record_user_interaction(True, duration_ms)

            logger.info(f"✅ Successfully responded to user in {duration_ms:.1f}ms")

        except Exception as e:
            # Handle agent execution errors
            error_msg = handle_critical_error(e, "agent_execution")
            await say(text=error_msg, thread_ts=thread_ts)

            # Record failed interaction
            duration_ms = (datetime.now() - start_time).total_seconds() * 1000
            metrics.record_user_interaction(False, duration_ms)

    except Exception as e:
        # Handle parsing/setup errors
        logger.error(f"Critical error in handle_mention: {e}")
        thread_ts = event.get("thread_ts", event.get("ts")) if isinstance(event, dict) else None
        error_msg = handle_critical_error(e, "slack_event_handling")
        await say(text=error_msg, thread_ts=thread_ts)

        # Record failed interaction
        duration_ms = (datetime.now() - start_time).total_seconds() * 1000
        metrics.record_user_interaction(False, duration_ms)


@app.event("message")
async def handle_message_events(body, logger) -> None:
    """Message event handler (acknowledgment only)."""
    logger.debug(body)


async def main() -> None:
    """Start the Strands-based Slack bot."""
    try:
        # Start periodic health check
        health_check_task = asyncio.create_task(setup_periodic_health_check())

        # Start periodic agent cache cleanup (every hour)
        async def periodic_cleanup():
            while True:
                await asyncio.sleep(3600)  # 1 hour
                cleanup_agent_cache()

        cleanup_task = asyncio.create_task(periodic_cleanup())

        # Start Socket Mode handler
        handler = AsyncSocketModeHandler(app, settings.slack_app_token)

        # Simple startup logging
        model_config = get_current_model_config()
        logger.info("🚀 QDash Strands Slack Agent starting...")
        logger.info(f"  Strands SDK: {STRANDS_AVAILABLE}")
        logger.info(f"  Model: {model_config.name}")
        logger.info(f"  Log Level: {settings.log_level}")

        await handler.start_async()

    except KeyboardInterrupt:
        logger.info("👋 Shutting down...")
        health_check_task.cancel()
        cleanup_task.cancel()

    except Exception as e:
        logger.critical(f"Startup failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
