"""Mechanisms shared by QDash's calibration audits: agent sessions and calibration sessions.

An audit is a read-time projection of authoritative records into ``AgentAuditEvent`` entries,
plus one kind of written record: an append-only decision, the recorder's statement with a
frozen snapshot of what QDash's records said about its evidence. Both audits use what this
module holds, so their events, snapshots, cursors, exports, and decision recording behave the
same way:

- copying scalar parameters and text into events with bounds (``scalar_parameters``);
- ordering events (time, state version, cause before effect, id);
- a snapshot as two matching projected reads, pages bound to its fingerprint by a cursor that
  names the audited record, and an export that is refused rather than cut short;
- recording a decision once per idempotency key in the lowest free quota slot of its scope,
  without a transaction (unique indexes decide a race), replaying the record for a retry.

The scope of a record is the audited session: ``session_id`` for an agent session,
``calibration_session_id`` for a calibration session. Nothing here grants an operation.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Generic, TypeVar, cast
from uuid import uuid4

from bunnet import SortDirection
from fastapi import HTTPException, status
from pymongo.errors import DuplicateKeyError

from qdash.common.utils.datetime import now
from qdash.datamodel.agent_session import AgentModelIdentity

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from pydantic import BaseModel

    from qdash.api.schemas.agent_session import AgentAuditEvent

# Per-record bounds of copied scalars; an event says when a bound dropped entries.
MAX_PARAMETERS = 50
MAX_TEXT = 500
DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 500
# An export larger than this is refused rather than cut short.
MAX_EXPORT_EVENTS = 100_000
# Cursors name the snapshot they page through; v1 cursors (a sort key) are refused.
CURSOR_PREFIX = "v2"
# Reads of the whole record set one snapshot takes at most before it gives up.
SNAPSHOT_ATTEMPTS = 3
# Inserts one recording tries while concurrent recordings keep taking the slot it chose.
MAX_SLOT_ATTEMPTS = 20


def utc(value: datetime | None) -> datetime | None:
    """The time in UTC; a naive stored time is UTC."""
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def bounded_text(value: Any, limit: int = MAX_TEXT) -> str:
    """The text, cut to ``limit`` characters with an ellipsis."""
    text = str(value or "")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def scalar(value: Any) -> Any:
    """A JSON scalar copy of a value, or None when it is not a finite scalar."""
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        return value if math.isfinite(float(value)) else None
    if isinstance(value, str):
        return bounded_text(value, 200)
    return None


def scalar_parameters(raw: Mapping[str, Any] | None) -> tuple[dict[str, dict[str, Any]], int]:
    """Scalar parameter values with their unit and error; arrays and objects are left out."""
    items: dict[str, dict[str, Any]] = {}
    dropped = 0
    for name, entry in sorted((raw or {}).items()):
        if hasattr(entry, "model_dump"):
            entry = entry.model_dump()  # noqa: PLW2901 - a stored model reads as its dict
        if isinstance(entry, dict):
            value = scalar(entry.get("value"))
            row: dict[str, Any] = {"value": value}
            if entry.get("unit"):
                row["unit"] = bounded_text(entry.get("unit"), 50)
            error = scalar(entry.get("error"))
            if isinstance(error, (int, float)) and not isinstance(error, bool) and error:
                row["error"] = error
        else:
            value = scalar(entry)
            row = {"value": value}
        if value is None and not (isinstance(entry, dict) and entry.get("value") is None):
            dropped += 1
            continue
        if len(items) >= MAX_PARAMETERS:
            dropped += 1
            continue
        items[name] = row
    return items, dropped


def recorded_model(value: Any) -> AgentModelIdentity | None:
    """A model identity stored as a dict, or None when absent or not a valid identity."""
    if isinstance(value, AgentModelIdentity):
        return value
    if not isinstance(value, dict):
        return None
    try:
        return AgentModelIdentity.model_validate(value)
    except ValueError:
        return None


def json_safe(value: Any) -> Any:
    """A JSON round trip of a snapshot, with times as ISO strings."""
    return json.loads(
        json.dumps(
            value,
            default=lambda item: item.isoformat() if isinstance(item, datetime) else str(item),
        )
    )


# ---------------------------------------------------------------------- ordering


SortKey = tuple[str, int, int, str]


def event_sort_key(rank: Mapping[str, int]) -> Callable[[AgentAuditEvent], SortKey]:
    """Time, then the state version (stored times have millisecond precision, so records of
    one millisecond share a time), then cause before effect by ``rank``, then the id."""

    def key(event: AgentAuditEvent) -> SortKey:
        at = cast("datetime", utc(event.at))
        return (
            at.isoformat(timespec="milliseconds"),
            event.state_version,
            rank.get(event.kind, 99),
            event.event_id,
        )

    return key


def number_events(events: list[AgentAuditEvent], rank: Mapping[str, int]) -> None:
    """Sort events in their stable order and give each its sequence."""
    events.sort(key=event_sort_key(rank))
    for index, event in enumerate(events):
        event.sequence = index


# ---------------------------------------------------------------------- snapshots


H = TypeVar("H")


@dataclass(frozen=True)
class AuditSnapshot(Generic[H]):
    """One projected read: the audited record's header, its events, and their fingerprint."""

    header: H
    events: list[AgentAuditEvent]
    snapshot_id: str


