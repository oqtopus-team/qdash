#!/usr/bin/env python3
"""
QDash Integrated Client Example

This demonstrates the integrated qdash.client usage
where you can import directly from the qdash package.

Usage:
    # Install QDash with client
    pip install -e .

    # Or add to PYTHONPATH
    export PYTHONPATH=/workspace/qdash/src:$PYTHONPATH
"""

import asyncio
from typing import List

try:
    # Modern integrated import - much cleaner!
    from qdash.client import Client, AuthenticatedClient
    from qdash.client.api.chip import list_chips, fetch_chip
    from qdash.client.api.execution import fetch_execution_lock_status
    from qdash.client.api.calibration import execute_calib
    from qdash.client.models import ExecuteCalibRequest
    from qdash.client.errors import UnexpectedStatus

    # Alternative: Direct from qdash root (if properly configured)
    # from qdash import Client, AuthenticatedClient

except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Make sure to:")
    print("1. Generate the client: task generate-python-client")
    print("2. Install qdash: pip install -e .")
    print("3. Or set PYTHONPATH: export PYTHONPATH=/workspace/qdash/src:$PYTHONPATH")
    exit(1)


class QDashQuantumManager:
    """High-level quantum calibration manager using the integrated client."""

    def __init__(self, base_url: str = "http://localhost:5715"):
        self.base_url = base_url
        self.client = Client(base_url=base_url)

    def get_available_chips(self) -> List:
        """Get all available quantum chips."""
        response = list_chips.sync_detailed(client=self.client)
        if response.status_code == 200:
            return response.parsed
        else:
            raise Exception(f"Failed to fetch chips: {response.status_code}")

    def get_chip_details(self, chip_name: str):
        """Get detailed information for a specific chip."""
        response = fetch_chip.sync_detailed(client=self.client, chip_name=chip_name)
        if response.status_code == 200:
            return response.parsed
        else:
            raise Exception(f"Failed to fetch chip {chip_name}: {response.status_code}")

    def is_system_ready(self) -> bool:
        """Check if the quantum system is ready for calibration."""
        response = fetch_execution_lock_status.sync_detailed(client=self.client)
        if response.status_code == 200:
            return not response.parsed.locked
        return False

    async def parallel_chip_analysis(self) -> dict:
        """Analyze multiple chips in parallel using async client."""
        async with Client(base_url=self.base_url) as async_client:
            # Get all chips first
            chips_response = await list_chips.asyncio_detailed(client=async_client)
            if chips_response.status_code != 200:
                raise Exception("Failed to fetch chips")

            chips = chips_response.parsed
            print(f"📡 Analyzing {len(chips)} chips in parallel...")

            # Create tasks for parallel chip detail fetching
            detail_tasks = []
            for chip in chips[:5]:  # Limit to first 5 for demo
                task = fetch_chip.asyncio_detailed(client=async_client, chip_name=chip.name)
                detail_tasks.append((chip.name, task))

            # Execute in parallel
            results = {}
            for chip_name, task in detail_tasks:
                try:
                    response = await task
                    if response.status_code == 200:
                        chip_detail = response.parsed
                        results[chip_name] = {
                            "status": "success",
                            "qubits": len(chip_detail.qubits),
                            "couplings": len(chip_detail.couplings),
                            "chip_id": chip_detail.id,
                        }
                    else:
                        results[chip_name] = {"status": "error", "code": response.status_code}
                except Exception as e:
                    results[chip_name] = {"status": "error", "error": str(e)}

            return results


def demo_integrated_client():
    """Demonstrate the integrated client usage."""
    print("🌟 QDash Integrated Client Demo")
    print("=" * 50)

    try:
        # Create quantum manager
        qm = QDashQuantumManager()

        # Check system status
        print("🔍 Checking system status...")
        if qm.is_system_ready():
            print("✅ System is ready for calibration")
        else:
            print("🔒 System is locked - calibration in progress")

        # Get available chips
        print("\n📡 Fetching available chips...")
        chips = qm.get_available_chips()
        print(f"✅ Found {len(chips)} quantum chips:")

        for chip in chips[:3]:  # Show first 3
            print(f"   • {chip.name} (ID: {chip.id})")

        # Get detailed info for first chip
        if chips:
            first_chip = chips[0]
            print(f"\n🔍 Getting details for chip: {first_chip.name}")
            details = qm.get_chip_details(first_chip.name)
            print(f"✅ Chip details:")
            print(f"   • Qubits: {len(details.qubits)}")
            print(f"   • Couplings: {len(details.couplings)}")
            print(f"   • ID: {details.id}")

    except Exception as e:
        print(f"❌ Demo failed: {e}")


async def demo_async_analysis():
    """Demonstrate async parallel analysis."""
    print("\n⚡ Async Parallel Analysis Demo")
    print("=" * 50)

    try:
        qm = QDashQuantumManager()

        print("🚀 Starting parallel chip analysis...")
        results = await qm.parallel_chip_analysis()

        print("✅ Analysis completed:")
        for chip_name, result in results.items():
            if result["status"] == "success":
                print(
                    f"   • {chip_name}: {result['qubits']} qubits, {result['couplings']} couplings"
                )
            else:
                print(f"   • {chip_name}: ❌ {result.get('error', 'Unknown error')}")

    except Exception as e:
        print(f"❌ Async demo failed: {e}")


def demo_direct_api_access():
    """Demonstrate direct API access for advanced users."""
    print("\n🔧 Direct API Access Demo")
    print("=" * 50)

    try:
        # Direct client usage for more control
        client = Client(
            base_url="http://localhost:5715",
            timeout=10.0,  # Custom timeout
            headers={"X-Custom-Header": "quantum-research"},
        )

        # Direct API calls
        print("📡 Making direct API calls...")

        # Example: Get chips with full response details
        response = list_chips.sync_detailed(client=client)
        print(f"✅ Response status: {response.status_code}")
        print(f"✅ Headers: {dict(response.headers) if response.headers else 'None'}")

        if response.status_code == 200:
            chips = response.parsed
            print(f"✅ Data: {len(chips)} chips loaded")

    except UnexpectedStatus as e:
        print(f"⚠️  Unexpected API status: {e.status_code}")
    except Exception as e:
        print(f"❌ Direct access demo failed: {e}")


async def main():
    """Main demo runner."""
    print("🎯 QDash Integrated Python Client")
    print("Now with clean imports: from qdash.client import Client")
    print("=" * 60)

    # Run demos
    demo_integrated_client()
    await demo_async_analysis()
    demo_direct_api_access()

    print(f"\n✨ Demo completed!")
    print(f"\n📖 Key Integration Benefits:")
    print(f"   • Clean imports: from qdash.client import Client")
    print(f"   • Part of main qdash package")
    print(f"   • No separate package to manage")
    print(f"   • Integrated with quantum calibration workflows")
    print(f"   • Type-safe attrs models")
    print(f"   • Full async/await support")


if __name__ == "__main__":
    asyncio.run(main())
