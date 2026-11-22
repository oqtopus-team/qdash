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
    ui_block,
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
        assert tool_label("codemode") == "Code mode script"
        assert tool_label("tool_search") == "Search tools"


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
    async def test_tool_end_carries_what_the_evaluation_model_saw(self) -> None:
        evaluation = {
            "prompt": "Reference for this experiment:\n## Experiment: CheckRabi",
            "model": "vllm/ising",
        }
        events = await _collect(
            {"type": "tool_start", "name": "qcal_evaluate", "id": "c8"},
            {
                "type": "tool_end",
                "name": "qcal_evaluate",
                "id": "c8",
                "isError": False,
                "evaluation": evaluation,
            },
            {"type": "tool_end", "name": "qcal_evaluate", "isError": False, "evaluation": "bogus"},
            {"type": "done", "text": "ok"},
        )
        ends = [data for name, data in events if name == "tool_end"]
        assert ends[0]["evaluation"] == evaluation
        assert "evaluation" not in ends[1]

    @pytest.mark.asyncio
    async def test_tool_end_carries_a_classify_decision(self) -> None:
        decided = {
            "classifier": "system-one-classifier/Open-Jev",
            "outcome": "classified",
            "category": "readout_problem",
            "probability": 0.8,
            "margin": 0.65,
            "probabilities": [
                {"category": "readout_problem", "probability": 0.8},
                {"category": "drive_problem", "probability": 0.2},
            ],
        }
        many = [{"category": f"c{i}", "probability": 0.05} for i in range(20)]
        events = await _collect(
            {"type": "tool_start", "name": "classify", "id": "k1"},
            {
                "type": "tool_end",
                "name": "classify",
                "id": "k1",
                "isError": False,
                "classification": {**decided, "state": {"context": "secret"}},
            },
            {
                "type": "tool_end",
                "name": "classify",
                "isError": True,
                "classification": {
                    "classifier": "c/m",
                    "outcome": "failed",
                    "reason": "x" * 1000,
                    "probability": True,
                    "probabilities": [*many, "bogus", {"category": "a", "probability": 2}],
                },
            },
            {
                "type": "tool_end",
                "name": "classify",
                "isError": False,
                "classification": {"classifier": "c/m", "outcome": "template"},
            },
            {"type": "done", "text": "ok"},
        )
        ends = [data for name, data in events if name == "tool_end"]
        # Only the known fields pass: never what the classifier was sent.
        assert ends[0]["classification"] == decided
        assert ends[1]["classification"] == {
            "classifier": "c/m",
            "outcome": "failed",
            "reason": "x" * 200,
            "probabilities": many[:8],
        }
        assert ends[1]["is_error"] is True
        assert "classification" not in ends[2]

    @pytest.mark.asyncio
    async def test_tool_end_carries_a_workspace_tools_answer(self) -> None:
        events = await _collect(
            {"type": "tool_start", "name": "bash", "id": "c9"},
            {
                "type": "tool_end",
                "name": "bash",
                "id": "c9",
                "isError": True,
                "output": "ls: no such file",
                "exitCode": 2,
            },
            {"type": "tool_end", "name": "write", "isError": False, "output": ""},
            {"type": "tool_end", "name": "read", "isError": False, "exitCode": True},
            {"type": "done", "text": "ok"},
        )
        ends = [data for name, data in events if name == "tool_end"]
        assert ends[0]["output"] == "ls: no such file"
        assert ends[0]["exit_code"] == 2
        assert "output" not in ends[1]
        assert "exit_code" not in ends[2]

    @pytest.mark.asyncio
    async def test_a_tool_call_being_written_streams_as_draft_and_deltas(self) -> None:
        events = await _collect(
            {"type": "tool_draft", "name": "write", "index": 1, "id": "call_1"},
            {"type": "tool_args_delta", "index": 1, "path": ["content"], "delta": "import numpy"},
            {"type": "tool_start", "name": "write", "id": "call_1", "args": {"path": "fit.py"}},
            {"type": "done", "text": "ok"},
        )
        named = [(name, data) for name, data in events if name.startswith("tool_")]
        assert named[0] == (
            "tool_draft",
            {"index": 1, "id": "call_1", "tool": "write", "label": "Write"},
        )
        assert named[1] == (
            "tool_args_delta",
            {"index": 1, "path": ["content"], "delta": "import numpy"},
        )
        assert named[2][0] == "tool_start"

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
    async def test_a_proposed_edit_becomes_an_edit_block(self) -> None:
        edit = {"summary": "Add T2", "code": "new code", "flowName": "t1"}
        events = await _collect(
            {"type": "edit", "edit": edit},
            {"type": "tool_end", "name": "propose_code_edit", "isError": False},
            {"type": "done", "text": "Here is the change."},
        )
        result = dict(events)["result"]
        assert result["blocks"][-1] == {
            "type": "edit",
            "content": None,
            "chart": None,
            "edit": edit,
        }

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


_UI = {
    "version": 1,
    "spec": {
        "root": "m",
        "elements": {
            "m": {"type": "Metric", "props": {"label": "T1", "value": 42}, "children": []}
        },
    },
    "fallback": "- T1: 42",
}


