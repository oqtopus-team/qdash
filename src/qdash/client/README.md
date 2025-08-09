# QDash Python Client

A Python client library for accessing QDash API, auto-generated from OpenAPI specification.

## Installation

### From GitHub

```bash
# Install directly from GitHub
pip install git+https://github.com/oqtopus-team/qdash.git#subdirectory=src/qdash/client

# Install from specific branch
pip install git+https://github.com/oqtopus-team/qdash.git@develop#subdirectory=src/qdash/client

# Install from specific tag/release
pip install git+https://github.com/oqtopus-team/qdash.git@v0.1.0#subdirectory=src/qdash/client
```

### From PyPI (when published)

```bash
pip install qdash-client
```

## Usage

```python
from client import Client
from client.api.chip import list_chips, fetch_chip

# Create client instance
client = Client(base_url="http://localhost:5715")

# Get all chips
response = list_chips.sync_detailed(client=client)
if response.status_code == 200:
    chips = response.parsed
    for chip in chips:
        print(f"Chip: {chip.name}")

# Get specific chip details
chip_response = fetch_chip.sync_detailed(
    client=client,
    chip_name="sample_chip"
)
if chip_response.status_code == 200:
    chip_detail = chip_response.parsed
    print(f"Qubits: {len(chip_detail.qubits)}")
```

## Async Usage

```python
import asyncio
from client import Client
from client.api.chip import list_chips

async def main():
    async with Client(base_url="http://localhost:5715") as client:
        response = await list_chips.asyncio_detailed(client=client)
        if response.status_code == 200:
            chips = response.parsed
            print(f"Found {len(chips)} chips")

asyncio.run(main())
```

## Features

- Full type hints support
- Synchronous and asynchronous API calls
- Auto-generated from OpenAPI specification
- Comprehensive error handling
- Context manager support

## Dependencies

- httpx >= 0.27.0
- attrs >= 23.1.0
- Python >= 3.10

## License

Apache License 2.0