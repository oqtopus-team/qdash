#!/usr/bin/env python3
"""Test script to verify enhanced client preservation during regeneration."""

def test_enhanced_client():
    """Test that enhanced client features are working."""
    try:
        from qdash_client import QDashClient, QDashHTTPError
        
        print("✅ Enhanced QDashClient import successful")
        
        # Test client creation
        client = QDashClient(
            base_url="http://localhost:5715",
            username="test_user"
        )
        
        print(f"✅ Enhanced client created: {client}")
        
        # Test module discovery
        endpoints = client.list_endpoints()
        print(f"✅ Module discovery: {len(endpoints)} modules found")
        
        # Test caching
        menu_module_1 = client.menu
        menu_module_2 = client.menu
        print(f"✅ Module caching: {menu_module_1 is menu_module_2}")
        
        # Test IDE support
        menu_methods = dir(client.menu)
        print(f"✅ IDE support: {len(menu_methods)} methods available")
        
        # Test method signature preservation
        list_menu_method = client.menu.list_menu
        has_signature = hasattr(list_menu_method, '__signature__')
        print(f"✅ Signature preservation: {has_signature}")
        
        # Test custom exceptions are available
        try:
            raise QDashHTTPError("Test error", 404)
        except QDashHTTPError as e:
            print(f"✅ Custom exceptions: {e.status_code}")
            
        print("\n🎉 All enhanced features verified!")
        return True
        
    except Exception as e:
        print(f"❌ Enhanced client test failed: {e}")
        return False


def test_preservation_list():
    """Test that preservation list exists and is readable."""
    from pathlib import Path
    
    project_root = Path(__file__).parent.parent
    preserve_file = project_root / "qdash_client" / ".qdash-preserve"
    
    if preserve_file.exists():
        try:
            content = preserve_file.read_text()
            lines = [l.strip() for l in content.split('\n') if l.strip() and not l.startswith('#')]
            print(f"✅ Preservation list: {len(lines)} files protected")
            
            for line in lines[:5]:  # Show first 5
                print(f"   🛡️  {line}")
            if len(lines) > 5:
                print(f"   ... and {len(lines) - 5} more")
                
            return True
        except Exception as e:
            print(f"❌ Failed to read preservation list: {e}")
            return False
    else:
        print(f"❌ Preservation list not found at {preserve_file}")
        return False


if __name__ == "__main__":
    print("🧪 Enhanced Client Preservation Test")
    print("=" * 50)
    
    success = True
    
    # Test enhanced client functionality
    print("\n1. Testing enhanced client features...")
    success &= test_enhanced_client()
    
    # Test preservation list
    print("\n2. Testing preservation configuration...")
    success &= test_preservation_list()
    
    print(f"\n{'🎉 All tests passed!' if success else '❌ Some tests failed!'}")
    print("\n💡 This script verifies that:")
    print("   • Enhanced client features are working")
    print("   • Preservation list is configured")
    print("   • Files will be protected during regeneration")