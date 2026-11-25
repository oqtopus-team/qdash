# qdash-sdk

Define and run calibrations, saved workflows, metric scripts, and dashboards from Python.
The SDK includes its Fern-generated API client and does not require `qdash-client`.
Existing `qdash-client` applications can continue using that package independently.

```bash
pip install qdash-sdk
qdash config init --project-id your-project-id
```

Fill in `api_token` in the generated file. Use `--base-url` when initializing for a remote
deployment. `QDash()` reads the default profile; then run a saved workflow:

```python
from qdash.sdk import QDash

qdash = QDash()
workflow = qdash.workflows.get("coherence_check")
result = workflow.run(parameters={"qids": ["0", "1"]}).wait()
print(result.status)
```

Reuse `qdash` across notebook cells or script operations. Call `qdash.close()` when you finish
using the connection. To select a profile explicitly, use `QDash.from_profile("local")`.
Use `QDash.from_env()` for environment-based configuration.

Keep the handle from `workflow.run()` to request cancellation with `run.cancel()`;
`run.wait()` then confirms the workflow's terminal state.

This starts hardware work. Choose an existing workflow and targets suitable for your deployment.
See the [Python reference](../../docs/reference/clients/python.md) for TOML profiles and other operations.
SDK reads of existing INI profiles remain supported with a deprecation warning.

## Examples

With the `local` TOML profile configured above, open:

1. [Read a project](examples/01_read_project.ipynb)
2. [Run a registered workflow](examples/02_registered_workflow.ipynb)
3. [Run a calibration](examples/03_calibration.ipynb)
4. [Run a task and inspect results](examples/04_task_workbench.ipynb)
5. [Investigate results](examples/05_investigate_results.ipynb)
6. [Export device gateway files](examples/06_device_gateway.ipynb)

The investigation example uses optional `pandas` for tables. Install it in your notebook
environment. Table operations apply
to the loaded page; use SDK filters to search history.

The **Run Calibration**, **Run Task**, and **Run Workflow** cells start measurements when executed.
To use this checkout, run
`pip install -e sdks/python` from the repository root in your notebook environment.

To check the installed SDK version:

```python
from qdash.sdk import version

print(version())
```

## Development

From the repository root:

```bash
uv sync --all-groups --all-packages
task test-sdk
```

Sources are in `src/qdash/sdk/`; generated code lives in `_generated/`.
Regenerate with `task generate-python-sdk` (requires Node.js and Docker).
See [generation and packaging](../../docs/developer-guide/architecture/python-sdk.md).