class TestUiBlocks:
    @pytest.mark.asyncio
    async def test_a_ui_streams_live_and_keeps_its_place_among_charts(self) -> None:
        chart = {"data": [{"y": [1]}], "layout": {}}
        events = await _collect(
            {"type": "chart", "chart": chart},
            {"type": "ui", "ui": _UI},
            {"type": "tool_end", "name": "render_ui", "isError": False},
            {"type": "done", "text": "T1 is fine."},
        )

        ui_block = {"type": "ui", "content": "- T1: 42", "chart": None, "ui": _UI}
        assert ("ui", ui_block) in events
        blocks = events[-1][1]["blocks"]
        assert [b["type"] for b in blocks] == ["chart", "ui", "text"]
        assert blocks[1] == ui_block

    @pytest.mark.asyncio
    async def test_a_ui_alone_is_a_real_answer(self) -> None:
        events = await _collect({"type": "ui", "ui": _UI}, {"type": "done", "text": ""})

        assert events[-1][0] == "result"

    @pytest.mark.asyncio
    async def test_a_malformed_ui_keeps_only_its_fallback_text(self) -> None:
        events = await _collect(
            {"type": "ui", "ui": {"version": "1", "spec": [], "fallback": "- T1: 42"}},
            {"type": "ui", "ui": {"version": 1, "spec": "nope"}},
            {"type": "ui", "ui": "not a block"},
            {"type": "done", "text": "Done."},
        )

        assert events[-1][1]["blocks"] == [
            {"type": "text", "content": "- T1: 42", "chart": None},
            {"type": "text", "content": "Done.", "chart": None},
        ]

    @pytest.mark.asyncio
    async def test_an_oversized_ui_is_not_stored(self) -> None:
        huge = {**_UI, "spec": {"root": "m", "elements": {"m": {"text": "x" * 300_000}}}}
        events = await _collect({"type": "ui", "ui": huge}, {"type": "done", "text": "Done."})

        assert [b["type"] for b in events[-1][1]["blocks"]] == ["text", "text"]

    @pytest.mark.asyncio
    async def test_a_ui_event_without_its_payload_is_malformed(self) -> None:
        events = await _collect({"type": "ui"})

        assert events == [
            ("error", {"step": "run_chat", "detail": "Agent runtime sent malformed data"})
        ]

    def test_forum_markdown_uses_the_ui_fallback(self) -> None:
        from qdash.copilot.blocks import blocks_to_markdown

        block = ui_block(_UI)
        assert block is not None
        result = build_blocks_result("Summary.", [block])
        assert blocks_to_markdown(result) == "- T1: 42\n\nSummary."


class TestBuildBlocksResult:
    def test_empty_text_produces_no_text_block(self) -> None:
        assert build_blocks_result("", []) == {"blocks": [], "assessment": None}


def test_user_attachments_are_forwarded_as_turn_images(monkeypatch: pytest.MonkeyPatch) -> None:
    from qdash.api.services import pi_chat_service
    from qdash.copilot.config import CopilotConfig, ModelConfig
    from qdash.copilot.contracts.models import ChatRequest

    monkeypatch.setattr(pi_chat_service, "user_instructions", lambda _username: None)
    config = CopilotConfig(model=ModelConfig(provider="vllm", name="m"))
    request = ChatRequest.model_validate(
        {
            "message": "Evaluate this",
            "session_id": "s1",
            "images": [{"data": "iVBORw0KGgo=", "mimeType": "image/png"}],
        }
    )
    payload = pi_chat_service._request_payload(request, config, "alice")

    assert payload["images"] == [{"data": "iVBORw0KGgo=", "mimeType": "image/png"}]
    # A turn without attachments carries no images key, so the runtime attaches nothing.
    bare = ChatRequest.model_validate({"message": "hi", "session_id": "s1"})
    assert "images" not in pi_chat_service._request_payload(bare, config, "alice")


def test_attachments_are_limited_to_supported_image_types() -> None:
    import pytest as _pytest
    from pydantic import ValidationError

    from qdash.copilot.contracts.models import ChatRequest

    with _pytest.raises(ValidationError):
        ChatRequest.model_validate(
            {
                "message": "x",
                "session_id": "s1",
                "images": [{"data": "YQ==", "mimeType": "image/gif"}],
            }
        )
    with _pytest.raises(ValidationError):
        ChatRequest.model_validate(
            {
                "message": "x",
                "session_id": "s1",
                "images": [{"data": "iVBORw0KGgo=", "mimeType": "image/png"}] * 5,
            }
        )


class _Recorder:
    def __init__(self, ids: dict[str, str] | None) -> None:
        self.ids = ids
        self.records: list[dict[str, Any]] = []
        self.calls: list[str | None] = []
        self.answers: list[str] = []

    def record(self, record: dict[str, Any], call: str | None = None) -> dict[str, str] | None:
        self.records.append(record)
        self.calls.append(call)
        return self.ids

    def finish(self, answer: str) -> None:
        self.answers.append(answer)


@pytest.mark.asyncio
async def test_chat_evaluations_are_recorded_and_the_chat_sees_where() -> None:
    recorder = _Recorder({"run_id": "evr_1", "evaluation_id": "ev_1"})
    record = {"task_id": "task-7", "evaluation": {"diagnosis": {"success": True}}}
    events = [
        _parse(sse)
        async for sse in translate(
            _lines(
                {
                    "type": "tool_end",
                    "name": "qcal_evaluate",
                    "id": "c8",
                    "entry_id": "12",
                    "isError": False,
                    "evaluation": {"prompt": "p", "model": "vllm/ising", "record": record},
                },
                {"type": "done", "text": "Looks good"},
            ),
            recorder=recorder,
        )
    ]

    assert recorder.records == [record]
    assert recorder.calls == ["entry:12"]
    assert recorder.answers == ["Looks good"]
    end = next(data for name, data in events if name == "tool_end")
    assert end["evaluation"] == {
        "prompt": "p",
        "model": "vllm/ising",
        "run_id": "evr_1",
        "evaluation_id": "ev_1",
    }


