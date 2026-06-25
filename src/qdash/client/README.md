# qdash.client README

`qdash.client` is a Python client for calling the QDash API.

- `services`: domain logic such as authentication, retries, and response normalization
- `rest`: low-level HTTP communication

This package follows the same approach as `oqtopus-client`, separating the transport layer from the service layer.
For user-facing examples, see `docs/user-guide/qdash-client.md`.

## Installation

Install the lightweight client package when only programmatic API access is needed.

```bash
pip install qdash-client
```

For development against this repository:

```bash
pip install ./src/qdash/client
```

The distribution name is `qdash-client`, but the Python import path is `qdash.client`.

## Publishing

`qdash-client` is published from this repository with PyPI Trusted Publishing. Configure the
`qdash-client` project on PyPI to trust this GitHub repository and the
`.github/workflows/publish-qdash-client.yml` workflow.

Release tags use the `qdash-client-v<version>` format. Do not edit a package version in
`pyproject.toml`; the package version is derived from the matching Git tag at build time.

```bash
git tag qdash-client-v<version>
git push origin qdash-client-v<version>
```

## Minimal Quick Start

This is a minimal example using `/chips`, `/metrics/config`, and `/task-results/timeseries`.

```python
from qdash.client import QDashClient

client = QDashClient()
try:
    chips = client.list_chips()
    print(chips.total)
    print([chip.chip_id for chip in chips.chips])

    metrics_config = client.get_metrics_config()
    print(metrics_config.keys())

    series = client.get_task_results_timeseries(
        chip_id="chip-001",
        parameter="t1",
        start_at="2026-06-01T00:00:00Z",
        end_at="2026-06-02T00:00:00Z",
    )
    print(series.data)
finally:
    client.close()
```

## 1. Public API

In most cases, you will use the following:

- `QDashClient`
- `QDashConfig`
- Exception classes such as `QDashApiError`

```python
from qdash.client import QDashClient, QDashConfig
```

## 2. Configuration

### 2.1 From Environment Variables

```python
from qdash.client import QDashClient

client = QDashClient.from_env()
```

Main environment variables:

- `QDASH_BASE_URL`
- `QDASH_API_TOKEN`
- `QDASH_PROJECT_ID`
- `QDASH_CF_ACCESS_CLIENT_ID`
- `QDASH_CF_ACCESS_CLIENT_SECRET`
- `QDASH_TIMEOUT_SECONDS`
- `QDASH_RETRY_MAX_ATTEMPTS`
- `QDASH_RETRY_BACKOFF_SECONDS`
- `QDASH_RETRY_MAX_BACKOFF_SECONDS`
- `QDASH_VERIFY_TLS`
- `QDASH_PROXY`
- `QDASH_USER_AGENT`

For legacy username/password authentication, set:

- `QDASH_USERNAME`
- `QDASH_PASSWORD_ENV`
- the environment variable named by `QDASH_PASSWORD_ENV` (defaults to `QDASH_PASSWORD`)

### 2.2 From a Configuration File

```python
from qdash.client import QDashClient

client = QDashClient.from_profile("default")
```

If `path` is omitted:

1. If `XDG_CONFIG_HOME` is set: `$XDG_CONFIG_HOME/qdash/config.ini`
2. Otherwise: `~/.config/qdash/config.ini`

Example configuration:

```ini
[default]
base_url = https://example.qdash/api
api_token = your-token
project_id = your-project-id
cf_access_client_id = your-cf-client-id
cf_access_client_secret = your-cf-client-secret
timeout_seconds = 30
retry_max_attempts = 3
retry_backoff_seconds = 0.2
retry_max_backoff_seconds = 5.0
```

For legacy username/password authentication from a config file, use `username` and `password_env`
instead of `api_token`.

Save a profile to `config.ini`:

```python
from qdash.client import QDashConfig

config = QDashConfig(
    base_url="https://example.qdash/api",
    api_token="your-token",
    cf_access_client_id="your-cf-client-id",
    cf_access_client_secret="your-cf-client-secret",
)
config.save(profile="prod")
```

The saved file is created with owner-only permissions (`0600`) because it can contain API tokens
and Cloudflare Access secrets.

### 2.3 Automatic Loading

```python
from qdash.client import QDashClient

# Loads config.ini by default
client = QDashClient()
```

## 3. Usage (Synchronous API)

### 3.1 List Chips

```python
from qdash.client import QDashClient

client = QDashClient()
try:
    chips = client.list_chips()
    print([chip.chip_id for chip in chips.chips])
finally:
    client.close()
```

### 3.2 Default Chip

`get_default_chip()` returns the most recently installed active chip. If no chips are active, it
falls back to the most recently installed chip returned by the API.

