# QDash Client

`qdash.client` is a Python client for reading QDash data from scripts, notebooks, and external automation.

## Installation

Install the lightweight client package when only programmatic API access is needed.

```bash
pip install qdash-client
```

For development against this repository, install it from the workspace path.

```bash
pip install ./src/qdash/client
```

The distribution name is `qdash-client`, but the Python import path is `qdash.client`.

```python
from qdash.client import QDashClient
```

## Configuration

Use an API token for programmatic access. The client reads configuration from environment variables or from `config.ini`.

```bash
export QDASH_BASE_URL="https://your-qdash-instance"
export QDASH_API_TOKEN="your-api-token"
export QDASH_PROJECT_ID="your-project-id"
```

If QDash is behind Cloudflare Access, also set:

```bash
export QDASH_CF_ACCESS_CLIENT_ID="your-client-id"
export QDASH_CF_ACCESS_CLIENT_SECRET="your-client-secret"
```

The same configuration can be stored in `$XDG_CONFIG_HOME/qdash/config.ini`, or in `~/.config/qdash/config.ini` when `XDG_CONFIG_HOME` is not set.

```ini
[default]
base_url = https://your-qdash-instance
api_token = your-api-token
project_id = your-project-id
cf_access_client_id = your-client-id
cf_access_client_secret = your-client-secret
timeout_seconds = 30
retry_max_attempts = 3
retry_backoff_seconds = 0.2
retry_max_backoff_seconds = 5.0
```

Use sections as profiles for different environments, and save a profile from Python when needed.

```python
from qdash.client import QDashConfig

config = QDashConfig(
    base_url="https://your-qdash-instance/api",
    api_token="your-api-token",
    cf_access_client_id="your-client-id",
    cf_access_client_secret="your-client-secret",
)
config.save(section="prod")
```

Saved config files use owner-only permissions (`0600`) because they can contain API tokens and
Cloudflare Access secrets.

## Basic Usage

Create a client, call the API, and close the HTTP session when the script exits.

```python
from qdash.client import QDashClient

client = QDashClient()
try:
    chips = client.list_chips()

    for chip in chips.chips:
        print(chip.chip_id, chip.activity_status)
finally:
    client.close()
```

Use `QDashConfig.from_env()` when a script should fail early if required environment variables are missing.

```python
from qdash.client import QDashClient, QDashConfig

config = QDashConfig.from_env()
client = QDashClient(config)
```

## Metrics Configuration

`get_metrics_config()` returns the metric metadata used by the QDash dashboard, including display labels and color scale settings.

```python
from qdash.client import QDashClient

client = QDashClient()
try:
    metrics_config = client.get_metrics_config()

    qubit_metrics = metrics_config.get("qubit_metrics", {})
    coupling_metrics = metrics_config.get("coupling_metrics", {})

    print("Qubit metrics:", sorted(qubit_metrics))
    print("Coupling metrics:", sorted(coupling_metrics))
finally:
    client.close()
```

## Time-Series Data

Use `get_task_results_timeseries()` to read calibrated parameter values for a chip and time range.

```python
from qdash.client import QDashClient

client = QDashClient()
try:
    series = client.get_task_results_timeseries(
        chip_id="chip-001",
        parameter="t1",
        tag="calibration",
        qid="Q00",
        start_at="2026-06-01T00:00:00Z",
        end_at="2026-06-08T00:00:00Z",
    )

    for qid, points in series.data.items():
        for point in points:
            print(qid, point.parameter_name, point.value, point.calibrated_at)
finally:
    client.close()
```

## Async Usage

The client also exposes async variants for read operations.

```python
import asyncio

from qdash.client import QDashClient, QDashConfig


async def main() -> None:
    config = QDashConfig.from_env()
    client = QDashClient(config)
    try:
        chips = await client.list_chips_async()
        print([chip.chip_id for chip in chips.chips])

        series = await client.get_task_results_timeseries_async(
            chip_id="chip-001",
            parameter="t1",
            start_at="2026-06-01T00:00:00Z",
            end_at="2026-06-08T00:00:00Z",
        )
        print(series.data)
    finally:
        client.close()


asyncio.run(main())
```

## Error Handling

All client API failures inherit from `QDashApiError`. Invalid request parameters raise `QDashValidationError`, missing resources raise `QDashNotFoundError`, and network or unexpected HTTP failures raise `QDashTransportError`.

```python
from qdash.client import QDashApiError, QDashClient

client = QDashClient()
try:
    chips = client.list_chips()
    print(chips.total)
except QDashApiError as exc:
    print(exc.status_code, exc)
finally:
    client.close()
```