def fingerprint(header: BaseModel, events: list[AgentAuditEvent]) -> str:
    """The snapshot id of a projected read."""
    digest = hashlib.sha256()
    digest.update(header.model_dump_json().encode())
    for event in events:
        digest.update(b"\n")
        digest.update(event.model_dump_json().encode())
    return digest.hexdigest()[:32]


def read_snapshot(read_once: Callable[[], AuditSnapshot[H]], noun: str) -> AuditSnapshot[H]:
    """Return two matching projected reads, or 503 if observed changes persist.

    Collections are read sequentially without a transaction. Matching fingerprints do not
    establish an atomic point-in-time snapshot: a value can change and revert between reads.
    The fingerprint binds pagination to matching projected content, not to an immutable view.
    """
    previous = read_once()
    for _ in range(SNAPSHOT_ATTEMPTS - 1):
        current = read_once()
        if current.snapshot_id == previous.snapshot_id:
            return current
        previous = current
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=(
            f"The {noun}'s records kept changing while its audit was read, so no consistent "
            "snapshot was taken; try again"
        ),
        headers={"Retry-After": "2"},
    )


@dataclass(frozen=True)
class CursorPosition:
    """Where a cursor continues: the audited record, its snapshot, and the next offset."""

    project_id: str
    scope_id: str
    snapshot_id: str
    offset: int


def encode_cursor(position: CursorPosition) -> str:
    """An opaque cursor for the next page of one snapshot."""
    raw = json.dumps(
        [
            CURSOR_PREFIX,
            position.project_id,
            position.scope_id,
            position.snapshot_id,
            position.offset,
        ],
        separators=(",", ":"),
    )
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_cursor(cursor: str) -> CursorPosition:
    """The position a cursor names; 400 for anything that is not a v2 cursor."""
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        prefix, project_id, scope_id, snapshot_id, offset = json.loads(
            base64.urlsafe_b64decode(padded.encode())
        )
        if (
            prefix != CURSOR_PREFIX
            or not all(isinstance(item, str) for item in (project_id, scope_id, snapshot_id))
            or not isinstance(offset, int)
            or isinstance(offset, bool)
            or offset < 1
        ):
            raise ValueError("unknown cursor")
        return CursorPosition(project_id, scope_id, snapshot_id, offset)
    except (ValueError, TypeError, binascii.Error, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid audit cursor; read the audit again from the first page",
        ) from exc


@dataclass(frozen=True)
class AuditPage(Generic[H]):
    """One page of a snapshot and the cursor of the next, or None at its end."""

    snapshot: AuditSnapshot[H]
    events: list[AgentAuditEvent]
    next_cursor: str | None


def read_page(
    *,
    project_id: str,
    scope_id: str,
    noun: str,
    read_once: Callable[[], AuditSnapshot[H]],
    cursor: str | None,
    limit: int,
) -> AuditPage[H]:
    """One page of a snapshot of a timeline, oldest first.

    The first page takes a snapshot; its cursor names the snapshot and the position after the
    page. A later page reads the records again and is served only when they still fingerprint
    as that snapshot; otherwise it is refused with 409 and the client starts again.
    """
    limit = max(1, min(limit, MAX_PAGE_SIZE))
    if cursor is None:
        snapshot = read_snapshot(read_once, noun)
        offset = 0
    else:
        position = decode_cursor(cursor)
        if position.project_id != project_id or position.scope_id != scope_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"The audit cursor belongs to another {noun}; read from the first page",
            )
        snapshot = read_once()
        if snapshot.snapshot_id != position.snapshot_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"The {noun}'s audit changed after its first page was read; the pages "
                    "already read belong to an older snapshot. Read it again from the first "
                    "page"
                ),
            )
        if position.offset >= len(snapshot.events):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid audit cursor"
            )
        offset = position.offset
    end = offset + limit
    next_cursor = (
        encode_cursor(CursorPosition(project_id, scope_id, snapshot.snapshot_id, end))
        if end < len(snapshot.events)
        else None
    )
    return AuditPage(snapshot, snapshot.events[offset:end], next_cursor)


