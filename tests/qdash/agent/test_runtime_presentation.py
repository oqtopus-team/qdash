"""The API's side of the runtime presentation contract: validation, relay, and parity.

The shared cases (``agent-runtime/testdata/presentation-v1.json``) hold, for the
same runtime events, the envelopes the runtime sends and the SSE the chat reads.
The runtime's tests check the envelopes; these check that the API relays them to
that SSE, and that the legacy NDJSON adapter yields the same SSE from the events.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from qdash.agent.contracts.presentation import (
    PRESENTATION_ACCEPT,
    PresentationError,
    parse_envelope,
)
from qdash.api.services.chat_transcript import TurnTranscript
from qdash.api.services.pi_runtime_legacy import translate
from qdash.api.services.runtime_presentation import (
    EnvelopeTooLargeError,
    bounded_lines,
    presentation_version,
    relay,
)
from qdash.dbmodel.agent_chat_session import AgentChatMessage

_SHARED = json.loads(
    (Path(__file__).parents[3] / "agent-runtime" / "testdata" / "presentation-v1.json").read_text()
)
_CASES = _SHARED["cases"]
_MEDIA = "application/vnd.qdash.agent-presentation+x-ndjson"


async def _lines(*items: Any):
    for item in items:
        yield item if isinstance(item, str) else json.dumps(item)


def _parse(sse: str) -> Any:
    if sse.startswith(":"):
        return ":"
    name, data = sse.strip().split("\n", 1)
    return [name.removeprefix("event: "), json.loads(data.removeprefix("data: "))]


async def _relay(*envelopes: Any, **kwargs: Any) -> list[Any]:
    return [_parse(sse) async for sse in relay(_lines(*envelopes), **kwargs)]


def _env(event: str, data: dict[str, Any], **internal: Any) -> dict[str, Any]:
    return {"v": 1, "event": event, "data": data, **({"internal": internal} if internal else {})}


class _Recorder:
    def __init__(self) -> None:
        self.records: list[tuple[dict[str, Any], str | None]] = []
        self.answers: list[str] = []

    def record(self, record: dict[str, Any], call: str | None = None) -> dict[str, str] | None:
        self.records.append((record, call))
        return {"run_id": "run-1", "evaluation_id": "ev-1"}

    def finish(self, answer: str) -> None:
        self.answers.append(answer)


@pytest.mark.parametrize("case", _CASES, ids=[case["name"] for case in _CASES])
@pytest.mark.asyncio
async def test_the_api_relays_each_shared_case_to_the_chats_sse(case: dict[str, Any]) -> None:
    assert await _relay(*case["presentation"]) == case["sse"]


@pytest.mark.parametrize("case", _CASES, ids=[case["name"] for case in _CASES])
@pytest.mark.asyncio
async def test_presentation_preserves_saved_progress_and_replayed_history(
    case: dict[str, Any],
) -> None:
    def stored(turn: TurnTranscript) -> list[dict[str, Any]]:
        # Record creation time varies; compare content, identity, and ordering.
        return [message.model_dump(exclude={"created_at"}) for message in turn.messages()]

    user = AgentChatMessage(role="user", content="Question", turn_request_id="r1")
    expected = TurnTranscript("r1", user, clock=lambda: 1000)
    actual = TurnTranscript("r1", user, clock=lambda: 1000)
    events = await _relay(*case["presentation"])
    for received, recorded in zip(events, case["sse"], strict=True):
        if recorded == ":":
            continue
        expected.apply(*recorded)
        actual.apply(*received)
        # Compare the persisted message shape after every event, including partial answers.
        assert stored(actual) == stored(expected)
        assert (actual.end, actual.error) == (expected.end, expected.error)
    saved = stored(actual)
    actual.restart()
    for event in events:
        if event != ":":
            actual.apply(*event)
    assert stored(actual) == saved


@pytest.mark.parametrize("case", _CASES, ids=[case["name"] for case in _CASES])
@pytest.mark.asyncio
async def test_the_legacy_adapter_yields_the_same_sse_from_the_runtime_events(
    case: dict[str, Any],
) -> None:
    legacy = [_parse(sse) async for sse in translate(_lines(*case["runtime_events"]))]
    assert legacy == case["sse"]


@pytest.mark.asyncio
async def test_both_paths_record_evaluations_and_answers_the_same_way() -> None:
    case = next(c for c in _CASES if c["name"] == "evaluation_classification_session")
    relayed, legacy = _Recorder(), _Recorder()
    via_contract = await _relay(*case["presentation"], recorder=relayed)
    via_legacy = [
        _parse(sse) async for sse in translate(_lines(*case["runtime_events"]), recorder=legacy)
    ]

    assert via_contract == via_legacy
    assert (
        relayed.records == legacy.records == [({"task_id": "task-1", "verdict": "good"}, "entry:5")]
    )
    assert relayed.answers == legacy.answers == ["Evaluated."]
    [evaluation] = [
        data["evaluation"]
        for name, data in via_contract
        if name == "tool_end" and "evaluation" in data
    ]
    assert evaluation == {
        "prompt": "Reference for CheckRabi",
        "model": "vllm/ising",
        "fallback": True,
        "run_id": "run-1",
        "evaluation_id": "ev-1",
    }
    assert "record" not in json.dumps(via_contract)


@pytest.mark.asyncio
async def test_an_earlier_turns_evaluation_is_not_filed_with_this_turn() -> None:
    recorder = _Recorder()
    events = await _relay(
        _env(
            "tool_end",
            {
                "id": "e1",
                "tool": "qcal_evaluate",
                "label": "Qcal evaluate",
                "is_error": False,
                "evaluation": {"prompt": "p"},
            },
            evaluation_record={"record": {"task_id": "t"}, "entry_id": "3", "before_turn": True},
        ),
        recorder=recorder,
    )
    assert recorder.records == []
    assert events[0][1]["evaluation"] == {"prompt": "p"}


@pytest.mark.asyncio
async def test_an_empty_answer_still_reaches_the_recorder() -> None:
    case = next(c for c in _CASES if c["name"] == "empty_answer")
    recorder = _Recorder()
    events = await _relay(*case["presentation"], recorder=recorder)
    assert recorder.answers == [""]
    assert events[-1] == [
        "error",
        {"step": "run_chat", "detail": "The model returned an empty response"},
    ]


@pytest.mark.asyncio
async def test_the_api_adds_its_step_and_extra_result() -> None:
    result = {"blocks": [{"type": "text", "content": "ok", "chart": None}], "assessment": None}
    events = await _relay(
        _env("result", result, answer="ok"),
        step="run_analysis",
        extra_result={"images_sent": {"count": 1}},
    )
    assert events == [["result", {**result, "images_sent": {"count": 1}}]]
    events = await _relay(_env("error", {"detail": "no"}), step="run_analysis")
    assert events == [["error", {"step": "run_analysis", "detail": "no"}]]


def _tool_end(**fields: Any) -> dict[str, Any]:
    return {"id": "c1", "tool": "bash", "label": "Bash", "is_error": False, **fields}


@pytest.mark.parametrize(
    ("line", "detail"),
    [
        (_env("delta", {"text": "x"}) | {"v": 2}, "unsupported presentation version"),
        ({"event": "delta", "data": {"text": "x"}}, "unsupported presentation version"),
        (_env("delta", {"text": "x"}) | {"v": True}, "unsupported presentation version"),
        (_env("delta", {"text": "x"}) | {"v": 1.0}, "unsupported presentation version"),
        (_env("script", {"html": "<b>"}), "unknown event"),
        (_env("delta", {"text": "x"}) | {"event": []}, "unknown event"),
        (_env("delta", {"text": "x"}) | {"event": {}}, "unknown event"),
        (_env("transcript", {"saved": True}), "unknown event"),
        (_env("restart", {}), "unknown event"),
        (_env("delta", {"text": 1}), "malformed data"),
        (_env("delta", {"text": "x", "html": "<b>"}), "malformed data"),
        (_env("tool_end", _tool_end(label="")), "malformed data"),
        (
            _env("tool_end", _tool_end(evaluation={"prompt": "p", "record": {"secret": 1}})),
            "malformed data",
        ),
        (
            _env("tool_end", _tool_end(evaluation={"prompt": "p", "run_id": "forged"})),
            "malformed data",
        ),
        (_env("tool_end", _tool_end(exit_code=True)), "malformed data"),
        (
            _env(
                "tool_end",
                _tool_end(
                    classification={"classifier": "c", "outcome": "classified", "probability": 2}
                ),
            ),
            "malformed data",
        ),
        (
            _env("tool_end", _tool_end(calibration_session={"calibration_session_id": "../x"})),
            "malformed data",
        ),
        (_env("result", {"blocks": [], "assessment": None}), "malformed data"),
        (
            _env(
                "result",
                {"blocks": [{"type": "html", "content": "<b>", "chart": None}], "assessment": None},
            ),
            "malformed data",
        ),
        (
            _env(
                "ui",
                {
                    "type": "ui",
                    "content": None,
                    "chart": None,
                    "ui": {"version": 1, "spec": {"x": "y" * 200_001}, "fallback": ""},
                },
            ),
            "malformed data",
        ),
        (_env("delta", {"text": "x"}, answer="leak"), "malformed data"),
        (
            _env(
                "result",
                {"blocks": [{"type": "text", "content": "x", "chart": None}], "assessment": None},
                evaluation_record={"record": {}},
            ),
            "malformed data",
        ),
        (_env("tool_end", _tool_end(), evaluation_record={"record": {}}), "malformed data"),
        (_env("delta", {"text": "x"}) | {"extra": 1}, "malformed data"),
        ("not json", "malformed data"),
        ("[1, 2]", "malformed data"),
    ],
)
@pytest.mark.asyncio
async def test_a_refused_envelope_ends_the_stream_explicitly(line: Any, detail: str) -> None:
    events = await _relay(_env("delta", {"text": "before"}), line, _env("delta", {"text": "after"}))
    assert events[0] == ["delta", {"text": "before"}]
    assert len(events) == 2
    name, data = events[1]
    assert name == "error"
    assert data["step"] == "run_chat"
    assert detail in data["detail"]
    assert "code" not in data


def test_parse_envelope_bounds_a_line() -> None:
    with pytest.raises(PresentationError, match="size limit"):
        parse_envelope(" " * (16 * 1024 * 1024 + 1))


@pytest.mark.asyncio
async def test_a_line_over_the_bound_is_refused_before_it_ends() -> None:
    async def chunks():
        yield '{"v": 1, "event": "delta", "data": {"text": "ok"}}\n'
        while True:
            yield "x" * 64

    lines = []
    with pytest.raises(EnvelopeTooLargeError):
        async for line in bounded_lines(chunks(), limit=256):
            lines.append(line)
    assert lines == ['{"v": 1, "event": "delta", "data": {"text": "ok"}}']

    async def huge():
        yield "x" * 300 + "\n"

    events = [_parse(sse) async for sse in relay(bounded_lines(huge(), limit=256))]
    assert events == [
        ["error", {"step": "run_chat", "detail": "Agent runtime sent an event over the size limit"}]
    ]


@pytest.mark.asyncio
async def test_bounded_lines_splits_across_chunks() -> None:
    async def chunks():
        yield '{"a"'
        yield ': 1}\n{"b": 2}\n\n{"c"'
        yield ": 3}"

    assert [line async for line in bounded_lines(chunks())] == [
        '{"a": 1}',
        '{"b": 2}',
        "",
        '{"c": 3}',
    ]


def test_the_response_media_type_selects_the_reader() -> None:
    assert presentation_version(None) is None
    assert presentation_version("application/x-ndjson") is None
    assert presentation_version("text/plain; charset=utf-8") is None
    assert presentation_version(f"{_MEDIA}; version=1") == 1
    assert presentation_version(f"{_MEDIA.upper()};version=1") == 1
    assert presentation_version(f"{_MEDIA}; version=2") == -1
    assert presentation_version(_MEDIA) == -1


def _mock_runtime(monkeypatch: pytest.MonkeyPatch, handler: Any) -> None:
    import httpx

    real = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: real(**kwargs, transport=httpx.MockTransport(handler)),
    )
    monkeypatch.setenv("AGENT_RUNTIME_TOKEN", "runtime-token")


async def _stream_payload() -> list[Any]:
    from qdash.api.services.pi_chat_service import QDashAuth, stream_payload

    auth = QDashAuth(access_token="user-token", project_id="p1")
    return [
        _parse(sse)
        async for sse in stream_payload({"request_id": "r1"}, step="run_chat", auth=auth)
    ]


@pytest.mark.asyncio
async def test_the_bridge_asks_for_the_contract_and_relays_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import httpx

    case = next(c for c in _CASES if c["name"] == "steers_and_recovered_turn_start")
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        body = "".join(json.dumps(line) + "\n" for line in case["presentation"])
        return httpx.Response(200, text=body, headers={"Content-Type": f"{_MEDIA}; version=1"})

    _mock_runtime(monkeypatch, handler)
    assert await _stream_payload() == case["sse"]
    assert sent[0].headers["Accept"] == PRESENTATION_ACCEPT
    assert sent[0].headers["X-QDash-Project-Id"] == "p1"


@pytest.mark.asyncio
async def test_the_bridge_reads_a_legacy_runtimes_ndjson(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    case = next(c for c in _CASES if c["name"] == "visuals_and_cards")

    def handler(_request: httpx.Request) -> httpx.Response:
        body = "".join(json.dumps(line) + "\n" for line in case["runtime_events"])
        return httpx.Response(200, text=body, headers={"Content-Type": "application/x-ndjson"})

    _mock_runtime(monkeypatch, handler)
    assert await _stream_payload() == case["sse"]


@pytest.mark.asyncio
async def test_the_bridge_refuses_an_unsupported_presentation_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import httpx

    def handler(_request: httpx.Request) -> httpx.Response:
        line = json.dumps(_env("delta", {"text": "x"}) | {"v": 2})
        return httpx.Response(
            200, text=line + "\n", headers={"Content-Type": f"{_MEDIA}; version=2"}
        )

    _mock_runtime(monkeypatch, handler)
    assert await _stream_payload() == [
        [
            "error",
            {
                "step": "run_chat",
                "detail": "Agent runtime sent an unsupported presentation version",
            },
        ]
    ]
