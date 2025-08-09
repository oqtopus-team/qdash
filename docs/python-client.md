# QDash Python Client

QDash Python client is automatically generated from the OpenAPI specification using `openapi-python-client` (1.6k⭐), providing full async/await support, attrs models, httpx integration, and type safety for quantum calibration workflows.

## Prerequisites

- QDash API server must be running
- Python 3.10 or higher

## Features

✨ **Modern Python Stack:**
- 🔥 **httpx** for async HTTP client with HTTP/2 support
- 🎯 **Pydantic v2** models with runtime validation
- ⚡ **Native async/await** support throughout
- 🛡️ **Full type hints** for IDE support and static analysis
- 🔄 **Both sync and async** client variants
- 🎨 **Clean generated code** following modern Python practices

## Installation

### Option 1: Dedicated Client Package (Recommended)

⚠️ **QDash Python client has moved to a separate lightweight package!**

```bash
# Install QDash Python client (lightweight, ~5MB)
pip install qdash-client

# Generate client code (requires running QDash API server)  
qdash-generate-client --api-url http://localhost:5715
```

### Option 2: Legacy Installation (Deprecated)

The old method still works but includes unnecessary platform dependencies:

```bash
# ⚠️ Deprecated: Installs heavy platform dependencies (~200MB)
pip install "git+https://github.com/oqtopus-team/qdash.git[client]"
generate-python-client
```

### Option 2: Development Installation

For development, install all dependencies:

```bash
# Clone and install in development mode
git clone https://github.com/oqtopus-team/qdash.git
cd qdash
uv sync --group dev
```

## Generate Modern Python Client

### Using Task (Recommended)

```bash
# Make sure QDash API is running first
task generate-python-client
```

### Using Script Directly

```bash
# Make sure QDash API is running first
uv run generate-python-client
```

This will:
1. Fetch the OpenAPI spec from the running QDash API server
2. Generate a Python client using `openapi-python-client`
3. Create both sync and async client variants with attrs models and httpx
4. Integrate the client into `src/qdash/client/` for clean imports

## Usage

After generating the client, you can use it with full error handling and retry logic:

### Environment Configuration

Different environments require different configurations:

```python
import os
from qdash.client import Client, AuthenticatedClient

# Development
dev_client = Client(
    base_url="http://localhost:5715",
    timeout=30.0,
    raise_on_unexpected_status=True
)

# Production
prod_client = AuthenticatedClient(
    base_url=os.getenv("QDASH_API_URL", "https://qdash.example.com"),
    token=os.getenv("QDASH_API_TOKEN"),
    headers={"X-Username": os.getenv("QDASH_USERNAME")},
    timeout=15.0
)
```

### Synchronous Usage

```python
# Clean integrated imports - much better!
from qdash.client import Client, AuthenticatedClient
from qdash.client.api.chip import list_chips, fetch_chip
from qdash.client.api.calibration import execute_calib
from qdash.client.models import ExecuteCalibRequest

# Alternative: Import directly from qdash (when installed)
# from qdash import Client, AuthenticatedClient

# Create sync client instance
client = Client(base_url="http://localhost:5715")

# Example: Get chip information with attrs models
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

# Example: Execute calibration with type safety
calibration_request = ExecuteCalibRequest(
    # Request fields based on the actual API schema
    chip_name="my-chip",
    task_details=[
        # Task details based on schema
    ]
)
result = execute_calib.sync_detailed(client=client, json_body=calibration_request)
if result.status_code == 200:
    print(f"Calibration started: {result.parsed}")
```

### Asynchronous Usage (Recommended for Quantum Workflows)

```python
import asyncio
from qdash_client import AsyncApiClient

async def quantum_calibration_workflow():
    """Example async workflow for quantum calibration."""
    
    async with AsyncApiClient(base_url="http://localhost:5715") as client:
        # Parallel operations for efficiency
        chips, history = await asyncio.gather(
            client.chip_get_chips_get(),
            client.calibration_get_calibration_history_get(limit=5)
        )
        
        print(f"Managing {len(chips)} chips with {len(history.items)} recent calibrations")
        
        # Start multiple calibrations concurrently
        calibration_tasks = []
        for chip in chips[:3]:  # Limit to first 3 chips
            calibration_request = {
                "chip_id": chip.id,
                "experiment_type": "t1_measurement", 
                "parameters": {"measurement_count": 1000}
            }
            task = client.calibration_start_calibration_post(json_body=calibration_request)
            calibration_tasks.append(task)
        
        # Wait for all calibrations to start
        calibration_results = await asyncio.gather(*calibration_tasks)
        
        # Monitor calibration progress
        for result in calibration_results:
            print(f"Started calibration {result.id} for chip {result.chip_id}")
            
            # Poll for completion using the status endpoint
            while True:
                status = await client.calibration_get_calibration_status_get(
                    calibration_id=result.id
                )
                print(f"Calibration {result.id}: {status.status} ({status.progress}%)")
                
                if status.status in ["completed", "failed", "cancelled"]:
                    break
                    
                await asyncio.sleep(1)

# Run the async workflow
asyncio.run(quantum_calibration_workflow())
```

### Advanced Usage with Context Management

