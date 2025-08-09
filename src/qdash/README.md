# QDash API Client

A client library for accessing QDash API, auto-generated from OpenAPI specification.

## Installation

```bash
# Install from GitHub subdirectory
pip install git+https://github.com/oqtopus-team/qdash.git#subdirectory=src/qdash/client
```

## Usage

First, create a client:

```python
from qdash.client import Client

client = Client(base_url="http://localhost:5715")
```

If the endpoints require authentication, use `AuthenticatedClient`:

```python
from qdash.client import AuthenticatedClient

client = AuthenticatedClient(
    base_url="https://api.example.com", 
    token="SuperSecretToken"
)
```

Now call your endpoint and use your models:

```python
from qdash.client.api.chip import list_chips, fetch_chip
from qdash.client.types import Response

with client as client:
    # Get parsed data directly
    chips = list_chips.sync(client=client)
    
    # Or get full response with status code
    response: Response = list_chips.sync_detailed(client=client)
    if response.status_code == 200:
        chips = response.parsed
```

Or use async version:

```python
from qdash.client.api.chip import list_chips

async with client as client:
    chips = await list_chips.asyncio(client=client)
    response = await list_chips.asyncio_detailed(client=client)
```

## SSL Configuration

By default, HTTPS APIs verify SSL certificates. You can customize this:

```python
# Use custom certificate bundle
client = AuthenticatedClient(
    base_url="https://internal_api.example.com", 
    token="SuperSecretToken",
    verify_ssl="/path/to/certificate_bundle.pem",
)

# Disable SSL verification (not recommended for production)
client = AuthenticatedClient(
    base_url="https://internal_api.example.com", 
    token="SuperSecretToken", 
    verify_ssl=False
)
```

## API Structure

1. Every path/method combo becomes a Python module with four functions:
   - `sync`: Blocking request that returns parsed data (if successful) or `None`
   - `sync_detailed`: Blocking request that always returns a `Response`, optionally with `parsed` set if the request was successful
   - `asyncio`: Like `sync` but async instead of blocking
   - `asyncio_detailed`: Like `sync_detailed` but async instead of blocking

2. All path/query params, and bodies become method arguments

3. API endpoints are organized by tags into modules under `client.api`

## Advanced Customization

Customize the underlying `httpx.Client`:

```python
from qdash.client import Client

def log_request(request):
    print(f"Request: {request.method} {request.url}")

def log_response(response):
    print(f"Response: {response.status_code}")

client = Client(
    base_url="https://api.example.com",
    httpx_args={
        "event_hooks": {
            "request": [log_request], 
            "response": [log_response]
        }
    },
)

# Or set the httpx client directly
import httpx
client = Client(base_url="https://api.example.com")
client.set_httpx_client(httpx.Client(base_url="https://api.example.com", proxies="http://localhost:8030"))
```

## Building / Publishing

This project uses [Poetry](https://python-poetry.org/) to manage dependencies and packaging. Here are the basics:

1. Update the metadata in pyproject.toml (e.g. authors, version)
2. Publish the client to PyPI:
   ```bash
   poetry build
   poetry publish
   ```

If you want to install this client locally:
```bash
pip install -e .
```

## Regenerating the Client

This client is auto-generated from the OpenAPI specification. To regenerate:

```bash
# From the project root
task generate-python-client

# Or using the script directly
uv run generate-python-client
```