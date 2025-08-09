#!/usr/bin/env python3
"""
QDash Python Client Examples

This demonstrates how to use the generated openapi-python-client
for QDash quantum calibration workflows.

Make sure to first install the client:
    pip install -e ./qdash_client
"""

import asyncio
from typing import Optional

# Import the generated client
try:
    from qdash_client import Client, AuthenticatedClient
    from qdash_client.api.chip import list_chips, fetch_chip
    from qdash_client.api.calibration import execute_calib
    from qdash_client.api.execution import fetch_execution_lock_status
    from qdash_client.models import ExecuteCalibRequest
    from qdash_client.errors import UnexpectedStatus
except ImportError:
    print("❌ QDash client not found!")
    print("First generate the client: task generate-python-client")
    print("Then install it: pip install -e ./qdash_client")
    exit(1)


def example_synchronous_usage():
    """Example of synchronous client usage."""
    print("🔄 Synchronous Client Example")
    print("=" * 40)

    # Create client
    client = Client(base_url="http://localhost:5715")

    try:
        # Example 1: List all chips
        print("📡 Fetching all chips...")
        chips_response = list_chips.sync_detailed(client=client)

        if chips_response.status_code == 200:
            chips = chips_response.parsed
            print(f"✅ Found {len(chips)} chips:")
            for chip in chips[:3]:  # Show first 3
                print(f"   • {chip.name} (ID: {chip.id})")
        else:
            print(f"❌ Error fetching chips: {chips_response.status_code}")
            return

        # Example 2: Get specific chip details
        if chips:
            first_chip_name = chips[0].name
            print(f"\n🔍 Fetching details for chip: {first_chip_name}")

            chip_response = fetch_chip.sync_detailed(client=client, chip_name=first_chip_name)

            if chip_response.status_code == 200:
                chip_detail = chip_response.parsed
                print(f"✅ Chip details:")
                print(f"   • Name: {chip_detail.name}")
                print(f"   • Qubits: {len(chip_detail.qubits)}")
                print(f"   • Couplings: {len(chip_detail.couplings)}")
            else:
                print(f"❌ Error fetching chip details: {chip_response.status_code}")

        # Example 3: Check execution lock status
        print(f"\n🔒 Checking execution lock status...")
        lock_response = fetch_execution_lock_status.sync_detailed(client=client)

        if lock_response.status_code == 200:
            lock_status = lock_response.parsed
            print(f"✅ Lock status: {'🔒 Locked' if lock_status.locked else '🔓 Unlocked'}")
            if lock_status.locked:
                print(f"   Locked by: {lock_status.locked_by}")
        else:
            print(f"❌ Error fetching lock status: {lock_response.status_code}")

    except UnexpectedStatus as e:
        print(f"❌ API returned unexpected status: {e.status_code}")
        print(f"   Response: {e.content}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")


async def example_asynchronous_usage():
    """Example of asynchronous client usage."""
    print("\n⚡ Asynchronous Client Example")
    print("=" * 40)

    # Create async client
    async with Client(base_url="http://localhost:5715") as client:
        try:
            # Example 1: Parallel requests
            print("📡 Making parallel requests...")

            # Use asyncio.gather for concurrent requests
            chips_task = list_chips.asyncio_detailed(client=client)
            lock_task = fetch_execution_lock_status.asyncio_detailed(client=client)

            chips_response, lock_response = await asyncio.gather(
                chips_task, lock_task, return_exceptions=True
            )

            # Handle chips response
            if isinstance(chips_response, Exception):
                print(f"❌ Error fetching chips: {chips_response}")
            elif chips_response.status_code == 200:
                chips = chips_response.parsed
                print(f"✅ Found {len(chips)} chips")

            # Handle lock response
            if isinstance(lock_response, Exception):
                print(f"❌ Error fetching lock: {lock_response}")
            elif lock_response.status_code == 200:
                lock_status = lock_response.parsed
                print(f"✅ Lock status: {'🔒 Locked' if lock_status.locked else '🔓 Unlocked'}")

            # Example 2: Conditional execution
            if (
                not isinstance(chips_response, Exception)
                and chips_response.status_code == 200
                and not isinstance(lock_response, Exception)
                and lock_response.status_code == 200
            ):
                chips = chips_response.parsed
                lock_status = lock_response.parsed

                if not lock_status.locked and chips:
                    print(f"\n🚀 System unlocked! Could start calibration on {chips[0].name}")
                    # Here you would start a calibration if needed
                    # calibration_request = ExecuteCalibRequest(...)
                    # await execute_calib.asyncio_detailed(client=client, json_body=calibration_request)
                else:
                    print(f"\n⏸️  System locked or no chips available")

        except Exception as e:
            print(f"❌ Async error: {e}")


def example_error_handling():
    """Example of proper error handling."""
    print("\n🛡️  Error Handling Example")
    print("=" * 40)

    # Create client with custom settings
    client = Client(
        base_url="http://localhost:5715",
        timeout=5.0,  # 5 second timeout
        raise_on_unexpected_status=True,  # Raise exceptions for unexpected status
    )

    try:
        # Try to fetch a non-existent chip
        response = fetch_chip.sync_detailed(client=client, chip_name="non-existent-chip")

        if response.status_code == 404:
            print("✅ Properly handled 404 - chip not found")
        elif response.status_code == 200:
            print("✅ Chip found unexpectedly!")
        else:
            print(f"⚠️  Unexpected status: {response.status_code}")

    except UnexpectedStatus as e:
        print(f"✅ Caught expected error: HTTP {e.status_code}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")


def example_authenticated_usage():
    """Example using authenticated client."""
    print("\n🔐 Authenticated Client Example")
    print("=" * 40)

    # For APIs requiring authentication
    auth_client = AuthenticatedClient(
        base_url="http://localhost:5715",
        token="your-api-token-here",  # Would come from login
        headers={"X-Username": "quantum-engineer"},
    )

    try:
        # Same API calls work with authenticated client
        chips_response = list_chips.sync_detailed(client=auth_client)

        if chips_response.status_code == 200:
            chips = chips_response.parsed
            print(f"✅ Authenticated access successful: {len(chips)} chips")
        else:
            print(f"❌ Authentication failed: {chips_response.status_code}")

    except Exception as e:
        print(f"❌ Auth error: {e}")


async def main():
    """Main example runner."""
    print("🌟 QDash Python Client Examples")
    print("Generated by openapi-python-client (1.6k⭐)")
    print("=" * 50)

    # Run examples
    example_synchronous_usage()
    await example_asynchronous_usage()
    example_error_handling()
    example_authenticated_usage()

    print("\n✨ Examples completed!")
    print("\n📖 Key Features Demonstrated:")
    print("   • Synchronous and asynchronous usage")
    print("   • Parallel request execution")
    print("   • Proper error handling")
    print("   • Type-safe responses with attrs models")
    print("   • Authentication support")
    print("   • httpx integration with modern Python")


if __name__ == "__main__":
    asyncio.run(main())