@pytest.mark.asyncio
async def test_each_evaluation_call_is_named_by_its_result_entry() -> None:
    """Every stream of a turn reports a result's durable entry the same way, whatever ID
    the model gave the call (a local model may reuse or omit it); a result committed
    before the turn's own message is an earlier turn's and is not recorded at all."""
    recorder = _Recorder(None)

    def end(call_id: str | None, entry_id: str | None, **extra: Any) -> dict[str, Any]:
        return {
            "type": "tool_end",
            "name": "qcal_evaluate",
            **({"id": call_id} if call_id is not None else {}),
            **({"entry_id": entry_id} if entry_id is not None else {}),
            "isError": False,
            "evaluation": {"prompt": "p", "record": {"task_id": "t"}},
            **extra,
        }

    async for _ in translate(
        _lines(
            end("c1", "3", before_turn=True),
            {"type": "turn_start", "answer": ""},
            end("c1", "7"),
            end("c1", "9"),
            end(None, "11"),
            end("c2", None),
            {"type": "done", "text": "ok"},
        ),
        recorder=recorder,
    ):
        pass
    assert recorder.calls == ["entry:7", "entry:9", "entry:11", None]


@pytest.mark.asyncio
async def test_an_unrecorded_evaluation_keeps_only_its_summary() -> None:
    recorder = _Recorder(None)
    events = [
        _parse(sse)
        async for sse in translate(
            _lines(
                {
                    "type": "tool_end",
                    "name": "qcal_evaluate",
                    "isError": False,
                    "evaluation": {"prompt": "p", "record": {"task_id": ""}},
                },
                {"type": "done", "text": "ok"},
            ),
            recorder=recorder,
        )
    ]
    end = next(data for name, data in events if name == "tool_end")
    assert end["evaluation"] == {"prompt": "p"}
    assert len(recorder.records) == 1

    # Without a recorder the record is still not forwarded to the chat.
    events = await _collect(
        {
            "type": "tool_end",
            "name": "qcal_evaluate",
            "isError": False,
            "evaluation": {"prompt": "p", "record": {"task_id": "t"}},
        },
        {"type": "done", "text": "ok"},
    )
    end = next(data for name, data in events if name == "tool_end")
    assert end["evaluation"] == {"prompt": "p"}


def _sse(name: str, data: dict[str, Any]) -> str:
    return f"event: {name}\ndata: {json.dumps(data)}\n\n"


def test_parse_sse_reads_this_modules_events() -> None:
    from qdash.api.services.pi_chat_service import parse_sse

    assert parse_sse(_sse("result", {"blocks": []})) == ("result", {"blocks": []})
    assert parse_sse(":\n\n") is None
    assert parse_sse("event: x\ndata: not json\n\n") is None


