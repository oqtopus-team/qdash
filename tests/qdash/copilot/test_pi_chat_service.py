"""Tests for the NDJSON to SSE translation used by the Pi chat backend."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pytest

from qdash.api.services.pi_chat_service import (
    _save_agent_messages,
    build_blocks_result,
    save_agent_messages,
    tool_label,
    translate,
)
from qdash.dbmodel.copilot_chat_session import CopilotChatSessionDocument


async def _lines(*events: dict[str, Any]):
    for event in events:
        yield json.dumps(event)


def _parse(sse: str) -> tuple[str, dict[str, Any]]:
    name, data = sse.strip().split("\n", 1)
    return name.removeprefix("event: "), json.loads(data.removeprefix("data: "))


async def _collect(
    *events: dict[str, Any],
) -> tuple[list[tuple[str, dict[str, Any]]], list[Any]]:
    saved: list[Any] = []
    out = [_parse(sse) async for sse in translate(_lines(*events), on_done=saved.append)]
    return out, saved


class TestToolLabel:
    def test_strips_prefix_and_underscores(self) -> None:
        assert tool_label("qdash_get_timeseries") == "Get timeseries"

    def test_keeps_non_qdash_tools_readable(self) -> None:
        assert tool_label("render_chart") == "Render chart"


class TestTranslate:
    @pytest.mark.asyncio
    async def test_done_yields_result_and_persists_state(self) -> None:
        messages = [{"role": "user", "content": "hi"}]
        events, saved = await _collect(
            {"type": "done", "text": "Hello", "messages": messages},
        )

        assert [name for name, _ in events] == ["status", "result"]
        assert events[1][1] == {
            "blocks": [{"type": "text", "content": "Hello", "chart": None}],
            "assessment": None,
        }
        assert saved == [messages]

    @pytest.mark.asyncio
    async def test_tool_events_become_status_updates(self) -> None:
        events, _ = await _collect(
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
        events, _ = await _collect(
            {"type": "chart", "chart": first},
            {"type": "chart", "chart": second},
            {"type": "done", "text": "see plots", "messages": []},
        )

        blocks = events[-1][1]["blocks"]
        assert [b["type"] for b in blocks] == ["chart", "chart", "text"]
        assert [blocks[0]["chart"], blocks[1]["chart"]] == [first, second]

    @pytest.mark.asyncio
    async def test_empty_turn_becomes_an_error_instead_of_a_blank_reply(self) -> None:
        events, saved = await _collect({"type": "done", "text": "", "messages": []})

        assert events == [
            ("error", {"step": "run_chat", "detail": "The model returned an empty response"})
        ]
        # The turn still happened, so the conversation state is still written.
        assert saved == [[]]

    @pytest.mark.asyncio
    async def test_a_chart_alone_is_a_real_answer(self) -> None:
        chart = {"data": [{"y": [1]}], "layout": {}}
        events, _ = await _collect(
            {"type": "chart", "chart": chart},
            {"type": "done", "text": "", "messages": []},
        )

        assert events[-1][0] == "result"

    @pytest.mark.asyncio
    async def test_error_line_stops_the_stream(self) -> None:
        events, saved = await _collect(
            {"type": "error", "message": "model exploded"},
            {"type": "done", "text": "unreachable", "messages": []},
        )

        assert events == [("error", {"step": "run_chat", "detail": "model exploded"})]
        assert saved == []

    @pytest.mark.asyncio
    async def test_truncated_stream_reports_an_error(self) -> None:
        events, saved = await _collect({"type": "tool_start", "name": "qdash_query"})

        assert events[-1][0] == "error"
        assert saved == []

    @pytest.mark.asyncio
    async def test_async_writeback_is_awaited(self) -> None:
        saved: list[list[dict[str, Any]]] = []

        async def on_done(messages: list[dict[str, Any]]) -> None:
            saved.append(messages)

        events = [
            _parse(sse)
            async for sse in translate(
                _lines({"type": "done", "text": "ok", "messages": [{"role": "user"}]}),
                on_done=on_done,
            )
        ]

        assert events[-1][0] == "result"
        assert saved == [[{"role": "user"}]]

    @pytest.mark.asyncio
    async def test_writeback_failure_becomes_an_error_event(self) -> None:
        async def on_done(_messages: list[dict[str, Any]]) -> None:
            raise RuntimeError("database unavailable")

        events = [
            _parse(sse)
            async for sse in translate(
                _lines({"type": "done", "text": "ok", "messages": []}),
                on_done=on_done,
            )
        ]

        assert events == [
            (
                "error",
                {"step": "run_chat", "detail": "Could not persist the conversation state"},
            )
        ]


class TestAgentMessagePersistence:
    def test_atomic_update_only_writes_agent_messages(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        collection = MagicMock()
        collection.update_one.return_value.matched_count = 1
        monkeypatch.setattr(
            CopilotChatSessionDocument,
            "get_motor_collection",
            lambda: collection,
        )
        messages = [{"role": "assistant", "content": "done"}]

        assert _save_agent_messages("alice", "session-1", messages)

        collection.update_one.assert_called_once_with(
            {"username": "alice", "session_id": "session-1"},
            {"$set": {"agent_messages": messages}},
        )

    @pytest.mark.asyncio
    async def test_missing_session_is_not_silently_ignored(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def run_in_thread(_function, *_args):
            return False

        monkeypatch.setattr("qdash.api.services.pi_chat_service.asyncio.to_thread", run_in_thread)

        with pytest.raises(RuntimeError, match="vanished before writeback"):
            await save_agent_messages("alice", "missing", [])


class TestBuildBlocksResult:
    def test_empty_text_produces_no_text_block(self) -> None:
        assert build_blocks_result("", []) == {"blocks": [], "assessment": None}
