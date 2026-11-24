# qdash-sdk

Define and run calibrations, saved workflows, metric scripts, and dashboards from Python.
The SDK includes its Fern-generated API client and does not require `qdash-client`.
Existing `qdash-client` applications can continue using that package independently.

```bash
pip install qdash-sdk
```

Configure `QDASH_BASE_URL`, `QDASH_API_TOKEN`, and `QDASH_PROJECT_ID`, then run a saved workflow:

```python
from qdash.sdk import QDash

qdash = QDash.from_env()
workflow = qdash.workflows.get("coherence_check")
result = workflow.run(parameters={"qids": ["0", "1"]}).wait()
print(result.status)
```

Reuse `qdash` across notebook cells or script operations. Call `qdash.close()` when you finish
using the connection.

This starts hardware work. Choose an existing workflow and targets suitable for your deployment.
See the [Python reference](../../docs/reference/clients/python.md) for TOML profiles and other operations.
SDK reads of existing INI profiles remain supported with a deprecation warning.

## Development

From the repository root:

```bash
uv sync --all-groups --all-packages
task test-sdk
```

Sources are in `src/qdash/sdk/`; generated code lives in `_generated/`.
Regenerate with `task generate-python-sdk` (requires Node.js and Docker).
See [generation and packaging](../../docs/developer-guide/architecture/python-sdk.md).
