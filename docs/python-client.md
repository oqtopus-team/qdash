# QDash Python Client Guide

QDash provides an auto-generated Python client library for interacting with the QDash API. This client is generated from the OpenAPI specification and provides type-safe access to all API endpoints.

## Features

- 🚀 **Auto-generated from OpenAPI**: Always up-to-date with the latest API
- 🔒 **Type-safe**: Full type hints and runtime validation with attrs
- ⚡ **Async/Sync Support**: Choose between synchronous and asynchronous operations
- 🎯 **Developer-friendly**: Clean API with excellent IDE support
- 📦 **Lightweight**: Minimal dependencies (httpx + attrs)

## Installation

### From GitHub (Recommended)

```bash
# Install client only (lightweight, no server dependencies)
pip install git+https://github.com/oqtopus-team/qdash.git#subdirectory=src/qdash/client

# From specific branch
pip install git+https://github.com/oqtopus-team/qdash.git@develop#subdirectory=src/qdash/client

# From specific tag/release
pip install git+https://github.com/oqtopus-team/qdash.git@v0.1.0#subdirectory=src/qdash/client
```

### Generate from API Server

If you have a running QDash API server and want to regenerate the client:

```bash
# Using the built-in task (recommended)
task generate-python-client

# Or using the script directly
uv run generate-python-client
```

## Quick Start

### Basic Usage

```python
from qdash.client import Client
from qdash.client.api.chip import list_chips, fetch_chip
from qdash.client.api.calibration import execute_calib
from qdash.client.models import ExecuteCalibRequest

# Create a client instance
client = Client(base_url="http://localhost:5715")

# Get all quantum chips
response = list_chips.sync_detailed(client=client)
if response.status_code == 200:
    chips = response.parsed
    for chip in chips:
        print(f"Chip: {chip.name}, ID: {chip.id}")

# Get specific chip details
chip_response = fetch_chip.sync_detailed(client=client, chip_name="sample_chip")
if chip_response.status_code == 200:
    chip_detail = chip_response.parsed
    print(f"Chip {chip_detail.name} has {len(chip_detail.qubits)} qubits")

# Start a calibration
calibration_request = ExecuteCalibRequest(
    chip_name="sample_chip",
    task_details=[]  # Add your task details here
)
result = execute_calib.sync_detailed(client=client, json_body=calibration_request)
if result.status_code == 200:
    print(f"Calibration started: {result.parsed}")
```

### Client Configuration

```python
import httpx
from qdash.client import Client, AuthenticatedClient

# Development environment with custom settings
dev_client = Client(
    base_url="http://localhost:5715",
    timeout=httpx.Timeout(30.0),
    raise_on_unexpected_status=True
)

# Production with authentication
prod_client = AuthenticatedClient(
    base_url="https://qdash.example.com",
    token="your-api-token",
    headers={"X-Username": "your-username"},
    timeout=httpx.Timeout(15.0)
)

# With custom httpx settings
client = Client(
    base_url="http://localhost:5715",
    httpx_args={
        "event_hooks": {
            "request": [lambda req: print(f"Request: {req.method} {req.url}")],
            "response": [lambda res: print(f"Response: {res.status_code}")]
        }
    }
)
```

### Synchronous Usage

```python
from qdash.client import Client
from qdash.client.api.chip import list_chips, fetch_chip
from qdash.client.api.calibration import execute_calib
from qdash.client.models import ExecuteCalibRequest

# Create sync client instance
client = Client(base_url="http://localhost:5715")

# Example: Get chip information
chips_response = list_chips.sync_detailed(client=client)
if chips_response.status_code == 200:
    chips = chips_response.parsed
    print(f"Found {len(chips)} chips")
    for chip in chips:
        print(f"Chip Name: {chip.name}, ID: {chip.id}")

# Example: Get specific chip details
if chips:
    chip_response = fetch_chip.sync_detailed(
        client=client,
        chip_name=chips[0].name
    )
    if chip_response.status_code == 200:
        chip_detail = chip_response.parsed
        print(f"Chip has {len(chip_detail.qubits)} qubits")
        print(f"Couplings: {len(chip_detail.couplings)}")

# Example: Execute calibration
calibration_request = ExecuteCalibRequest(
    chip_name="my-chip",
    task_details=[]
)
result = execute_calib.sync_detailed(client=client, json_body=calibration_request)
if result.status_code == 200:
    print(f"Calibration started: {result.parsed}")
```

### Asynchronous Usage (Recommended for Parallel Operations)

