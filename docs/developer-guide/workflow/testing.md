# Workflow Testing

Workflow tests use fake backends, in-memory repositories, and mocks instead of laboratory hardware.

## Choose the Test Scope

| Change | Tests under `tests/qdash/workflow/` |
| --- | --- |
| Calibration task | `calibtasks/` |
| Backend, executor, scheduler | `engine/` |
| Pipeline, session, service | `service/` |
| Deployment and workers | Top-level tests and `worker/` |
| Template | Matching `test_*_template.py` |

## Run the Tests

```bash
uv run pytest tests/qdash/workflow/engine/scheduler/test_cr_scheduler.py -v
task test-workflow
```

Run `task test` when shared models, repositories, or API behavior also change.

## Follow Existing Fixtures

Reuse the nearest fixtures and in-memory implementations. Patch where the tested module imports
a dependency, use `tmp_path` for files, and reset context and globals. Wait for observable async
completion rather than sleeping.

## Cover Runtime Invariants

Test the changed boundary's observable behavior: state transitions, hardware conflicts, parameter
resolution, snapshot matching, publication, artifacts, and cleanup. Failure and cancellation
must release owned reservations and finalize records. Template tests check target precedence,
step/task order, and settings without launching hardware.
