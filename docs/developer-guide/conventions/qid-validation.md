# QID Validation

Qubit/coupling identifier (`qid`) fields across all DB models are plain `str` with no validation. This has caused data pollution incidents where invalid qid formats were written to MongoDB.

## Problem

The seed import pipeline once wrote coupling-format qids (`"0-1"`) and zero-padded qids (`"000"`) into `QubitDocument`. These invalid records caused silent data corruption: queries returned wrong results, and the copilot agent's `int(qid)` conversions failed.

### Affected Models

| Model | Expected qid Format | Current Validation |
|-------|---------------------|--------------------|
| QubitDocument | `^\d+$` (e.g. `"0"`, `"143"`) | None |
| CouplingDocument | `^\d+-\d+$` (e.g. `"0-1"`) | None |
| QubitHistoryDocument | `^\d+$` | None |
| CouplingHistoryDocument | `^\d+-\d+$` | None |
| TaskResultHistoryDocument | `^\d+$` or `^\d+-\d+$` | None |
| ParameterVersionDocument | `^\d+$` or `^\d+-\d+$` | None |
| ActivityDocument | `^\d+$` or `^\d+-\d+$` | None |

### Pollution Patterns Found

**Coupling qids in QubitDocument** -- Coupling parameter YAML files were saved as QubitDocuments. Filter: `{"qid": {"$regex": "-"}}`.

**Zero-padded duplicates** -- Seed import normalized `"Q000"` to `"000"` instead of `"0"`. Filter: `{"qid": {"$regex": "^0\\d+$"}}`.

## Plan

### Prerequisites

Run the existing migration **before** adding validators. Bunnet deserializes MongoDB documents through Pydantic, so `find()` on polluted data raises `ValidationError` if a validator rejects the stored value. The migration itself uses `find()` and would break.

```bash
python -m qdash.dbmodel.migration remove-coupling-from-qubit          # dry-run
python -m qdash.dbmodel.migration remove-coupling-from-qubit --execute
```

See `src/qdash/dbmodel/migration.py` (`migrate_remove_coupling_from_qubit`) for details.

### Step 1: Add Pydantic Field Validators

Add `field_validator("qid")` to each Document class. Qubit models accept numeric-only strings; coupling models accept hyphen-separated pairs; mixed models accept both.

```python
# QubitDocument, QubitHistoryDocument
import re
from pydantic import field_validator

_QUBIT_QID_RE = re.compile(r"^\d+$")

@field_validator("qid")
@classmethod
def validate_qid(cls, v: str) -> str:
    if not _QUBIT_QID_RE.match(v):
        raise ValueError(f"Invalid qubit qid: {v!r} (expected numeric string)")
    if len(v) > 1 and v.startswith("0"):
        raise ValueError(f"Zero-padded qubit qid: {v!r}")
    return v
```

```python
# CouplingDocument, CouplingHistoryDocument
_COUPLING_QID_RE = re.compile(r"^\d+-\d+$")

@field_validator("qid")
@classmethod
def validate_qid(cls, v: str) -> str:
    if not _COUPLING_QID_RE.match(v):
        raise ValueError(f"Invalid coupling qid: {v!r} (expected N-M format)")
    return v
```

```python
# TaskResultHistoryDocument, ParameterVersionDocument, ActivityDocument
_ANY_QID_RE = re.compile(r"^\d+(-\d+)?$")

@field_validator("qid")
@classmethod
def validate_qid(cls, v: str) -> str:
    if v == "":
        return v  # these models allow empty qid as default
    if not _ANY_QID_RE.match(v):
        raise ValueError(f"Invalid qid: {v!r} (expected numeric or N-M format)")
    return v
```

### Step 2: Add MongoDB Schema Validation (Optional)

MongoDB supports JSON Schema validation at the collection level. This provides a second layer of defense independent of the application.

```javascript
db.runCommand({
  collMod: "qubit",
  validator: {
    $jsonSchema: {
      properties: {
        qid: { bsonType: "string", pattern: "^\\d+$" }
      }
    }
  },
  validationAction: "error"
})
```

This catches writes from any client (migration scripts, manual fixes, other services), not just the API.

## Implementation Files

| File | Change |
|------|--------|
| `src/qdash/dbmodel/qubit.py` | Add `validate_qid` to QubitDocument |
| `src/qdash/dbmodel/coupling.py` | Add `validate_qid` to CouplingDocument |
| `src/qdash/dbmodel/qubit_history.py` | Add `validate_qid` to QubitHistoryDocument |
| `src/qdash/dbmodel/coupling_history.py` | Add `validate_qid` to CouplingHistoryDocument |
| `src/qdash/dbmodel/task_result_history.py` | Add `validate_qid` to TaskResultHistoryDocument |
| `src/qdash/dbmodel/provenance.py` | Add `validate_qid` to ParameterVersionDocument, ActivityDocument |
| `tests/qdash/dbmodel/test_qid_validation.py` | Unit tests for valid/invalid qid patterns |
