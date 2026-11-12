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

The Quantum Machines tests that load the real `qm-qua` and `qualang-tools` packages are skipped
unless the workflow `qm` extra is installed. The default CI test jobs do not install it; the
`Test QM SDK (Python 3.11)` job in `.github/workflows/backend-ci.yml` installs the locked extra,
fails if the SDK packages cannot be imported, and runs these tests without hardware, network
access, or QM credentials. Run the same commands locally before changing the `qm` or `qm-fake`
backend:

```bash
uv sync --locked --all-groups --all-packages --extra qm
uv run --no-sync pytest tests/qdash/workflow/calibtasks/qm tests/qdash/workflow/engine/backend/test_qm_backend.py \
  tests/qdash/workflow/engine/backend/test_qm_configuration.py -v
```

- `calibtasks/qm/test_qm_fake_device.py` runs the `qm-fake` device against the real packages
  with outgoing sockets blocked. It checks that `run_rabi` executes the program that
  `QUA_calibrations` generates, that amplitudes, shots, elements, streams, and QUA configuration
  changes in a program change the result or fail, that unsupported programs fail, that the fake
  API signatures are subsets of the SDK's, and that a run through `TaskExecutor` records
  labelled artifacts without writing a calibration value.
- `calibtasks/qm/test_qm_rabi_sdk.py` checks the `qm` backend's program generation and its
  hardware and simulator paths with the QOP server replaced by a stub.
- `calibtasks/qm/test_qm_fake.py` runs without the extra: it makes the QM packages unimportable
  and checks the settings, the routing, and that a `qm-fake` run fails with the install command.
- `calibtasks/qm/test_qm_native_config_sdk.py` imports a native `configuration.py` directly
  and through the loader, checks that the SDK accepts both, and runs **QMAmplitudeRabi** on
  `qm-fake` from settings files that point at a configuration with a computed NumPy waveform.
- `engine/backend/test_qm_configuration.py` runs without the extra and checks
  `load_qm_configuration`: the returned `config` keeps tuples, integer keys and arrays, a missing
  or non-dictionary export fails, and helper modules of two chips stay isolated.

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
| `calibtasks/fake/` | `calibtasks/test_fake_backend_sync.py`, `calibtasks/test_fake_bring_up.py` |
| `engine/backend/qm.py`, `engine/backend/qm_configuration.py`, `engine/backend/qm_fake.py`, `calibtasks/qm/` | `engine/backend/test_qm_backend.py`, `engine/backend/test_qm_configuration.py`, `calibtasks/qm/` |

Paths in the table are relative to `src/qdash/workflow/` and `tests/qdash/workflow/`.
