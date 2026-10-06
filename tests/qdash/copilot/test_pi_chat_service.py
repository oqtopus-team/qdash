"""Tests for the NDJSON to SSE translation used by the Pi chat backend."""

from __future__ import annotations

import json
from typing import Any

import pytest

from qdash.api.services.pi_chat_service import (
    approval_payload,
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


def test_approval_decisions_are_forwarded_to_the_runtime() -> None:
    from qdash.copilot.contracts.models import ApprovalDecision

    assert approval_payload(None) == {}
    assert approval_payload(ApprovalDecision(id="c1", approve=True)) == {
        "approval": {"id": "c1", "approve": True}
    }


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
    async def test_pings_become_sse_comments(self) -> None:
        raw = [
            sse async for sse in translate(_lines({"type": "ping"}, {"type": "done", "text": "ok"}))
        ]
        assert raw[0] == ":\n\n"
        assert "result" in [_parse(sse)[0] for sse in raw[1:]]

    @pytest.mark.asyncio
    async def test_tool_end_carries_fetched_figures(self) -> None:
        events = await _collect(
            {"type": "tool_start", "name": "qdash_get_task_figures", "id": "c7"},
            {
                "type": "tool_end",
                "name": "qdash_get_task_figures",
                "id": "c7",
                "isError": False,
                "figures": ["exec/1/CheckRabi_0.png"],
            },
            {"type": "tool_end", "name": "qdash_get_timeseries", "isError": False},
            {"type": "done", "text": "ok"},
        )
        ends = [data for name, data in events if name == "tool_end"]
        assert ends[0]["figures"] == ["exec/1/CheckRabi_0.png"]
        assert "figures" not in ends[1]

    @pytest.mark.asyncio
    async def test_tool_events_become_status_updates(self) -> None:
        events = await _collect(
            {"type": "tool_start", "name": "qdash_get_timeseries"},
            {"type": "tool_end", "name": "qdash_get_timeseries", "isError": False},
            {"type": "done", "text": "ok", "messages": []},
        )

        statuses = [data for name, data in events if name == "status"]
        assert statuses[0]["step"] == "tool_call"
        assert statuses[0]["message"] == "Get timeseries..."
        assert statuses[1]["completed_tools"] == ["Get timeseries"]

    @pytest.mark.asyncio
    async def test_tool_events_carry_call_details(self) -> None:
        events = await _collect(
            {"type": "tool_start", "name": "qdash_query", "id": "c1", "args": {"qid": "0"}},
            {"type": "tool_end", "name": "qdash_query", "id": "c1", "isError": True},
            {"type": "done", "text": "ok"},
        )

        named = dict(events[:1] + [e for e in events if e[0] == "tool_end"])
        assert named["tool_start"] == {
            "id": "c1",
            "tool": "qdash_query",
            "label": "Query",
            "args": {"qid": "0"},
        }
        assert named["tool_end"] == {
            "id": "c1",
            "tool": "qdash_query",
            "label": "Query",
            "is_error": True,
        }

    @pytest.mark.asyncio
    async def test_text_and_thinking_deltas_stream_before_the_result(self) -> None:
        events = await _collect(
            {"type": "thinking_delta", "delta": "Checking T1"},
            {"type": "text_delta", "delta": "T1 is "},
            {"type": "text_delta", "delta": "45 us"},
            {"type": "done", "text": "T1 is 45 us"},
        )

        assert [name for name, _ in events] == ["thinking", "delta", "delta", "status", "result"]
        assert events[0][1] == {"text": "Checking T1"}
        assert "".join(data["text"] for name, data in events if name == "delta") == "T1 is 45 us"

    @pytest.mark.asyncio
    async def test_a_turn_ending_on_a_question_renders_it_as_a_card(self) -> None:
        ask = {"question": "Which qubit?", "options": [{"label": "Q32"}, {"label": "Q33"}]}
        approval = {"id": "c1", "tool": "qdash_execute_agent_action", "label": "Run", "args": {}}
        events = await _collect(
            {"type": "ask", "ask": ask},
            {"type": "approval", "approval": approval},
            # Both end the turn, often without any text.
            {"type": "done", "text": ""},
        )

        assert [name for name, _ in events] == ["status", "result"]
        assert events[1][1]["blocks"] == [
            {"type": "ask", "content": None, "chart": None, "ask": ask},
            {"type": "approval", "content": None, "chart": None, "approval": approval},
        ]

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
