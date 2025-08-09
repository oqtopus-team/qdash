# QDash Python Client

A Python client library for accessing QDash API, auto-generated from OpenAPI specification.

## Installation

### Option 1: Install client standalone (Recommended for client-only usage)

```bash
# Install directly from the client subdirectory
pip install git+https://github.com/oqtopus-team/qdash.git#subdirectory=src/qdash/client

# Or if you have the repository cloned locally
cd src/qdash/client
pip install .
```

### Option 2: Install as part of the full QDash package

```bash
# Install the entire QDash package
pip install git+https://github.com/oqtopus-team/qdash.git

# The client will be available as qdash.client
```

### Option 3: From PyPI (when published)

```bash
# Future release - client only
pip install qdash-client

# Or full package
pip install qdash
```

## Usage

When installed standalone (qdash-client):
```python
from qdash_client import Client
from qdash_client.api.chip import list_chips, fetch_chip
```

When installed as part of qdash package:
```python
from qdash.client import Client
from qdash.client.api.chip import list_chips, fetch_chip
```

## Usage

```python
# When installed as standalone package (qdash-client)
from qdash_client import Client
from qdash_client.api.chip import list_chips, fetch_chip

# Or when installed as part of qdash
# from qdash.client import Client
# from qdash.client.api.chip import list_chips, fetch_chip

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