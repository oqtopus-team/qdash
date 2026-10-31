# Workflow Testing

Workflow tests mirror the runtime layers under `src/qdash/workflow/` and run without laboratory
hardware by using fake backends, in-memory repositories, and focused mocks.

## Choose the Test Scope

| Change | Test location |
| --- | --- |
| Calibration task implementation | `tests/qdash/workflow/calibtasks/` |
| Backend, execution, scheduler, task, or repository behavior | `tests/qdash/workflow/engine/` |
| Pipeline steps, session context, or service orchestration | `tests/qdash/workflow/service/` |
| Prefect deployment or worker integration | `tests/qdash/workflow/test_*.py`, `tests/qdash/workflow/worker/` |
| Reusable workflow template | Matching `tests/qdash/workflow/test_*_template.py` file |

Place a test beside the layer that owns the behavior. Add a broader service or template test only
when the change crosses layer boundaries.

## Run the Tests

Run the complete workflow suite from the repository root:

```bash
task test-workflow
```

Use pytest directly for a focused loop:

```bash
uv run pytest tests/qdash/workflow/engine/scheduler/test_cr_scheduler.py -v
uv run pytest tests/qdash/workflow/service/test_pipeline_flow.py -v -k cancellation
```

Run `task test` when the change also affects shared models, repositories, or API behavior.

## Follow Existing Fixtures

Search the nearest test module and parent `conftest.py` before adding a fixture. Prefer the
repository's fake backend and in-memory repository implementations to database mocks. Patch the
symbol where the code under test imports it, and configure every property that the tested path
reads.

Use `tmp_path` for files and reset context, environment, and patched globals after each test.
Tests that exercise Prefect hooks or async services must wait for observable completion instead
of using fixed sleeps.

## Cover Runtime Invariants

Test the invariant owned by the changed component:

- task and execution state transitions, including failure and cancellation;
- scheduler grouping, ordering, and conflict constraints;
- parameter resolution, snapshots, accepted output, and backend updates;
- result, figure, raw-data, provenance, and history persistence;
- execution-lock acquisition and release;
- service cleanup when a flow crashes or is cancelled.

Use descriptive names that state the action and expected result, such as
`test_cancel_releases_execution_lock`. Keep one behavior per test and assert externally visible
state instead of private call order unless call order is the contract.

## Implementation and Test Map

| Implementation | Primary tests |
| --- | --- |
| `engine/orchestrator.py` | `engine/test_orchestrator_*.py` |
| `engine/task/` | `engine/task/` |
| `engine/execution/` | `engine/execution/` |
| `engine/scheduler/` | `engine/scheduler/` |
| `engine/repository/` | `engine/repository/` |
| `service/` | `service/` |
| `templates/` | Top-level `test_*_template.py` files |

Paths in the table are relative to `src/qdash/workflow/` and `tests/qdash/workflow/`.