class TestThreadReply:
    @pytest.mark.asyncio
    async def test_one_turn_opens_with_the_thread_and_ends_with_the_result(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from qdash.api.services import pi_chat_service
        from qdash.copilot.config import CopilotConfig, ModelConfig

        captured: dict[str, Any] = {}
        deleted: list[tuple[str, str]] = []

        async def fake_stream_payload(payload, *, step, auth, extra_result=None, recorder=None):
            captured["payload"] = payload
            captured["auth"] = auth
            yield _sse("status", {"step": "tool_call", "tool": "qdash_get_task_result"})
            yield _sse("status", {"step": "complete", "message": "Done"})
            yield _sse("result", {"blocks": [{"type": "text", "content": "Reply", "chart": None}]})

        async def fake_delete(username: str, session_id: str) -> None:
            deleted.append((username, session_id))

        monkeypatch.setattr(pi_chat_service, "stream_payload", fake_stream_payload)
        monkeypatch.setattr(pi_chat_service, "delete_runtime_session_state", fake_delete)
        config = CopilotConfig(
            enabled=True, chat_models=[ModelConfig(provider="openai-compatible", name="qwen")]
        )

        events = [
            event
            async for event in pi_chat_service.thread_reply(
                username="alice",
                auth=pi_chat_service.QDashAuth("alice-token", "p1"),
                config=config,
                scope="issue",
                instruction="Reply in the thread.",
                history=[
                    {"role": "user", "content": "T1 dropped"},
                    {"role": "assistant", "content": "Check the fit"},
                ],
                user_message="Why?",
            )
        ]

        payload = captured["payload"]
        assert payload["owner_id"] == "alice"
        assert payload["conversation_id"].startswith("issue-")
        assert payload["message"] == "Why?"
        assert payload["model"] == {"provider": "openai-compatible", "name": "qwen"}
        assert "[User] T1 dropped" in payload["initial_message"]
        assert "[AI] Check the fit" in payload["initial_message"]
        assert payload["initial_message"].endswith("## Latest post to answer\n\nWhy?")
        assert captured["auth"] == pi_chat_service.QDashAuth("alice-token", "p1")
        # Progress is forwarded, the completion status is not, the result comes last as a dict.
        assert [e for e in events if isinstance(e, str)] == [
            _sse("status", {"step": "tool_call", "tool": "qdash_get_task_result"})
        ]
        assert events[-1] == {"blocks": [{"type": "text", "content": "Reply", "chart": None}]}
        assert deleted == [("alice", payload["conversation_id"])]

    @pytest.mark.asyncio
    async def test_a_failed_turn_forwards_the_error_and_yields_no_result(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from qdash.api.services import pi_chat_service
        from qdash.copilot.config import CopilotConfig

        async def fake_stream_payload(payload, *, step, auth, extra_result=None, recorder=None):
            yield _sse("error", {"step": step, "detail": "runtime down"})

        async def fake_delete(username: str, session_id: str) -> None:
            return None

        monkeypatch.setattr(pi_chat_service, "stream_payload", fake_stream_payload)
        monkeypatch.setattr(pi_chat_service, "delete_runtime_session_state", fake_delete)

        events = [
            event
            async for event in pi_chat_service.thread_reply(
                username="alice",
                auth=pi_chat_service.QDashAuth("t", "p"),
                config=CopilotConfig(enabled=True),
                scope="forum",
                instruction="x",
                history=[],
                user_message="hi",
            )
        ]
        assert events == [_sse("error", {"step": "run_chat", "detail": "runtime down"})]


class TestCompleteOnce:
    @pytest.mark.asyncio
    async def test_returns_the_answer_text(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from qdash.api.services import pi_chat_service
        from qdash.copilot.config import CopilotConfig

        async def fake_stream_payload(payload, *, step, auth, extra_result=None, recorder=None):
            assert payload["message"] == "Extract"
            yield _sse(
                "result",
                {"blocks": [{"type": "text", "content": '{"title": "x"}', "chart": None}]},
            )

        async def fake_delete(username: str, session_id: str) -> None:
            return None

        monkeypatch.setattr(pi_chat_service, "stream_payload", fake_stream_payload)
        monkeypatch.setattr(pi_chat_service, "delete_runtime_session_state", fake_delete)

        text = await pi_chat_service.complete_once(
            username="alice",
            auth=pi_chat_service.QDashAuth("t", "p"),
            config=CopilotConfig(enabled=True),
            scope="knowledge",
            prompt="Extract",
        )
        assert text == '{"title": "x"}'

    @pytest.mark.asyncio
    async def test_raises_with_the_runtime_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from qdash.api.services import pi_chat_service
        from qdash.copilot.config import CopilotConfig

        async def fake_stream_payload(payload, *, step, auth, extra_result=None, recorder=None):
            yield _sse("error", {"step": step, "detail": "model error"})

        async def fake_delete(username: str, session_id: str) -> None:
            return None

        monkeypatch.setattr(pi_chat_service, "stream_payload", fake_stream_payload)
        monkeypatch.setattr(pi_chat_service, "delete_runtime_session_state", fake_delete)

        with pytest.raises(RuntimeError, match="model error"):
            await pi_chat_service.complete_once(
                username="alice",
                auth=pi_chat_service.QDashAuth("t", "p"),
                config=CopilotConfig(enabled=True),
                scope="knowledge",
                prompt="Extract",
            )


def test_a_turns_thinking_level_overrides_the_models_configured_effort(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import pytest as _pytest
    from pydantic import ValidationError

    from qdash.api.services import pi_chat_service
    from qdash.copilot.config import CopilotConfig, ModelConfig
    from qdash.copilot.contracts.models import ChatRequest

    monkeypatch.setattr(pi_chat_service, "user_instructions", lambda _username: None)
    config = CopilotConfig(model=ModelConfig(provider="vllm", name="m", reasoning_effort="high"))
    chosen = ChatRequest.model_validate(
        {"message": "hi", "session_id": "s1", "thinking_level": "off"}
    )
    auto = ChatRequest.model_validate({"message": "hi", "session_id": "s1"})

    assert pi_chat_service._request_payload(chosen, config, "alice")["thinking_level"] == "off"
    # Unset ("Auto" in the UI) keeps the model's configured reasoning effort.
    assert pi_chat_service._request_payload(auto, config, "alice")["thinking_level"] == "high"
    with _pytest.raises(ValidationError):
        ChatRequest.model_validate({"message": "hi", "session_id": "s1", "thinking_level": "max"})


def test_the_open_page_travels_with_the_turn(monkeypatch: pytest.MonkeyPatch) -> None:
    from qdash.api.services import pi_chat_service
    from qdash.copilot.config import CopilotConfig, ModelConfig
    from qdash.copilot.contracts.models import ChatRequest

    # The user's stored preferences come from Mongo, which this test does not run.
    monkeypatch.setattr(pi_chat_service, "user_instructions", lambda _username: None)
    config = CopilotConfig(model=ModelConfig(provider="vllm", name="m"))
    plain = ChatRequest.model_validate({"message": "hi", "session_id": "s1"})
    assert "page_context" not in pi_chat_service._request_payload(plain, config, "alice")
    on_editor = ChatRequest.model_validate(
        {
            "message": "add T2",
            "session_id": "s1",
            "page": {
                "path": "/workflow/t1",
                "title": "Workflow t1",
                "flow": {"name": "t1", "chip_id": "64Qv3", "code": "x = 1\n", "dirty": True},
            },
        }
    )
    assert pi_chat_service._request_payload(on_editor, config, "alice")["page_context"] == {
        "path": "/workflow/t1",
        "title": "Workflow t1",
        "flow": {"name": "t1", "chip_id": "64Qv3", "code": "x = 1\n", "dirty": True},
        "metric_script": None,
        "dashboard": None,
    }
    on_script = ChatRequest.model_validate(
        {
            "message": "use the median",
            "session_id": "s1",
            "page": {
                "path": "/dashboards/scripts/ms_0123456789ab",
                "metric_script": {
                    "script_id": "ms_0123456789ab",
                    "name": "ZX90",
                    "code": "x = 1\n",
                    "dirty": True,
                },
            },
        }
    )
    assert pi_chat_service._request_payload(on_script, config, "alice")["page_context"][
        "metric_script"
    ] == {"script_id": "ms_0123456789ab", "name": "ZX90", "code": "x = 1\n", "dirty": True}
    on_dashboard = ChatRequest.model_validate(
        {
            "message": "add a ZX90 map",
            "session_id": "s1",
            "page": {
                "path": "/dashboards/new",
                "dashboard": {"name": "", "code": '{"panels": []}', "visibility": "private"},
            },
        }
    )
    assert pi_chat_service._request_payload(on_dashboard, config, "alice")["page_context"][
        "dashboard"
    ] == {
        "dashboard_id": None,
        "name": "",
        "description": None,
        "visibility": "private",
        "chip_id": None,
        "version": None,
        "code": '{"panels": []}',
        "dirty": False,
    }
    with pytest.raises(ValueError):
        ChatRequest.model_validate(
            {
                "message": "share it",
                "session_id": "s1",
                "page": {"path": "/x", "dashboard": {"code": "{}", "visibility": "public"}},
            }
        )


@pytest.mark.parametrize("contents", ["runtime-secret\n", ""])
def test_runtime_headers_from_file(monkeypatch, tmp_path, contents):
    from qdash.api.services.pi_chat_service import _runtime_headers

    token_file = tmp_path / "token"
    token_file.write_text(contents)
    monkeypatch.delenv("AGENT_RUNTIME_TOKEN", raising=False)
    monkeypatch.setenv("AGENT_RUNTIME_TOKEN_FILE", str(token_file))
    if contents:
        assert _runtime_headers() == {"Authorization": "Bearer runtime-secret"}
    else:
        with pytest.raises(RuntimeError, match="credential is unavailable"):
            _runtime_headers()


def test_runtime_headers_explicit_token_takes_precedence(monkeypatch):
    from qdash.api.services.pi_chat_service import _runtime_headers

    monkeypatch.setenv("AGENT_RUNTIME_TOKEN", "explicit-secret")
    monkeypatch.setenv("AGENT_RUNTIME_TOKEN_FILE", "/missing/credential")
    assert _runtime_headers() == {"Authorization": "Bearer explicit-secret"}


def test_runtime_headers_missing_credentials_fail_closed(monkeypatch, tmp_path):
    from qdash.api.services.pi_chat_service import _runtime_headers

    monkeypatch.delenv("AGENT_RUNTIME_TOKEN", raising=False)
    monkeypatch.delenv("AGENT_RUNTIME_TOKEN_FILE", raising=False)
    with pytest.raises(RuntimeError, match="credential is unavailable"):
        _runtime_headers()
    monkeypatch.setenv("AGENT_RUNTIME_TOKEN_FILE", str(tmp_path / "missing"))
    with pytest.raises(FileNotFoundError):
        _runtime_headers()


class TestSteerAndContinue:
    @pytest.mark.asyncio
    async def test_an_applied_steer_closes_the_answer_so_far_and_resets_its_blocks(self) -> None:
        chart = {"data": [{"x": [1]}], "layout": {}}
        events = await _collect(
            {"type": "chart", "chart": chart},
            {
                "type": "steer",
                "request_id": "s1",
                "status": "applied",
                "entry_id": "7",
                "text": "And T2?",
                "answer": "T1 is 42 us.",
            },
            {"type": "text_delta", "delta": "T2 is 30 us."},
            {"type": "done", "text": "T2 is 30 us.", "entry_id": "9"},
        )

        assert [name for name, _ in events] == ["steer", "delta", "status", "result"]
        assert events[0][1] == {
            "request_id": "s1",
            "status": "applied",
            "entry_id": "7",
            "text": "And T2?",
            "result": {
                "blocks": [
                    {"type": "chart", "content": None, "chart": chart},
                    {"type": "text", "content": "T1 is 42 us.", "chart": None},
                ],
                "assessment": None,
            },
        }
        # The chart belongs to the answer before the steer, not to the final one.
        assert events[-1][1] == {
            "blocks": [{"type": "text", "content": "T2 is 30 us.", "chart": None}],
            "assessment": None,
            "entry_id": "9",
        }

    @pytest.mark.asyncio
    async def test_a_steer_placed_before_the_turn_is_marked(self) -> None:
        events = await _collect(
            {
                "type": "steer",
                "request_id": "s0",
                "status": "applied",
                "entry_id": "4",
                "text": "Use Q5",
                "answer": "",
                "before_turn": True,
            },
            {"type": "done", "text": "Answer", "entry_id": "9"},
        )

        assert events[0][0] == "steer"
        assert events[0][1]["before_turn"] is True
        assert events[0][1]["request_id"] == "s0"

    @pytest.mark.asyncio
    async def test_the_turns_own_message_closes_what_a_recovered_run_answered(self) -> None:
        chart = {"data": [{"x": [1]}], "layout": {}}
        events = await _collect(
            {
                "type": "steer",
                "request_id": "s0",
                "status": "applied",
                "entry_id": "4",
                "text": "Use Q5",
                "answer": "",
                "before_turn": True,
            },
            {"type": "chart", "chart": chart},
            {"type": "text_delta", "delta": "Plotted."},
            {"type": "turn_start", "answer": "Plotted."},
            {"type": "text_delta", "delta": "Answer."},
            {"type": "done", "text": "Answer.", "entry_id": "9"},
        )

        assert [name for name, _ in events] == [
            "steer",
            "delta",
            "turn_start",
            "delta",
            "status",
            "result",
        ]
        # The recovered answer and its chart end at the turn's own message.
        assert events[2][1] == {
            "result": {
                "blocks": [
                    {"type": "chart", "content": None, "chart": chart},
                    {"type": "text", "content": "Plotted.", "chart": None},
                ],
                "assessment": None,
            }
        }
        assert events[-1][1] == {
            "blocks": [{"type": "text", "content": "Answer.", "chart": None}],
            "assessment": None,
            "entry_id": "9",
        }

    @pytest.mark.asyncio
    async def test_a_withdrawn_steer_is_reported(self) -> None:
        events = await _collect(
            {"type": "steer", "request_id": "s1", "status": "withdrawn", "reason": "aborted"},
            {"type": "error", "message": "conversation was not answered: aborted"},
        )

        assert events[0] == (
            "steer",
            {"request_id": "s1", "status": "withdrawn", "reason": "aborted"},
        )
        assert events[1][0] == "error"

    @pytest.mark.asyncio
    async def test_a_continue_with_nothing_to_answer_is_a_noop_not_an_error(self) -> None:
        events = await _collect({"type": "noop", "reason": "nothing_to_answer"})

        assert events == [("noop", {"reason": "nothing_to_answer"})]

    @pytest.mark.asyncio
    async def test_a_steer_without_its_request_id_is_malformed(self) -> None:
        events = await _collect({"type": "steer", "status": "applied"})

        assert events[0][0] == "error"


def test_a_continue_is_forwarded_without_its_message(monkeypatch: pytest.MonkeyPatch) -> None:
    from qdash.api.services import pi_chat_service
    from qdash.copilot.config import CopilotConfig, ModelConfig
    from qdash.copilot.contracts.models import ChatRequest

    monkeypatch.setattr(pi_chat_service, "user_instructions", lambda _username: None)
    config = CopilotConfig(model=ModelConfig(provider="vllm", name="m"))
    request = ChatRequest.model_validate(
        {"message": "", "session_id": "s1", "request_id": "r1", "continue_run": True}
    )
    payload = pi_chat_service._request_payload(request, config, "alice")

    assert payload["continue"] is True
    assert payload["request_id"] == "r1"
    plain = ChatRequest.model_validate({"message": "hi", "session_id": "s1"})
    assert "continue" not in pi_chat_service._request_payload(plain, config, "alice")


class _RuntimeResponse:
    def __init__(self, status_code: int, body: Any) -> None:
        self.status_code = status_code
        self._body = body

    def json(self) -> Any:
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


def _fake_runtime(
    monkeypatch: pytest.MonkeyPatch, response: _RuntimeResponse, sent: list[dict[str, Any]]
) -> None:
    import httpx

    class Client:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> Client:
            return self

        async def __aexit__(self, *_args: Any) -> None:
            return None

        async def post(self, url: str, *, headers: dict[str, str], json: Any) -> _RuntimeResponse:
            sent.append({"url": url, "headers": headers, "json": json})
            return response

    monkeypatch.setattr(httpx, "AsyncClient", Client)
    monkeypatch.setenv("AGENT_RUNTIME_TOKEN", "runtime-token")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "body", "expected"),
    [
        (200, {"status": "queued", "submission_id": "5"}, {"status": "queued"}),
        (
            200,
            {"status": "applied", "submission_id": "5", "entry_id": "8"},
            {"status": "applied", "entry_id": "8"},
        ),
        (
            200,
            {"status": "withdrawn", "submission_id": "5", "reason": "aborted"},
            {"status": "withdrawn", "reason": "aborted"},
        ),
        (409, {"status": "rejected", "reason": "idle"}, {"status": "rejected", "reason": "idle"}),
    ],
)
async def test_a_steer_reaches_the_runtime_with_the_users_credentials(
    monkeypatch: pytest.MonkeyPatch, status_code: int, body: Any, expected: dict[str, Any]
) -> None:
    from qdash.api.services import pi_chat_service

    sent: list[dict[str, Any]] = []
    _fake_runtime(monkeypatch, _RuntimeResponse(status_code, body), sent)
    result = await pi_chat_service.steer_runtime_turn(
        "alice",
        "s1",
        request_id="r1",
        turn_request_id="t1",
        message="Use Q5",
        auth=pi_chat_service.QDashAuth("alice-token", "p1"),
    )

    assert result == {"reason": None, "entry_id": None, **expected}
    assert sent[0]["url"].endswith("/chat/steer")
    assert sent[0]["json"] == {
        "owner_id": "alice",
        "conversation_id": "s1",
        # A chat never branched is its own store's root: no conversation is named.
        "store_session_id": "s1",
        "request_id": "r1",
        "turn_request_id": "t1",
        "message": "Use Q5",
    }
    assert sent[0]["headers"]["X-QDash-Token"] == "alice-token"
    assert sent[0]["headers"]["X-QDash-Project-Id"] == "p1"
    assert sent[0]["headers"]["Authorization"] == "Bearer runtime-token"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "body", "expected_status"),
    [(403, {"error": "other project"}, 403), (500, ValueError("not json"), 502)],
)
async def test_a_refused_steer_raises(
    monkeypatch: pytest.MonkeyPatch, status_code: int, body: Any, expected_status: int
) -> None:
    from qdash.api.services import pi_chat_service

    _fake_runtime(monkeypatch, _RuntimeResponse(status_code, body), [])
    with pytest.raises(pi_chat_service.SteerRefusedError) as raised:
        await pi_chat_service.steer_runtime_turn(
            "alice",
            "s1",
            request_id="r1",
            turn_request_id="t1",
            message="x",
            auth=pi_chat_service.QDashAuth("t"),
        )
    assert raised.value.status_code == expected_status


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "body", "expected"),
    [
        (200, {"status": "not_found"}, {"status": "not_found"}),
        (
            200,
            {"status": "applied", "submission_id": "5", "entry_id": "8"},
            {"status": "applied", "entry_id": "8"},
        ),
        (200, {"status": "queued", "submission_id": "5"}, {"status": "queued"}),
    ],
)
async def test_a_steer_status_only_reads_and_never_sends_the_message(
    monkeypatch: pytest.MonkeyPatch, status_code: int, body: Any, expected: dict[str, Any]
) -> None:
    from qdash.api.services import pi_chat_service

    sent: list[dict[str, Any]] = []
    _fake_runtime(monkeypatch, _RuntimeResponse(status_code, body), sent)
    result = await pi_chat_service.steer_runtime_status(
        "alice", "s1", request_id="r1", auth=pi_chat_service.QDashAuth("alice-token", "p1")
    )

    assert result == {"reason": None, "entry_id": None, **expected}
    assert sent[0]["url"].endswith("/chat/steer/status")
    # No message: the lookup cannot admit anything.
    assert sent[0]["json"] == {
        "owner_id": "alice",
        "conversation_id": "s1",
        "store_session_id": "s1",
        "request_id": "r1",
    }
    assert sent[0]["headers"]["X-QDash-Project-Id"] == "p1"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "body", "expected_status"),
    [(403, {"error": "another project"}, 403), (503, {"error": "store"}, 502)],
)
async def test_a_refused_steer_status_raises(
    monkeypatch: pytest.MonkeyPatch, status_code: int, body: Any, expected_status: int
) -> None:
    from qdash.api.services import pi_chat_service

    _fake_runtime(monkeypatch, _RuntimeResponse(status_code, body), [])
    with pytest.raises(pi_chat_service.SteerRefusedError) as raised:
        await pi_chat_service.steer_runtime_status(
            "alice", "s1", request_id="r1", auth=pi_chat_service.QDashAuth("t", "p2")
        )
    assert raised.value.status_code == expected_status


