# QDash Client Usage Comparison

## Before (Current Usage)

```python
def main():
    from qdash_client import Client
    from qdash_client.api.menu import list_menu

    print("✅ Client imported successfully")

    # Verbose initialization
    client = Client(
        base_url="http://localhost:2004",
        headers={"X-Username":"orangekame3"},
        raise_on_unexpected_status=True
    )
    print("✅ Client created")

    # Verbose API calls with manual response handling
    print("📡 Testing API connection...")
    response = list_menu.sync_detailed(client=client)  # type: ignore
    print(response)  # Raw response object

    print("Hello from client-test!")
```

**Issues:**

- Verbose imports for each API endpoint
- Manual header setup
- Manual response parsing
- No error handling
- Raw response objects
- Type ignore needed

## After (Enhanced Usage)

```python
def main():
    from qdash_client import QDashClient

    print("✅ Enhanced QDashClient imported successfully")

    # Simple initialization with sensible defaults
    client = QDashClient(
        base_url="http://localhost:2004",
        username="orangekame3"  # Automatic X-Username header
    )
    print(f"✅ Client created: {client}")

    # Built-in health check
    if client.is_healthy():
        print("✅ API is healthy")

    # Clean API calls with automatic parsing
    menus = client.get_menus()
    if menus:
        print(f"📄 Found {len(menus.menus)} menus")

    chips = client.get_chips()
    if chips:
        print(f"💾 Found {len(chips)} chips")
        for chip in chips[:3]:
            print(f"   - {chip.chip_id}: {chip.num_qubits} qubits")

    print("🚀 Enhanced demo completed!")
```

**Improvements:**

- ✅ Single import
- ✅ Sensible defaults
- ✅ Automatic authentication headers
- ✅ Built-in error handling
- ✅ Parsed response objects
- ✅ Health checks
- ✅ Clean method names
- ✅ Type safety without ignores

## Configuration Options

### Environment-based Configuration

```python
import os
from qdash_client import QDashClient

client = QDashClient(
    base_url=os.getenv("QDASH_URL", "http://localhost:5715"),
    username=os.getenv("QDASH_USER"),
    timeout=30,
    verify_ssl=False  # For development
)
```

### Advanced Usage

```python
# Batch operations
chips = client.get_chips()
for chip in chips:
    executions = client.get_chip_executions(chip.chip_id)
    print(f"{chip.chip_id}: {len(executions)} executions")

# System status
config = client.get_config()
lock_status = client.get_execution_lock_status()
parameters = client.get_parameters()
```

## Migration Guide

1. **Replace imports:**

   ```python
   # Old
   from qdash_client import Client
   from qdash_client.api.menu import list_menu

   # New
   from qdash_client import QDashClient
   ```

2. **Simplify initialization:**

   ```python
   # Old
   client = Client(
       base_url="http://localhost:2004",
       headers={"X-Username": "orangekame3"},
       raise_on_unexpected_status=True
   )

   # New
   client = QDashClient(
       base_url="http://localhost:2004",
       username="orangekame3"
   )
   ```

3. **Use convenience methods:**

   ```python
   # Old
   response = list_menu.sync_detailed(client=client)
   if response.status_code == 200:
       menus = response.parsed

   # New
   menus = client.get_menus()
   ```
