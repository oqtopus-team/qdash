"""The agent runtime's presentation contract, as the API validates it.

The runtime maps a chat turn's events to what the chat shows and streams them
as envelopes, one JSON object per line (``agent-runtime/src/presentation.ts``)::

    {"v": 1, "event": "tool_end", "data": {...}, "internal": {...}}

``data`` is exactly the payload of the SSE event ``event`` the chat reads.
``internal`` carries what only the API uses (an evaluation record to store, the
turn's answer text) and is never relayed. Every model forbids unknown fields and
coerces nothing, so a relayed ``data`` is the runtime's own object, checked.
Shared cases live in ``agent-runtime/testdata/presentation-v1.json``.
"""

from __future__ import annotations

import json
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StrictBool,
    StrictInt,
    StrictStr,
    TypeAdapter,
    ValidationError,
    field_validator,
    model_validator,
)

PRESENTATION_VERSION = 1
PRESENTATION_MEDIA_TYPE = "application/vnd.qdash.agent-presentation+x-ndjson"
# What the API asks the runtime for; an older runtime ignores it and sends NDJSON.
PRESENTATION_ACCEPT = (
    f"{PRESENTATION_MEDIA_TYPE}; version={PRESENTATION_VERSION}, application/x-ndjson;q=0.5"
)
# Bound on one envelope line. A turn's final ``result`` carries every chart it drew.
MAX_ENVELOPE_CHARS = 16 * 1024 * 1024
# Bound on one stored ``ui`` block; the runtime caps the spec itself at 100k characters.
MAX_UI_BLOCK_CHARS = 200_000
MAX_LABEL_CHARS = 200
MAX_CLASSIFICATION_TEXT = 200
MAX_CLASSIFICATION_CATEGORIES = 8

Label = Annotated[StrictStr, Field(min_length=1, max_length=MAX_LABEL_CHARS)]
ShortText = Annotated[StrictStr, Field(min_length=1, max_length=MAX_CLASSIFICATION_TEXT)]