def _failing_runtime(monkeypatch: pytest.MonkeyPatch, error: Exception) -> None:
    import httpx

    class Client:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> Client:
            return self

        async def __aexit__(self, *_args: Any) -> None:
            return None

        async def post(self, *_args: Any, **_kwargs: Any) -> _RuntimeResponse:
            raise error

    monkeypatch.setattr(httpx, "AsyncClient", Client)


@pytest.mark.asyncio
async def test_a_fork_failure_says_whether_the_request_may_still_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import httpx

    from qdash.api.services import pi_chat_service
    from qdash.api.services.copilot_chat_session_service import (
        BranchRefusedError,
        ForkSettledError,
    )

    # The store generation is read from MongoDB; this test is about the runtime call only.
    monkeypatch.setattr(pi_chat_service, "store_generation", lambda _user, _store: "g1")

    async def fork() -> Any:
        return await pi_chat_service.fork_runtime_branch(
            "alice", "s1", None, "5", "b1", auth=pi_chat_service.QDashAuth("t", "p1")
        )

    # A refusal: the runtime created nothing.
    _fake_runtime(monkeypatch, _RuntimeResponse(409, {"error": "busy", "reason": "busy"}), [])
    with pytest.raises(BranchRefusedError) as refused:
        await fork()
    assert refused.value.reason == "busy"
    # A storage fault the runtime answered, or a runtime never reached: over, outcome unknown.
    _fake_runtime(monkeypatch, _RuntimeResponse(500, {"error": "internal server error"}), [])
    with pytest.raises(ForkSettledError):
        await fork()
    _failing_runtime(monkeypatch, httpx.ConnectError("refused"))
    with pytest.raises(ForkSettledError):
        await fork()
    # A timeout: the runtime may still be forking, so it is not reported as over.
    _failing_runtime(monkeypatch, httpx.ReadTimeout("slow"))
    with pytest.raises(httpx.ReadTimeout):
        await fork()


