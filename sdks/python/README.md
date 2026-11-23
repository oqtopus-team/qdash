# qdash-sdk

Define and run calibrations, saved workflows, metric scripts, and dashboards from Python.
The SDK installs the matching `qdash-client` version.

```bash
pip install qdash-sdk
```

Configure `QDASH_BASE_URL`, `QDASH_API_TOKEN`, and `QDASH_PROJECT_ID`, then run a saved workflow:

```python
from qdash.sdk import QDash

with QDash.from_env() as qdash:
    workflow = qdash.workflows.get("coherence_check")
    result = workflow.run(parameters={"qids": ["0", "1"]}).wait()
    print(result.status)
```

This starts hardware work. Choose an existing workflow and targets suitable for your deployment.
See the [Python reference](../../docs/reference/clients/python.md) for configuration and other operations.

## Development

From the repository root:

```bash
uv sync --all-groups --all-packages
task test-sdk
```

Sources are in `src/qdash/sdk/`; transport and API models stay in `qdash-client`.
Both packages share QDash's version; see [packaging](../../docs/developer-guide/architecture/python-sdk.md#packaging-and-release).