```python
from qdash.client import QDashClient

client = QDashClient()
try:
    chip = client.get_default_chip()
    print(chip.chip_id)
finally:
    client.close()
```

Use `get_default_chip_id()` when an API call only needs the chip ID.

### 3.3 Time-Series Metrics

```python
from qdash.client import QDashClient

client = QDashClient()
try:
    chip_id = client.get_default_chip_id()
    series = client.get_task_results_timeseries(
        chip_id=chip_id,
        parameter="t1",
        tag="calibration",
        start_at="2026-06-01T00:00:00Z",
        end_at="2026-06-08T00:00:00Z",
        qid="Q00",
    )
    print(series.data)
finally:
    client.close()
```

### 3.4 Agent-Friendly Read-Only Queries

The client exposes common read-only endpoints used by QDash agents and scripts:

```python
from qdash.client import QDashClient

client = QDashClient.from_profile("local")
try:
    chip_id = client.get_default_chip_id()

    task_results = client.list_task_results(chip_id=chip_id, status="success", limit=20)
    latest_t1 = client.get_qubit_latest_task_results(chip_id=chip_id, task="t1")
    q00_history = client.get_qubit_task_history(
        chip_id=chip_id,
        qid="Q00",
        task="t1",
        date="20260625",
    )

    projects = client.list_projects()
    file_tree = client.get_files_tree()
    git_status = client.get_git_status()
    issues = client.list_issues(limit=20)
    knowledge = client.list_issue_knowledge(status="approved", limit=20)
    flows = client.list_flows()
    executions = client.list_executions(chip_id=chip_id, limit=20)
    provenance = client.get_provenance_stats()

    print(task_results.total, latest_t1.task_name, q00_history.name)
    print(projects.total, len(file_tree), git_status, len(issues.issues))
    print(len(knowledge.items), len(flows.flows), len(executions.executions))
    print(provenance.total_entities)
finally:
    client.close()
```

Available read-only helpers include:

- Task results: `list_task_results()`, `get_qubit_latest_task_results()`,
  `get_qubit_task_history()`, `get_coupling_latest_task_results()`,
  `get_coupling_task_history()`
- Projects and files: `list_projects()`, `get_project()`, `get_files_tree()`,
  `get_git_status()`
- Issues and knowledge: `list_issues()`, `get_issue()`, `list_issue_knowledge()`,
  `get_issue_knowledge()`
- Flows and executions: `list_flows()`, `get_flow()`, `list_executions()`,
  `get_execution()`
- Provenance: `get_provenance_entity()`, `get_provenance_lineage()`,
  `get_provenance_impact()`, `get_provenance_history()`, `get_provenance_stats()`,
  `get_provenance_changes()`

### 3.5 Metrics Configuration

```python
from qdash.client import QDashClient

client = QDashClient()
try:
    config = client.get_metrics_config()
    print(config.get("qubit_metrics", {}).keys())
    print(config.get("coupling_metrics", {}).keys())
finally:
    client.close()
```

## 4. Usage (Asynchronous API)

```python
import asyncio
from qdash.client import QDashClient

async def main() -> None:
    client = QDashClient()
    try:
        chips = await client.list_chips_async()
        print([chip.chip_id for chip in chips.chips])

        metrics_config = await client.get_metrics_config_async()
        print(metrics_config.get("qubit_metrics", {}).keys())

        series = await client.get_task_results_timeseries_async(
            chip_id="chip-001",
            parameter="t1",
            start_at="2026-06-01T00:00:00Z",
            end_at="2026-06-02T00:00:00Z",
        )
        print(series.data)
    finally:
        client.close()

asyncio.run(main())
```

## 5. Error Handling

Main exceptions:

- `QDashApiError` (base class)
- `QDashAuthError` (missing or invalid authentication)
- `QDashNotFoundError` (404)
- `QDashValidationError` (422)
- `QDashTransportError` (transport errors, timeouts, or other HTTP statuses)

```python
from qdash.client import QDashClient, QDashApiError

client = QDashClient()
try:
    print(client.list_chips().chips)
except QDashApiError as exc:
    print(exc.status_code, exc)
finally:
    client.close()
```

## 6. Exporter Helper Functionality

`QDashClient` provides helper methods for exporters.

- `normalize_chip_metrics(chip_id, payload)`

This method converts a QDash API response into a list of
`NormalizedMetricRecord` objects that are easier for exporters to consume.

## 7. Using the Low-Level REST Client Directly

In most cases, using `QDashClient` is recommended.

If you need direct access to the low-level API, you can use `qdash.client.rest`.

```python
from qdash.client.rest import ApiClient, Configuration

cfg = Configuration(host="https://example.qdash/api")
rest_client = ApiClient(cfg)

try:
    resp = rest_client.request("GET", "/chips")
    print(resp.status_code, resp.data)
finally:
    rest_client.close()
```
