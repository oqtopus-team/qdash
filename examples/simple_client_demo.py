#!/usr/bin/env python3
"""
QDash Client Demo

Simple demonstration of QDash client usage.
Run after: task generate-python-client
"""


def main() -> None:
    """Demo function."""
    print("🚀 QDash Client Demo")
    print("=" * 25)

    try:
        # Import at runtime to avoid early import issues
        from qdash_client import Client
        from qdash_client.api.chip import list_chips

        print("✅ Client imported successfully")

        # Create client instance
        client = Client(base_url="http://localhost:5715")
        print("✅ Client created")

        # Example API call (will fail if server not running, but that's OK)
        print("📡 Testing API connection...")
        response = list_chips.sync_detailed(client=client)  # type: ignore

        if response.status_code == 200:
            chips = response.parsed or []
            print(f"✅ Connected! Found {len(chips)} chips")
        else:
            print(f"⚠️  Server responded with status: {response.status_code}")

    except ImportError as e:
        print(f"❌ Import failed: {e}")
        print("Solution: run 'task generate-python-client'")
    except Exception as e:
        print(f"⚠️  Connection failed: {e}")
        print("This is expected if QDash server is not running")
        print("Client import and creation succeeded!")


if __name__ == "__main__":
    main()
