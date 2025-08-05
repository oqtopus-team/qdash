import ast
import datetime
from typing import Any

from pydantic import BaseModel
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.initialize import initialize
from qdash.slack_agent.agent import Tool, ToolParameter

initialize()  # Ensure database is initialized


# Response models
class SearchResult(BaseModel):
    """Search result."""

    title: str
    snippet: str


class SearchResponse(BaseModel):
    """Search response."""

    query: str
    results: list[SearchResult]


# Tool functions
async def get_current_time() -> str:
    """Get current time."""
    # Use JST (Japan Standard Time) timezone-aware datetime
    jst = datetime.timezone(datetime.timedelta(hours=9))
    return datetime.datetime.now(tz=jst).strftime("%Y-%m-%d %H:%M:%S JST")


async def web_search(query: str) -> dict[str, Any]:
    """Execute web search (demo mode)."""
    import logging

    logger = logging.getLogger(__name__)
    logger.info(f"🔍 Using Demo Mode for query: '{query}'")

    response = SearchResponse(
        query=query,
        results=[
            SearchResult(
                title="[DEMO] Mock search result",
                snippet="This is demo data. Real web search is not configured in this implementation.",
            ),
            SearchResult(
                title="[DEMO] Search placeholder",
                snippet="This bot currently uses demo search results. For real search functionality, consider integrating a web search API.",
            ),
        ],
    )
    return response.model_dump()


async def calculate(expression: str) -> float:
    """Calculate mathematical expression."""
    try:
        # Use ast.literal_eval for safe evaluation of literals
        result = ast.literal_eval(expression)
        return float(result)
    except Exception as e:
        raise ValueError(f"Calculation error: {e!s}")


def get_string_length(text: str) -> int:
    """Get string length."""
    return len(text)


def get_current_chip() -> str:
    """Get current chip."""
    chip = ChipDocument.get_current_chip("admin")
    if chip:
        return str(chip.chip_id)
    return "No current chip found"


# Tool definitions
current_time_tool = Tool(
    name="get_current_time",
    description="Get current date and time",
    parameters=ToolParameter(properties={}, required=[]),
    function=get_current_time,
)

web_search_tool = Tool(
    name="web_search",
    description="Execute web search",
    parameters=ToolParameter(
        properties={"query": {"type": "string", "description": "Search query"}}, required=["query"]
    ),
    function=web_search,
)

calculate_tool = Tool(
    name="calculate",
    description="Calculate mathematical expression",
    parameters=ToolParameter(
        properties={
            "expression": {
                "type": "string",
                "description": "Expression to calculate (e.g. 2+2, 10*5, max(1,2,3))",
            }
        },
        required=["expression"],
    ),
    function=calculate,
)

string_length_tool = Tool(
    name="get_string_length",
    description="Get string length",
    parameters=ToolParameter(
        properties={"text": {"type": "string", "description": "Text to measure"}}, required=["text"]
    ),
    function=get_string_length,
)

curent_chip_id_tool = Tool(
    name="get_current_chip",
    description="Get current chip ID",
    parameters=ToolParameter(properties={}, required=[]),
    function=get_current_chip,
)


# Default tool set
DEFAULT_TOOLS = [
    current_time_tool,
    web_search_tool,
    calculate_tool,
    string_length_tool,
    curent_chip_id_tool,
]
