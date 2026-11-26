"""Compare-and-set writes of one calibration parameter, and the backend apply lease.

QDash runs on standalone MongoDB without multi-document transactions, and ``QubitDocument``
has no version field. Agent commits therefore version one parameter by its stored value:

- ``read_parameter`` returns the raw stored sub-document of ``data.<name>`` (or its absence),
  exactly as MongoDB holds it.
- ``compare_and_set_parameter`` writes the new value with one ``find_one_and_update`` whose
  filter requires the stored sub-document to still equal an expected one (field order and
  types included, because the expected value was read back from MongoDB). A write by anyone
  else in between makes the filter miss, and nothing is written.

Other writers (workflow result saving, manual edits, reviewed set commits) still use
``QubitDocument.update_calib_data``, a read-modify-write ``save`` of the whole document. Such a
writer can still overwrite a value an agent committed after the fact; the agent side detects
that by comparing the stored value with the commit's ``after_snapshot`` before it relies on
it, and refuses rather than writing over it.

The apply lease (``AgentBackendApplyLockDocument``) serializes every agent candidate backend
apply on a chip, reviewed or session-granted, from its reservation until it settles. Workflow
runs that write parameter files themselves (``update_params``) do not take the lease, so
the lease orders agent applies only among themselves.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from qdash.common.utils.datetime import now
from qdash.datamodel.qubit import QubitModel
from qdash.dbmodel.agent_session import (
    AgentBackendApplyLockDocument,
    AgentCandidateCommitDocument,
)
from qdash.dbmodel.lookups import user_id_for_username
from qdash.dbmodel.qubit import QubitDocument
from qdash.dbmodel.qubit_history import QubitHistoryDocument

# Backend apply states in which an apply holds the chip's lease.
LEASE_HOLDING_BACKEND_STATUSES = ("dispatching", "queued", "applying")


@dataclass(frozen=True)
class StoredParameter:
    """One parameter of a qubit as MongoDB stores it; ``present`` is false when absent."""

    present: bool
    value: Any = None

    def as_record(self) -> dict[str, Any]:
        """The parameter as a storable baseline record."""
        return {"present": self.present, "value": deepcopy(self.value)}

    @classmethod
    def from_record(cls, record: Any) -> StoredParameter | None:
        """A baseline record read back, or None when it is not one."""
        if not isinstance(record, dict) or not isinstance(record.get("present"), bool):
            return None
        return cls(present=record["present"], value=record.get("value"))


def _checked_name(name: str) -> str:
    if not name or "." in name or name.startswith("$"):
        raise ValueError(f"Parameter name '{name}' cannot be written as one field")
    return name


def _qubit_filter(project_id: str, chip_id: str, qid: str) -> dict[str, Any]:
    return {"project_id": project_id, "chip_id": chip_id, "qid": qid}


def read_parameter(project_id: str, chip_id: str, qid: str, name: str) -> StoredParameter | None:
    """The stored ``data.<name>`` of a qubit, raw; None when the qubit does not exist."""
    field = f"data.{_checked_name(name)}"
    raw = QubitDocument.get_motor_collection().find_one(
        _qubit_filter(project_id, chip_id, qid), {field: 1}
    )
    if raw is None:
        return None
    data = raw.get("data")
    if not isinstance(data, dict) or name not in data:
        return StoredParameter(present=False)
    return StoredParameter(present=True, value=data[name])


def parameter_matches(stored: StoredParameter | None, expected: StoredParameter) -> bool:
    """Whether a stored parameter is exactly the expected one."""
    return (
        stored is not None
        and stored.present == expected.present
        and (not expected.present or stored.value == expected.value)
    )


def compare_and_set_parameter(
    *,
    project_id: str,
    chip_id: str,
    qid: str,
    name: str,
    expected: StoredParameter,
    snapshot: dict[str, Any],
    username: str,
) -> Any | None:
    """Write ``snapshot`` into ``data.<name>`` only while it still equals ``expected``.

    The new value is merged into the expected one as ``update_calib_data`` merges it. Returns
    the stored value after the write, or None when the stored value was not ``expected`` and
    nothing was written. A successful write also records the qubit history snapshot.
    """
    field = f"data.{_checked_name(name)}"
    condition: dict[str, Any] = (
        {field: expected.value} if expected.present else {field: {"$exists": False}}
    )
    base = deepcopy(expected.value) if isinstance(expected.value, dict) else {}
    merged = QubitDocument.merge_calib_data(base, deepcopy(snapshot))
    user_id = user_id_for_username(username)
    updated = QubitDocument.get_motor_collection().find_one_and_update(
        {**_qubit_filter(project_id, chip_id, qid), **condition},
        {
            "$set": {
                field: merged,
                "username": username,
                "user_id": user_id,
                "system_info.updated_at": now(),
            }
        },
        return_document=ReturnDocument.AFTER,
    )
    if updated is None:
        return None
    QubitHistoryDocument.create_history(
        QubitModel(
            project_id=project_id,
            user_id=user_id,
            qid=qid,
            chip_id=chip_id,
            data=updated["data"],
            username=username,
        )
    )
    return updated["data"][name]


def apply_lock_key(chip_id: str) -> str:
    """The lease key of a chip; one per chip id, since parameter files are per chip."""
    return f"chip:{chip_id}"


def acquire_backend_apply_lock(
    *, project_id: str, chip_id: str, session_id: str, commit_id: str, token: str
) -> str | None:
    """Take the chip's apply lease for one reserved apply; None when taken, else the holder.

    A lease whose holder no longer holds an apply reservation with that token (it settled or
    was released, and its own release did not happen) is stale; it is removed with a
    compare-and-delete and the insert is tried once more.
    """
    key = apply_lock_key(chip_id)
    collection = AgentBackendApplyLockDocument.get_motor_collection()
    record = {
        "lock_key": key,
        "project_id": project_id,
        "chip_id": chip_id,
        "session_id": session_id,
        "commit_id": commit_id,
        "token": token,
        "acquired_at": now(),
    }
    for _ in range(2):
        try:
            collection.insert_one(dict(record))
            return None
        except DuplicateKeyError:
            holder = collection.find_one({"lock_key": key})
        if holder is None:
            continue
        if holder.get("commit_id") == commit_id and holder.get("token") == token:
            return None
        holding = AgentCandidateCommitDocument.get_motor_collection().find_one(
            {
                "commit_id": holder.get("commit_id"),
                "backend_dispatch_token": holder.get("token"),
                "backend_status": {"$in": list(LEASE_HOLDING_BACKEND_STATUSES)},
            },
            {"commit_id": 1},
        )
        if holding is not None:
            return str(holder.get("commit_id"))
        collection.delete_one(
            {"lock_key": key, "commit_id": holder.get("commit_id"), "token": holder.get("token")}
        )
    holder = collection.find_one({"lock_key": key})
    return str(holder.get("commit_id")) if holder is not None else "unknown"


def holds_backend_apply_lock(chip_id: str, commit_id: str, token: str | None) -> bool:
    """Whether the apply of ``commit_id`` with ``token`` holds the chip's lease."""
    if not token:
        return False
    found = AgentBackendApplyLockDocument.get_motor_collection().find_one(
        {"lock_key": apply_lock_key(chip_id), "commit_id": commit_id, "token": token}
    )
    return found is not None


def release_backend_apply_lock(chip_id: str, commit_id: str, token: str | None) -> None:
    """Release the chip's lease if this apply holds it."""
    if not token:
        return
    AgentBackendApplyLockDocument.get_motor_collection().delete_one(
        {"lock_key": apply_lock_key(chip_id), "commit_id": commit_id, "token": token}
    )