@pytest.mark.asyncio
async def test_a_store_held_by_a_deleted_chats_turn_is_removed_after_stopping_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from qdash.api.services import pi_chat_service
    from qdash.api.services.copilot_chat_session_service import RuntimeTarget

    answers = [False, True]
    deletes: list[tuple[str, str | None]] = []
    aborts: list[tuple[str, str, RuntimeTarget | None]] = []

    async def delete(username: str, store: str, generation: str | None = None) -> bool:
        deletes.append((store, generation))
        return answers.pop(0)

    async def abort(username: str, session_id: str, target: RuntimeTarget | None = None) -> str:
        aborts.append((username, session_id, target))
        return "stopped"

    monkeypatch.setattr(pi_chat_service, "delete_runtime_session_state", delete)
    monkeypatch.setattr(pi_chat_service, "abort_runtime_turn", abort)
    chats = [("b1", RuntimeTarget("s1", "7", "g1"))]
    assert await pi_chat_service.remove_runtime_store(
        "alice", "s1", "g1", chats, attempts=3, retry_delay=0
    )
    # Every attempt, a retry included, removes only the generation it was given.
    assert deletes == [("s1", "g1"), ("s1", "g1")]
    assert aborts == [("alice", "b1", RuntimeTarget("s1", "7", "g1"))]
    # Still held after every attempt: reported, so the deleted chat is kept for a retry.
    answers[:] = [False, False]
    assert not await pi_chat_service.remove_runtime_store(
        "alice", "s1", "g1", chats, attempts=2, retry_delay=0
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "expected"),
    [(200, "stopped"), (404, "not_running"), (409, "unknown"), (502, "unknown")],
)
async def test_stopping_a_turn_reports_what_the_runtime_confirmed(
    monkeypatch: pytest.MonkeyPatch, status_code: int, expected: str
) -> None:
    from qdash.api.services import pi_chat_service
    from qdash.api.services.copilot_chat_session_service import RuntimeTarget

    sent: list[dict[str, Any]] = []
    _fake_runtime(monkeypatch, _RuntimeResponse(status_code, {}), sent)
    outcome = await pi_chat_service.abort_runtime_turn(
        "alice", "b1", RuntimeTarget("s1", "7", "g1")
    )
    assert outcome == expected
    # Exactly that chat: its store, that incarnation of it, and its conversation.
    assert sent[0]["json"] == {
        "owner_id": "alice",
        "conversation_id": "b1",
        "store_session_id": "s1",
        "store_conversation_id": "7",
        "store_generation": "g1",
    }
    assert "X-QDash-Token" not in sent[0]["headers"]
    # A deleted chat's stop also asks for work its store kept, with the user's credentials.
    sent.clear()
    await pi_chat_service.abort_runtime_turn(
        "alice",
        "b1",
        RuntimeTarget("s1", "7", "g1"),
        stored_with=pi_chat_service.QDashAuth("alice-token", "p1"),
    )
    assert sent[0]["json"]["include_stored"] is True
    assert sent[0]["headers"]["X-QDash-Token"] == "alice-token"