```python
from qdash_client import AsyncQDashClient
from qdash_client.exceptions import QDashAPIError

async def robust_calibration():
    """Example with proper error handling and resource management."""
    
    try:
        async with AsyncQDashClient(
            base_url="http://localhost:5715",
            timeout=30.0,  # Custom timeout
            headers={"X-Username": "quantum-operator"}  # Custom headers
        ) as client:
            
            # Type-safe parameter access
            chip = await client.get_chip("my-chip-id")
            current_frequency = chip.parameters.qubit_frequency
            
            # Update with Pydantic validation
            updated_params = chip.parameters.model_copy(
                update={"qubit_frequency": current_frequency + 1e6}
            )
            
            await client.update_chip_parameters("my-chip-id", updated_params)
            
    except QDashAPIError as e:
        print(f"API Error: {e.status_code} - {e.message}")
        if e.details:
            print(f"Details: {e.details}")
    except Exception as e:
        print(f"Unexpected error: {e}")
```

## Configuration

The client generation can be configured via environment variables:

- `API_PORT`: QDash API port (default: 5715)
- `API_HOST`: QDash API host (default: localhost)
- `CLIENT_NAME`: Generated client class name (default: QDashClient)
- `PACKAGE_NAME`: Generated package name (default: qdash_client)
- `HTTP_CLIENT`: HTTP library to use (httpx, requests, aiohttp - default: httpx)
- `CLIENT_OUTPUT_DIR`: Custom output directory

Example with custom configuration:
```bash
export API_PORT=8080
export CLIENT_NAME=MyQuantumClient
export HTTP_CLIENT=httpx
task generate-python-client
```

## Quantum Computing Optimizations

The modern client is specifically optimized for quantum calibration workflows:

### 1. **Concurrent Calibrations**
```python
# Run multiple calibrations in parallel
async def parallel_calibrations(chip_ids: list[str]):
    async with AsyncQDashClient() as client:
        tasks = [
            client.start_calibration(chip_id, experiment_type="rabi")
            for chip_id in chip_ids
        ]
        return await asyncio.gather(*tasks)
```

### 2. **Real-time Monitoring**
```python
# Stream calibration progress with async generators
async def monitor_calibration(calibration_id: str):
    async with AsyncQDashClient() as client:
        async for update in client.stream_calibration_progress(calibration_id):
            yield update.progress, update.current_step
            if update.status == "completed":
                break
```

### 3. **Type-Safe Parameter Management**
```python
# Pydantic ensures parameter validation
from qdash_client.models import RabiParameters

rabi_params = RabiParameters(
    frequency_start=5.0e9,  # Validated range
    frequency_stop=5.5e9,
    amplitude_start=0.01,
    amplitude_stop=0.1,
    num_points=100
)
# Type error if invalid parameters!
```

## Regenerating the Client

When the QDash API changes, regenerate the client:

```bash
task generate-python-client
```

The `--overwrite` flag is used by default to replace the existing client.

## Testing & Integration

### Integration Tests

Client integration tests verify functionality across different scenarios:

```bash
# Run all tests including client tests
pytest tests/ -v

# Run only client integration tests
pytest tests/test_client_integration.py -v

# Run integration tests (requires running API server)
pytest tests/test_client_integration.py -m integration -v
```

### Error Recovery & Retry Logic

The client examples include robust error recovery patterns with exponential backoff and proper exception handling.

### CI Pipeline Integration

- Generated code in `src/qdash/client/` excluded from linting/formatting
- Dependencies pinned for stability (`httpx>=0.27.0,<0.28.0`, `attrs>=23.1.0,<25.0.0`)
- Integration tests verify functionality across environments

## Examples

Comprehensive examples are available:
- [`examples/qdash_client_example.py`](../examples/qdash_client_example.py) - Sync/async usage with error handling
- [`examples/python_client_examples.py`](../examples/python_client_examples.py) - Advanced quantum workflows
- [`examples/client_configurations.py`](../examples/client_configurations.py) - Environment-specific configurations
- [`tests/test_client_integration.py`](../tests/test_client_integration.py) - Integration test patterns

## Development

The client generation script is located at:
- `src/qdash/scripts/generate_client.py`

Key features:
- **Configuration management** with dataclasses
- **Robust error handling** with retries and validation  
- **Health checks** before generation
- **Dependency version pinning**
- **Environment-aware configurations**
- **Comprehensive test coverage**

## Performance

The modern client provides significant performance improvements:

- **HTTP/2 support** via httpx for multiplexing
- **Connection pooling** for reduced latency
- **Async I/O** prevents blocking during long calibrations
- **Pydantic v2** with Rust-based validation for speed
- **Type hints** enable optimizations in Python 3.11+

## Troubleshooting

### "openapi-python-generator not found" error
Install the modern generator:
```bash
uv sync --group dev  # or pip install openapi-python-generator
```

### "Connection refused" error
Make sure the QDash API server is running:
```bash
uvicorn src.qdash.api.main:app --reload --port 5715
```

### Import errors after generation
Install the generated client:
```bash
pip install -e ./qdash_client
```

### Pydantic validation errors
The modern client provides detailed validation errors:
```python
try:
    client.create_calibration(invalid_data)
except ValidationError as e:
    print("Validation failed:", e.errors())
```

### Type checking with mypy
The generated client has full type coverage:
```bash
mypy your_quantum_script.py  # Should pass without errors
```

## Migration from Legacy Client

If migrating from the old `openapi-python-client` generated client:

### Before (Legacy)
```python
from qdash_client.api.chip import get_chips
response = get_chips.sync_detailed(client=client)
chips = response.parsed
```

### After (Modern)
```python
# Much cleaner!
chips = client.get_chips()  # Direct return, full typing
```

The modern client eliminates the need for:
- Manual response parsing
- `sync_detailed` method calls  
- Complex import patterns
- Manual type casting