```python
import asyncio
from qdash.client import Client
from qdash.client.api.chip import list_chips, fetch_chip
from qdash.client.api.execution import fetch_execution_lock_status

async def parallel_chip_analysis():
    """Example async workflow for parallel chip analysis."""

    async with Client(base_url="http://localhost:5715") as client:
        # Check system status first
        lock_status = await fetch_execution_lock_status.asyncio_detailed(client=client)
        if lock_status.status_code == 200 and not lock_status.parsed.locked:
            print("System ready for calibration")

        # Get all chips
        chips_response = await list_chips.asyncio_detailed(client=client)
        if chips_response.status_code != 200:
            raise Exception("Failed to fetch chips")

        chips = chips_response.parsed
        print(f"Analyzing {len(chips)} chips in parallel...")

        # Fetch details for multiple chips in parallel
        detail_tasks = [
            fetch_chip.asyncio_detailed(client=client, chip_name=chip.name)
            for chip in chips[:5]  # Limit to first 5
        ]

        # Wait for all tasks to complete
        results = await asyncio.gather(*detail_tasks, return_exceptions=True)

        # Process results
        for chip, result in zip(chips[:5], results):
            if isinstance(result, Exception):
                print(f"Error fetching {chip.name}: {result}")
            elif result.status_code == 200:
                detail = result.parsed
                print(f"{chip.name}: {len(detail.qubits)} qubits, {len(detail.couplings)} couplings")

# Run the async workflow
asyncio.run(parallel_chip_analysis())
```

### Error Handling

```python
from qdash.client import Client
from qdash.client.api.chip import fetch_chip
from qdash.client.errors import UnexpectedStatus

try:
    client = Client(
        base_url="http://localhost:5715",
        raise_on_unexpected_status=True  # Raise exceptions on non-2xx responses
    )

    response = fetch_chip.sync_detailed(client=client, chip_name="nonexistent")

except UnexpectedStatus as e:
    print(f"API Error: {e.status_code} - {e.content}")
except Exception as e:
    print(f"Unexpected error: {e}")
```

## API Reference

### Client Methods

Each API endpoint generates four methods:

1. **`sync`**: Synchronous call returning parsed data or None
2. **`sync_detailed`**: Synchronous call returning Response object with status code
3. **`asyncio`**: Asynchronous call returning parsed data or None
4. **`asyncio_detailed`**: Asynchronous call returning Response object with status code

### Available API Modules

- **`api.chip`**: Chip management and information
- **`api.calibration`**: Calibration workflow execution
- **`api.execution`**: Execution status and locks
- **`api.menu`**: Menu and experiment configuration
- **`api.settings`**: Application settings
- **`api.auth`**: Authentication endpoints
- **`api.parameter`**: Parameter configuration
- **`api.tag`**: Tagging system
- **`api.device_topology`**: Device topology management
- **`api.backend`**: Backend operations
- **`api.file`**: File operations
- **`api.task`**: Task management

### Response Objects

```python
from qdash.client.types import Response

# Response object structure
response = fetch_chip.sync_detailed(client=client, chip_name="chip1")
response.status_code  # HTTP status code
response.content      # Raw response content
response.headers      # Response headers
response.parsed       # Parsed model (if successful)
```

## Working with Models

All request and response models are generated with attrs and provide:

- Full type hints
- Validation
- Serialization/deserialization
- Immutability by default

```python
from qdash.client.models import ChipResponse, ExecuteCalibRequest

# Models are attrs classes
chip = ChipResponse(
    name="quantum_chip_1",
    id="chip_001",
    qubits=[...],
    couplings=[...]
)

# Access attributes
print(chip.name)
print(len(chip.qubits))

# Models are immutable by default
# Use evolve to create modified copies
from attrs import evolve
modified_chip = evolve(chip, name="quantum_chip_2")
```

## Best Practices

1. **Use context managers** for proper resource cleanup:

   ```python
   with Client(base_url="...") as client:
       # Your code here
   ```

2. **Check status codes** before accessing parsed data:

   ```python
   response = api_call.sync_detailed(client=client)
   if response.status_code == 200:
       data = response.parsed
   ```

3. **Use async for parallel operations** to improve performance:

   ```python
   results = await asyncio.gather(*[task1, task2, task3])
   ```

4. **Configure timeouts** for production environments:

   ```python
   client = Client(base_url="...", timeout=httpx.Timeout(10.0))
   ```

5. **Handle errors gracefully** with proper exception handling

## Troubleshooting

### Common Issues

1. **Import errors**: Make sure the client is installed:

   ```bash
   pip install git+https://github.com/oqtopus-team/qdash.git#subdirectory=src/qdash/client
   ```

2. **Connection errors**: Verify the API server is running:

   ```bash
   curl http://localhost:5715/docs
   ```

3. **Type errors**: The client uses strict typing. Check your IDE for type hints.

4. **Outdated client**: Regenerate the client after API changes:
   ```bash
   task generate-python-client
   ```

## Contributing

The client is auto-generated. To modify:

1. Update the API endpoints in `src/qdash/api/`
2. Regenerate the client: `task generate-python-client`
3. Test your changes
4. Submit a pull request

## License

Apache License 2.0 - See [LICENSE](https://github.com/oqtopus-team/qdash/blob/main/LICENSE) for details.