@pytest.mark.asyncio
async def test_a_stop_the_runtime_never_answered_is_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import httpx

    from qdash.api.services import pi_chat_service

    _failing_runtime(monkeypatch, httpx.ConnectError("down"))
    assert await pi_chat_service.abort_runtime_turn("alice", "s1") == "unknown"


def test_a_reattach_is_forwarded_and_sends_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    from qdash.api.services import pi_chat_service
    from qdash.copilot.config import CopilotConfig, ModelConfig
    from qdash.copilot.contracts.models import ChatRequest

    monkeypatch.setattr(pi_chat_service, "user_instructions", lambda _username: None)
    config = CopilotConfig(model=ModelConfig(provider="vllm", name="m"))
    request = ChatRequest.model_validate(
        {"message": "calibrate Q0", "session_id": "s1", "request_id": "r1", "reattach": True}
    )
    payload = pi_chat_service._request_payload(request, config, "alice")

    assert payload["reattach"] is True
    assert payload["request_id"] == "r1"
    plain = ChatRequest.model_validate({"message": "hi", "session_id": "s1"})
    assert "reattach" not in pi_chat_service._request_payload(plain, config, "alice")


class TestStreamLoss:
    """A stream that ends before the turn did says so, so the chat reattaches."""

    @pytest.mark.asyncio
    async def test_a_stream_that_closes_without_a_result_is_lost_not_failed(self) -> None:
        events = await _collect(
            {"type": "tool_start", "name": "qdash_wait_agent_intervention", "id": "w1"},
        )

        name, data = events[-1]
        assert name == "error"
        assert data["code"] == "stream_lost"

    @pytest.mark.asyncio
    async def test_a_runtime_error_keeps_its_code(self) -> None:
        events = await _collect(
            {"type": "error", "message": "refused", "code": "turn_not_started"},
        )

        assert events == [
            ("error", {"step": "run_chat", "detail": "refused", "code": "turn_not_started"})
        ]

    @pytest.mark.asyncio
    async def test_a_failed_answer_has_no_stream_loss_code(self) -> None:
        events = await _collect({"type": "error", "message": "conversation was not answered"})

        assert "code" not in events[0][1]