class PresentationError(ValueError):
    """An envelope the API refuses to relay; ``detail`` is what the chat is told."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


Probability = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False, strict=False)]


class _Text(_Strict):
    text: StrictStr


class _ToolDraft(_Strict):
    index: StrictInt
    id: StrictStr | None
    tool: Label
    label: Label


class _ToolArgsDelta(_Strict):
    index: StrictInt
    path: list[StrictStr | StrictInt]
    delta: StrictStr


class _ToolStart(_Strict):
    id: StrictStr | None
    tool: Label
    label: Label
    args: JsonValue


class _Status(_Strict):
    step: Literal["tool_call", "thinking", "complete"]
    message: StrictStr
    tool: Label | None = None
    completed_tools: list[Label] | None = None


class _Evaluation(_Strict):
    """What an evaluation tool sent its model; ids are the API's to add, never the runtime's."""

    prompt: StrictStr = Field(min_length=1)
    model: StrictStr | None = None
    fallback: StrictBool | None = None


class _RankedCategory(_Strict):
    category: ShortText
    probability: Probability

    @field_validator("probability", mode="before")
    @classmethod
    def _number(cls, value: Any) -> Any:
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ValueError("must be a number")
        return value


class _Classification(_Strict):
    classifier: ShortText
    outcome: Literal["classified", "ambiguous", "failed"]
    category: ShortText | None = None
    probability: Probability | None = None
    margin: float | None = Field(default=None, allow_inf_nan=False, strict=False)
    probabilities: list[_RankedCategory] | None = Field(
        default=None, min_length=1, max_length=MAX_CLASSIFICATION_CATEGORIES
    )
    reason: ShortText | None = None

    @field_validator("probability", "margin", mode="before")
    @classmethod
    def _number(cls, value: Any) -> Any:
        if value is not None and (isinstance(value, bool) or not isinstance(value, int | float)):
            raise ValueError("must be a number")
        return value


class _CalibrationSession(_Strict):
    calibration_session_id: StrictStr = Field(pattern=r"^[A-Za-z0-9_.:-]{1,200}$")
    chip_id: StrictStr | None = Field(default=None, min_length=1, max_length=200)


class _ToolEnd(_Strict):
    id: StrictStr | None
    tool: Label
    label: Label
    is_error: StrictBool
    figures: list[StrictStr] | None = Field(default=None, min_length=1)
    evaluation: _Evaluation | None = None
    classification: _Classification | None = None
    calibration_session: _CalibrationSession | None = None
    output: StrictStr | None = Field(default=None, min_length=1)
    exit_code: StrictInt | None = None


class _TextBlock(_Strict):
    type: Literal["text"]
    content: StrictStr
    chart: None


class _Chart(_Strict):
    data: list[JsonValue]
    layout: JsonValue


class _ChartBlock(_Strict):
    type: Literal["chart"]
    content: None
    chart: _Chart


class _UiPayload(_Strict):
    version: StrictInt
    spec: dict[str, JsonValue]
    fallback: StrictStr


class _UiBlock(_Strict):
    type: Literal["ui"]
    content: StrictStr | None
    chart: None
    ui: _UiPayload

    @model_validator(mode="after")
    def _bounded(self) -> _UiBlock:
        size = len(json.dumps(self.ui.model_dump(), separators=(",", ":"), ensure_ascii=False))
        if size > MAX_UI_BLOCK_CHARS:
            raise ValueError("ui block exceeds its size bound")
        return self


class _AskBlock(_Strict):
    type: Literal["ask"]
    content: None
    chart: None
    ask: JsonValue


class _ApprovalBlock(_Strict):
    type: Literal["approval"]
    content: None
    chart: None
    approval: JsonValue


class _EditBlock(_Strict):
    type: Literal["edit"]
    content: None
    chart: None
    edit: JsonValue


_Block = Annotated[
    _TextBlock | _ChartBlock | _UiBlock | _AskBlock | _ApprovalBlock | _EditBlock,
    Field(discriminator="type"),
]


class _Blocks(_Strict):
    blocks: list[_Block]
    assessment: None


class _SteerApplied(_Strict):
    request_id: StrictStr
    status: Literal["applied"]
    entry_id: StrictStr | None
    text: StrictStr
    result: _Blocks
    before_turn: Literal[True] | None = None


class _SteerWithdrawn(_Strict):
    request_id: StrictStr
    status: Literal["withdrawn"]
    reason: StrictStr


class _TurnStart(_Strict):
    result: _Blocks


class _Noop(_Strict):
    reason: StrictStr


class _Error(_Strict):
    detail: StrictStr
    code: StrictStr | None = None


class _Result(_Strict):
    blocks: list[_Block] = Field(min_length=1)
    assessment: None
    entry_id: StrictStr | None = Field(default=None, min_length=1)


class _Keepalive(_Strict):
    pass


_EVENT_DATA: dict[str, TypeAdapter[Any]] = {
    "keepalive": TypeAdapter(_Keepalive),
    "delta": TypeAdapter(_Text),
    "thinking": TypeAdapter(_Text),
    "tool_draft": TypeAdapter(_ToolDraft),
    "tool_args_delta": TypeAdapter(_ToolArgsDelta),
    "tool_start": TypeAdapter(_ToolStart),
    "status": TypeAdapter(_Status),
    "tool_end": TypeAdapter(_ToolEnd),
    # A composed UI, or its plain-text fallback when the UI itself was malformed.
    "ui": TypeAdapter(Annotated[_UiBlock | _TextBlock, Field(discriminator="type")]),
    "steer": TypeAdapter(Annotated[_SteerApplied | _SteerWithdrawn, Field(discriminator="status")]),
    "turn_start": TypeAdapter(_TurnStart),
    "noop": TypeAdapter(_Noop),
    "error": TypeAdapter(_Error),
    "result": TypeAdapter(_Result),
}

# Events that end a turn's stream.
TERMINAL_EVENTS = frozenset({"noop", "error", "result"})


class EvaluationRecord(_Strict):
    """An evaluation tool's record, which the API stores; the chat sees only its ids."""

    record: dict[str, JsonValue]
    entry_id: StrictStr | None = Field(default=None, min_length=1)
    before_turn: Literal[True] | None = None


class PresentationInternal(_Strict):
    evaluation_record: EvaluationRecord | None = None
    answer: StrictStr | None = None


class PresentationEnvelope(_Strict):
    v: Literal[1]
    event: StrictStr
    data: dict[str, JsonValue]
    internal: PresentationInternal | None = None


# Which events may carry which ``internal`` fields.
_INTERNAL_FIELDS = {"tool_end": {"evaluation_record"}, "result": {"answer"}, "error": {"answer"}}


def parse_envelope(line: str) -> PresentationEnvelope:
    """Validate one envelope line, or raise ``PresentationError`` saying what was refused."""
    if len(line) > MAX_ENVELOPE_CHARS:
        raise PresentationError("Agent runtime sent an event over the size limit")
    try:
        raw = json.loads(line)
    except ValueError as exc:
        raise PresentationError("Agent runtime sent malformed data") from exc
    if not isinstance(raw, dict):
        raise PresentationError("Agent runtime sent malformed data")
    if type(raw.get("v")) is not int or raw["v"] != PRESENTATION_VERSION:
        raise PresentationError("Agent runtime sent an unsupported presentation version")
    if not isinstance(raw.get("event"), str) or raw["event"] not in _EVENT_DATA:
        raise PresentationError("Agent runtime sent an unknown event")
    try:
        envelope = PresentationEnvelope.model_validate(raw)
        _EVENT_DATA[envelope.event].validate_python(envelope.data)
    except ValidationError as exc:
        raise PresentationError("Agent runtime sent malformed data") from exc
    internal = envelope.internal
    if internal is not None:
        allowed = _INTERNAL_FIELDS.get(envelope.event, set())
        if not internal.model_fields_set <= allowed:
            raise PresentationError("Agent runtime sent malformed data")
        if internal.evaluation_record is not None and not isinstance(
            envelope.data.get("evaluation"), dict
        ):
            raise PresentationError("Agent runtime sent malformed data")
    return envelope
