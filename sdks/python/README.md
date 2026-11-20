# qdash-sdk

`qdash-sdk` provides `qdash.sdk`: the `QDash` session, which validates and starts calibrations
on a chip and lists and runs the workflows registered in a project, and the calibration
definitions, built on
[`qdash-client`](../../clients/python/README.md). Installing it installs the matching
`qdash-client` release:

```bash
pip install qdash-sdk
```

```python
from qdash.sdk import QDash

with QDash.from_env() as qdash:
    # A registered workflow runs code saved in QDash on the chip it was saved for.
    for summary in qdash.workflows.list():
        print(summary.name, summary.chip_id)
    workflow = qdash.workflows.get("coherence_check")
    result = workflow.run(parameters={"qids": ["0", "1"]}).wait()
    print(result.status)
```

`qdash.scripts` and `qdash.dashboards` save metric scripts and custom dashboards; a session works
without `with` too:

```python
from qdash.sdk import Dashboard, QDash, Script

qdash = QDash.from_env()
script = qdash.scripts.create(Script.from_file("zx90_median.py", visibility="project"))
board = Dashboard("ZX90 health", visibility="project")
board.add_metric(script.metric("zx90_median"), period=14)
print(qdash.dashboards.create(board).dashboard_id)
```

The [Python client guide](../../docs/reference/clients/python.md) covers configuration,
`chip.calibrate(targets, steps)`, which runs steps defined in Python on the chip you name,
registered workflows, the pipeline API, and metric scripts and dashboards.

## Develop the Package

Install the workspace and run the SDK checks from the repository root:

```bash
uv sync --all-groups --all-packages
task test-sdk
```

`src/qdash/sdk/` holds the SDK sources; API requests, models, configuration, and errors stay in
`qdash-client`. `tests/test_sdk_distributions.py` builds both wheels and checks that each one
installs only its own namespace.

## Version and Publication

`qdash-sdk` has no version of its own. hatch-vcs derives it the same way as `qdash-client`,
and `hatch_build.py` pins the dependency to that version: a build of `X.Y.Z` or `X.Y.ZbN`
requires `qdash-client==X.Y.Z` or `qdash-client==X.Y.ZbN`. Development builds require any
`qdash-client`.

`.github/workflows/publish-qdash-client.yml` publishes both packages from one release record:
`qdash-client` first, then `qdash-sdk`. See
[Python SDK architecture](../../docs/developer-guide/architecture/python-sdk.md#packaging-and-release).
