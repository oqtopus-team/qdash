#!/usr/bin/env python3
"""Demonstration of automatic API endpoint discovery."""

def main():
    """Demonstrate automatic API discovery - no manual endpoint implementation needed!"""
    from qdash_client import QDashClient
    
    print("🚀 Automatic API Discovery Demo")
    print("=" * 50)

    # Simple initialization
    client = QDashClient(
        base_url="http://localhost:2004",
        username="orangekame3"
    )
    
    print("✅ QDashClient created with automatic API discovery")
    
    # Show all available endpoints
    print("\n📋 Available API endpoints:")
    endpoints = client.list_endpoints()
    for module, functions in endpoints.items():
        print(f"  📁 {module}:")
        for func in functions[:5]:  # Show first 5 functions per module
            print(f"    • {func}")
        if len(functions) > 5:
            print(f"    ... and {len(functions) - 5} more")
    
    print(f"\n🎯 Total: {sum(len(funcs) for funcs in endpoints.values())} API endpoints discovered automatically!")

    # Method 1: Direct module access (like your original style)
    print("\n" + "="*50)
    print("🔧 Method 1: Direct module access")
    print("="*50)
    
    try:
        # Access API modules directly - they auto-include client and parse responses
        menus = client.menu.list_menu()  # Automatically parsed!
        if menus:
            print(f"📄 Found {len(menus.menus) if hasattr(menus, 'menus') else 'some'} menus")
        else:
            print("📄 No menus found or API error")
            
        chips = client.chip.list_chips()
        if chips:
            print(f"💾 Found {len(chips)} chips")
            for chip in chips[:3]:
                print(f"   - {chip.chip_id}: {chip.num_qubits} qubits")
        else:
            print("💾 No chips found or API error")
            
    except AttributeError as e:
        print(f"⚠️  Module access error: {e}")

    # Method 2: Generic call method
    print("\n" + "="*50)  
    print("🎯 Method 2: Generic call method")
    print("="*50)
    
    # Generic method - can call any endpoint by string path
    menus = client.call('menu.list_menu')
    if menus:
        print(f"📄 Found menus via call(): {type(menus)}")
    
    config = client.call('settings.fetch_config')  
    if config:
        print(f"⚙️  Got config via call(): {type(config)}")
    
    # With parameters
    chip = client.call('chip.fetch_chip', chip_id='64Qv1')
    if chip:
        print(f"🔍 Found specific chip: {chip.chip_id}")
    else:
        print("🔍 Chip not found")

    # Method 3: Health check and error handling
    print("\n" + "="*50)
    print("🏥 Method 3: Health check and error handling")
    print("="*50)
    
    if client.is_healthy():
        print("✅ API is healthy and responding")
    else:
        print("❌ API health check failed")
        
    # Try calling non-existent endpoint
    result = client.call('nonexistent.endpoint')
    print(f"🚫 Non-existent endpoint result: {result}")

    print("\n🎉 Demo completed!")
    print("\n💡 Key benefits:")
    print("   • No manual endpoint implementation needed")
    print("   • Automatic client injection and response parsing")  
    print("   • Multiple access patterns (module.func or call('module.func'))")
    print("   • All endpoints available immediately")
    print("   • Error handling built-in")


def comparison_with_original():
    """Show the difference between original and automatic approach."""
    print("\n" + "="*70)
    print("📊 COMPARISON: Original vs Automatic")
    print("="*70)
    
    print("\n❌ Original approach:")
    print("   from qdash_client import Client") 
    print("   from qdash_client.api.menu import list_menu")
    print("   client = Client(...)")
    print("   response = list_menu.sync_detailed(client=client)")
    print("   menus = response.parsed if response.status_code == 200 else None")
    
    print("\n✅ Automatic approach:")
    print("   from qdash_client import QDashClient")
    print("   client = QDashClient(...)")
    print("   menus = client.menu.list_menu()  # OR client.call('menu.list_menu')")
    
    print("\n🚀 Benefits:")
    print("   • 5 lines → 3 lines")
    print("   • No imports for each endpoint")
    print("   • No manual response handling")
    print("   • All endpoints available automatically")
    print("   • Built-in error handling")


if __name__ == "__main__":
    main()
    comparison_with_original()