def _mock_runtime(monkeypatch: pytest.MonkeyPatch, handler: Any) -> None:
    import httpx

    real = httpx.AsyncClient

    def client(**kwargs: Any) -> httpx.AsyncClient:
        return real(**kwargs, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(httpx, "AsyncClient", client)
    monkeypatch.setenv("AGENT_RUNTIME_TOKEN", "runtime-token")


async def _stream_payload(payload: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    from qdash.api.services.pi_chat_service import QDashAuth, stream_payload

    auth = QDashAuth(access_token="user-token", project_id="p1")
    return [
        _parse(sse)
        async for sse in stream_payload(payload, step="run_chat", auth=auth)
        if not sse.startswith(":")
    ]


@pytest.mark.asyncio
async def test_a_dropped_runtime_connection_is_reported_as_stream_lost(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import httpx

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.RemoteProtocolError("peer closed connection", request=request)

    _mock_runtime(monkeypatch, handler)
    events = await _stream_payload({"request_id": "r1", "reattach": True})

    assert events[-1][0] == "error"
    assert events[-1][1]["code"] == "stream_lost"


@pytest.mark.asyncio
async def test_a_reattach_to_an_unknown_turn_is_turn_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import httpx

    sent: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(
            404, json={"error": "The assistant has no record", "reason": "turn_not_found"}
        )

    _mock_runtime(monkeypatch, handler)
    events = await _stream_payload({"request_id": "r1", "reattach": True})

    assert sent == [{"request_id": "r1", "reattach": True}]
    assert events == [
        (
            "error",
            {
                "step": "run_chat",
                "detail": "The assistant has no record",
                "code": "turn_not_found",
            },
        )
    ]


@pytest.mark.asyncio
async def test_a_reattached_stream_replays_the_resumed_turn_to_its_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import httpx

    lines = [
        {"type": "tool_start", "name": "qdash_wait_agent_intervention", "id": "w1"},
        {"type": "ping"},
        {"type": "tool_end", "name": "qdash_wait_agent_intervention", "id": "w1", "isError": False},
        {"type": "text_delta", "delta": "Resumed."},
        {"type": "done", "text": "Resumed.", "entry_id": "12"},
    ]

    def handler(_request: httpx.Request) -> httpx.Response:
        body = "".join(json.dumps(line) + "\n" for line in lines)
        return httpx.Response(200, text=body, headers={"Content-Type": "application/x-ndjson"})

    _mock_runtime(monkeypatch, handler)
    events = await _stream_payload({"request_id": "r1", "reattach": True})

    names = [name for name, _ in events]
    assert names == ["tool_start", "status", "tool_end", "status", "delta", "status", "result"]
    assert events[-1][1]["entry_id"] == "12"
