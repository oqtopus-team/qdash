"""Tests for the NDJSON to SSE translation used by the Pi chat backend."""

from __future__ import annotations

import json
from typing import Any

import pytest

from qdash.api.services.pi_chat_service import (
    build_blocks_result,
    tool_label,
    translate,
)


async def _lines(*events: dict[str, Any]):
    for event in events:
        yield json.dumps(event)


def _parse(sse: str) -> tuple[str, dict[str, Any]]:
    name, data = sse.strip().split("\n", 1)
    return name.removeprefix("event: "), json.loads(data.removeprefix("data: "))


async def _collect(
    *events: dict[str, Any],
) -> list[tuple[str, dict[str, Any]]]:
    return [_parse(sse) async for sse in translate(_lines(*events))]


class TestToolLabel:
    def test_strips_prefix_and_underscores(self) -> None:
        assert tool_label("qdash_get_timeseries") == "Get timeseries"

    def test_keeps_non_qdash_tools_readable(self) -> None:
        assert tool_label("render_chart") == "Render chart"


class TestTranslate:
    @pytest.mark.asyncio
    async def test_done_yields_result(self) -> None:
        events = await _collect({"type": "done", "text": "Hello"})

        assert [name for name, _ in events] == ["status", "result"]
        assert events[1][1] == {
            "blocks": [{"type": "text", "content": "Hello", "chart": None}],
            "assessment": None,
        }

    @pytest.mark.asyncio
    async def test_tool_events_become_status_updates(self) -> None:
        events = await _collect(
            {"type": "tool_start", "name": "qdash_get_timeseries"},
            {"type": "tool_end", "name": "qdash_get_timeseries", "isError": False},
            {"type": "done", "text": "ok", "messages": []},
        )

        assert events[0][1]["step"] == "tool_call"
        assert events[0][1]["message"] == "Get timeseries..."
        assert events[1][1]["completed_tools"] == ["Get timeseries"]

    @pytest.mark.asyncio
    async def test_charts_precede_the_text_block_in_order(self) -> None:
        first = {"data": [{"y": [1]}], "layout": {}}
        second = {"data": [{"y": [2]}], "layout": {}}
        events = await _collect(
            {"type": "chart", "chart": first},
            {"type": "chart", "chart": second},
            {"type": "done", "text": "see plots", "messages": []},
        )

        blocks = events[-1][1]["blocks"]
        assert [b["type"] for b in blocks] == ["chart", "chart", "text"]
        assert [blocks[0]["chart"], blocks[1]["chart"]] == [first, second]

    @pytest.mark.asyncio
    async def test_empty_turn_becomes_an_error_instead_of_a_blank_reply(self) -> None:
        events = await _collect({"type": "done", "text": ""})

        assert events == [
            ("error", {"step": "run_chat", "detail": "The model returned an empty response"})
        ]

    @pytest.mark.asyncio
    async def test_a_chart_alone_is_a_real_answer(self) -> None:
        chart = {"data": [{"y": [1]}], "layout": {}}
        events = await _collect(
            {"type": "chart", "chart": chart},
            {"type": "done", "text": "", "messages": []},
        )

        assert events[-1][0] == "result"

    @pytest.mark.asyncio
    async def test_error_line_stops_the_stream(self) -> None:
        events = await _collect(
            {"type": "error", "message": "model exploded"},
            {"type": "done", "text": "unreachable", "messages": []},
        )

        assert events == [("error", {"step": "run_chat", "detail": "model exploded"})]

    @pytest.mark.asyncio
    async def test_truncated_stream_reports_an_error(self) -> None:
        events = await _collect({"type": "tool_start", "name": "qdash_query"})

        assert events[-1][0] == "error"

    @pytest.mark.asyncio
    async def test_malformed_runtime_line_becomes_an_error(self) -> None:
        async def malformed():
            yield "not-json"

        events = [_parse(sse) async for sse in translate(malformed())]
        assert events == [
            ("error", {"step": "run_chat", "detail": "Agent runtime sent malformed data"})
        ]


class TestBuildBlocksResult:
    def test_empty_text_produces_no_text_block(self) -> None:
        assert build_blocks_result("", []) == {"blocks": [], "assessment": None}
