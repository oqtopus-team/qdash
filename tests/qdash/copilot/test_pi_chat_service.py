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
        self.answers: list[str] = []

    def record(self, record: dict[str, Any]) -> dict[str, str] | None:
        self.records.append(record)
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
                    "isError": False,
                    "evaluation": {"prompt": "p", "model": "vllm/ising", "record": record},
                },
                {"type": "done", "text": "Looks good"},
            ),
            recorder=recorder,
        )
    ]

    assert recorder.records == [record]
    assert recorder.answers == ["Looks good"]
    end = next(data for name, data in events if name == "tool_end")
    assert end["evaluation"] == {
        "prompt": "p",
        "model": "vllm/ising",
        "run_id": "evr_1",
        "evaluation_id": "ev_1",
    }


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
    }