def read_export(read_once: Callable[[], AuditSnapshot[H]], noun: str) -> AuditSnapshot[H]:
    """The whole of one snapshot; refused, never cut short, beyond the export bound."""
    snapshot = read_snapshot(read_once, noun)
    if len(snapshot.events) > MAX_EXPORT_EVENTS:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"The {noun}'s audit has {len(snapshot.events)} events, more than one export "
                f"holds ({MAX_EXPORT_EVENTS}); read it in pages with the audit endpoint"
            ),
        )
    return snapshot


# ---------------------------------------------------------------------- decisions


def decision_request_hash(body: BaseModel) -> str:
    """The hash a retry must match. The reported model is provenance, not part of the
    decision: a retry keeps the first record's model."""
    payload = json.dumps(
        body.model_dump(mode="json", exclude={"model"}),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()


D = TypeVar("D")


class DecisionLedger(Generic[D]):
    """Append-only decisions of one scope, with a quota and idempotent recording.

    ``document`` is the Bunnet document class; its collection has unique indexes on (scope,
    idempotency key) and (scope, quota slot), so the quota check and the record are one insert.
    """

    def __init__(
        self,
        document: Any,
        *,
        limit: int,
        noun: str,
        slots: Callable[[Mapping[str, str]], int] | None = None,
    ) -> None:
        self.document = document
        self.limit = limit
        self.noun = noun
        # Read through this hook so a caller can observe or interleave the quota read.
        self._slots = slots

    def by_key(self, scope: Mapping[str, str], key: str) -> D | None:
        return cast("D | None", self.document.find_one({**scope, "idempotency_key": key}).run())

    def used_slots(self, scope: Mapping[str, str]) -> int:
        """The next free quota slot, through the hook when one was given."""
        return self._slots(scope) if self._slots is not None else self.count_slots(scope)

    def count_slots(self, scope: Mapping[str, str]) -> int:
        """One past the highest quota slot of the scope; a removed record leaves its slot."""
        last = list(
            self.document.find(dict(scope))
            .sort([("quota_slot", SortDirection.DESCENDING)])
            .limit(1)
            .run()
        )
        return int(last[0].quota_slot) + 1 if last else 0

    def quota_full(self) -> HTTPException:
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"The {self.noun}'s audit is full: it already holds {self.limit} decisions, so "
                "no further decision is recorded"
            ),
        )

    def replay(self, existing: D, request_hash: str) -> D:
        if existing.request_hash != request_hash:  # type: ignore[attr-defined]
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Idempotency key was already used for a different decision",
            )
        return existing

    def precheck(self, scope: Mapping[str, str], key: str, request_hash: str) -> D | None:
        """The recorded decision for a retry, or None; 409 when the quota is used up."""
        existing = self.by_key(scope, key)
        if existing is not None:
            return self.replay(existing, request_hash)
        if self.used_slots(scope) >= self.limit:
            raise self.quota_full()
        return None

    def insert(self, scope: Mapping[str, str], fields: dict[str, Any], request_hash: str) -> D:
        """Insert the decision in the scope's lowest free quota slot.

        A refused insert means a concurrent recording won; the loop then replays that record
        when it carries the same key, or takes the next slot. Nothing is reserved apart from
        the record itself.
        """
        for _ in range(MAX_SLOT_ATTEMPTS):
            slot = self.used_slots(scope)
            if slot >= self.limit:
                raced = self.by_key(scope, fields["idempotency_key"])
                if raced is not None:
                    return self.replay(raced, request_hash)
                raise self.quota_full()
            doc = self.document(
                decision_id=str(uuid4()), recorded_at=now(), quota_slot=slot, **fields
            )
            try:
                doc.insert()
            except DuplicateKeyError:
                raced = self.by_key(scope, fields["idempotency_key"])
                if raced is not None:
                    return self.replay(raced, request_hash)
                continue
            return cast("D", doc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Other decisions of the {self.noun} were being recorded at the same time; retry",
            headers={"Retry-After": "1"},
        )
