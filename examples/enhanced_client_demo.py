#!/usr/bin/env python3
"""Enhanced QDashClient usage example with improved error handling and caching."""

def main():
    """Demonstrate enhanced QDashClient with all GPT-recommended improvements."""
    from qdash_client import QDashClient, QDashHTTPError, QDashConnectionError
    
    print("🚀 Enhanced QDashClient Demo (GPT-Improved)")
    print("=" * 60)

    # Simple initialization with defaults
    client = QDashClient(
        base_url="http://localhost:2004",
        username="orangekame3"
    )
    print(f"✅ Enhanced QDashClient created: {client}")

    # Show available endpoints with caching
    print(f"
📋 Available API modules: {len(client.__dir__())} total")
    print("   Modules:", ", ".join([m for m in client.__dir__() if not m.startswith('_')]))
    
    # Test caching performance
    print("
⚡ Testing caching performance...")
    import time
    
    # First access (will cache)
    start = time.time()
    try:
        menu_module = client.menu  # This will cache the module
        first_access_time = time.time() - start
        print(f"   First access: {first_access_time:.4f}s (caching)")
        
        # Second access (from cache)
        start = time.time()
        menu_module_cached = client.menu
        second_access_time = time.time() - start
        print(f"   Second access: {second_access_time:.4f}s (cached)")
        print(f"   Speedup: {first_access_time/second_access_time:.1f}x faster")
        
    except Exception as e:
        print(f"   ⚠️ Module access error: {e}")

    # Test IDE autocompletion support
    print(f"
🔧 Testing IDE support...")
    try:
        menu_methods = dir(client.menu)
        print(f"   Menu module methods: {len(menu_methods)} available")
        print(f"   First 5: {menu_methods[:5]}")
        
        # Check if method has proper signature
        list_menu_func = client.menu.list_menu
        if hasattr(list_menu_func, '__signature__'):
            print(f"   ✅ list_menu signature: {list_menu_func.__signature__}")
        if hasattr(list_menu_func, '__doc__'):
            doc_preview = (list_menu_func.__doc__ or "No docstring")[:100]
            print(f"   ✅ list_menu docstring: {doc_preview}...")
            
    except Exception as e:
        print(f"   ⚠️ IDE support error: {e}")

    # Test proper error handling
    print(f"
🔥 Testing improved error handling...")
    
    # Test API call with proper exception handling
    try:
        print("   📡 Calling menu.list_menu...")
        menus = client.menu.list_menu()
        if menus:
            count = len(menus.menus) if hasattr(menus, 'menus') else len(menus) if isinstance(menus, list) else 'unknown'
            print(f"   ✅ Success: Found {count} menus")
        else:
            print("   📄 Success: No menus returned")
            
    except QDashHTTPError as e:
        print(f"   🔴 HTTP Error: {e}")
        print(f"      Status: {e.status_code}")
        print(f"      URL: {e.request_url}")
        print(f"      Request ID: {e.request_id}")
        
    except QDashConnectionError as e:
        print(f"   🔴 Connection Error: {e}")
        
    except Exception as e:
        print(f"   🔴 Unexpected Error: {type(e).__name__}: {e}")

    # Test chip operations 
    try:
        print("   🔧 Calling chip.list_chips...")
        chips = client.chip.list_chips()
        if chips:
            print(f"   ✅ Success: Found {len(chips)} chips")
            for chip in chips[:3]:
                print(f"      - {chip.chip_id}: {chip.num_qubits} qubits")
        else:
            print("   💾 Success: No chips returned")
            
    except QDashHTTPError as e:
        print(f"   🔴 HTTP Error: {e.status_code} - {e}")
        
    except Exception as e:
        print(f"   🔴 Error: {type(e).__name__}: {e}")

    # Test generic call method with error handling
    print(f"
🎯 Testing generic call() method...")
    try:
        config = client.call('settings.fetch_config')
        print(f"   ✅ Config call successful: {type(config).__name__}")
        
    except QDashHTTPError as e:
        print(f"   🔴 HTTP Error in call(): {e.status_code}")
        
    except ValueError as e:
        print(f"   🔴 Invalid endpoint: {e}")
        
    except Exception as e:
        print(f"   🔴 Call error: {type(e).__name__}: {e}")

    # Test invalid endpoint
    try:
        client.call('invalid.endpoint')
        print("   ❌ Should have failed!")
    except ValueError as e:
        print(f"   ✅ Correctly caught invalid endpoint: {e}")
    except Exception as e:
        print(f"   ⚠️ Unexpected error type: {type(e).__name__}: {e}")

    # Show cache status
    print(f"
📊 Final cache status: {client}")
    
    print(f"
🎉 Enhanced demo completed!")


def error_handling_showcase():
    """Demonstrate comprehensive error handling."""
    from qdash_client import QDashClient, QDashHTTPError, QDashConnectionError, QDashAuthError
    
    print("
" + "=" * 60)
    print("🔥 Error Handling Showcase")
    print("=" * 60)
    
    # Different error scenarios
    scenarios = [
        ("Invalid URL", {"base_url": "http://invalid-host:9999"}),
        ("Wrong port", {"base_url": "http://localhost:9999"}),
        ("Valid config", {"base_url": "http://localhost:2004", "username": "orangekame3"}),
    ]
    
    for name, config in scenarios:
        print(f"
🧪 Testing: {name}")
        try:
            client = QDashClient(**config)
            
            # Test health check
            if client.is_healthy():
                print("   ✅ API is healthy")
                
                # Try actual API call
                result = client.call('settings.fetch_config')
                print("   ✅ API call successful")
            else:
                print("   ❌ API health check failed")
                
        except QDashConnectionError as e:
            print(f"   🔴 Connection failed: {e}")
        except QDashHTTPError as e:
            print(f"   🔴 HTTP error {e.status_code}: {e}")
        except Exception as e:
            print(f"   🔴 Unexpected error: {type(e).__name__}: {e}")


def performance_comparison():
    """Compare performance between cached and non-cached access."""
    from qdash_client import QDashClient
    import time
    
    print("
" + "=" * 60) 
    print("⚡ Performance Comparison")
    print("=" * 60)
    
    client = QDashClient(base_url="http://localhost:2004", username="orangekame3")
    
    print("
🔬 Module access performance:")
    times = []
    
    # Test multiple accesses to same module
    for i in range(5):
        start = time.time()
        menu_module = client.menu
        elapsed = time.time() - start
        times.append(elapsed)
        print(f"   Access {i+1}: {elapsed:.6f}s")
    
    print(f"   Average: {sum(times)/len(times):.6f}s")
    print(f"   First vs Last: {times[0]/times[-1]:.1f}x speedup")
    
    print("
🎯 Method wrapper performance:")
    method_times = []
    
    # Test multiple accesses to same method
    for i in range(5):
        start = time.time()
        method = client.menu.list_menu
        elapsed = time.time() - start
        method_times.append(elapsed)
        print(f"   Method access {i+1}: {elapsed:.6f}s")
    
    print(f"   Method average: {sum(method_times)/len(method_times):.6f}s")
    print(f"   Method first vs last: {method_times[0]/method_times[-1]:.1f}x speedup")


if __name__ == "__main__":
    main()
    error_handling_showcase()
    performance_comparison()#!/usr/bin/env python3
"""Enhanced QDashClient usage example with improved error handling and caching."""

def main():
    """Demonstrate enhanced QDashClient with all GPT-recommended improvements."""
    from qdash_client import QDashClient, QDashHTTPError, QDashConnectionError
    
    print("🚀 Enhanced QDashClient Demo (GPT-Improved)")
    print("=" * 60)

    # Simple initialization with defaults
    client = QDashClient(
        base_url="http://localhost:2004",
        username="orangekame3"
    )
    print(f"✅ Enhanced QDashClient created: {client}")

    # Show available endpoints with caching
    print(f"
📋 Available API modules: {len(client.__dir__())} total")
    print("   Modules:", ", ".join([m for m in client.__dir__() if not m.startswith('_')]))
    
    # Test caching performance
    print("
⚡ Testing caching performance...")
    import time
    
    # First access (will cache)
    start = time.time()
    try:
        menu_module = client.menu  # This will cache the module
        first_access_time = time.time() - start
        print(f"   First access: {first_access_time:.4f}s (caching)")
        
        # Second access (from cache)
        start = time.time()
        menu_module_cached = client.menu
        second_access_time = time.time() - start
        print(f"   Second access: {second_access_time:.4f}s (cached)")
        print(f"   Speedup: {first_access_time/second_access_time:.1f}x faster")
        
    except Exception as e:
        print(f"   ⚠️ Module access error: {e}")

    # Test IDE autocompletion support
    print(f"
🔧 Testing IDE support...")
    try:
        menu_methods = dir(client.menu)
        print(f"   Menu module methods: {len(menu_methods)} available")
        print(f"   First 5: {menu_methods[:5]}")
        
        # Check if method has proper signature
        list_menu_func = client.menu.list_menu
        if hasattr(list_menu_func, '__signature__'):
            print(f"   ✅ list_menu signature: {list_menu_func.__signature__}")
        if hasattr(list_menu_func, '__doc__'):
            doc_preview = (list_menu_func.__doc__ or "No docstring")[:100]
            print(f"   ✅ list_menu docstring: {doc_preview}...")
            
    except Exception as e:
        print(f"   ⚠️ IDE support error: {e}")

    # Test proper error handling
    print(f"
🔥 Testing improved error handling...")
    
    # Test API call with proper exception handling
    try:
        print("   📡 Calling menu.list_menu...")
        menus = client.menu.list_menu()
        if menus:
            count = len(menus.menus) if hasattr(menus, 'menus') else len(menus) if isinstance(menus, list) else 'unknown'
            print(f"   ✅ Success: Found {count} menus")
        else:
            print("   📄 Success: No menus returned")
            
    except QDashHTTPError as e:
        print(f"   🔴 HTTP Error: {e}")
        print(f"      Status: {e.status_code}")
        print(f"      URL: {e.request_url}")
        print(f"      Request ID: {e.request_id}")
        
    except QDashConnectionError as e:
        print(f"   🔴 Connection Error: {e}")
        
    except Exception as e:
        print(f"   🔴 Unexpected Error: {type(e).__name__}: {e}")

    # Test chip operations 
    try:
        print("   🔧 Calling chip.list_chips...")
        chips = client.chip.list_chips()
        if chips:
            print(f"   ✅ Success: Found {len(chips)} chips")
            for chip in chips[:3]:
                print(f"      - {chip.chip_id}: {chip.num_qubits} qubits")
        else:
            print("   💾 Success: No chips returned")
            
    except QDashHTTPError as e:
        print(f"   🔴 HTTP Error: {e.status_code} - {e}")
        
    except Exception as e:
        print(f"   🔴 Error: {type(e).__name__}: {e}")

    # Test generic call method with error handling
    print(f"
🎯 Testing generic call() method...")
    try:
        config = client.call('settings.fetch_config')
        print(f"   ✅ Config call successful: {type(config).__name__}")
        
    except QDashHTTPError as e:
        print(f"   🔴 HTTP Error in call(): {e.status_code}")
        
    except ValueError as e:
        print(f"   🔴 Invalid endpoint: {e}")
        
    except Exception as e:
        print(f"   🔴 Call error: {type(e).__name__}: {e}")

    # Test invalid endpoint
    try:
        client.call('invalid.endpoint')
        print("   ❌ Should have failed!")
    except ValueError as e:
        print(f"   ✅ Correctly caught invalid endpoint: {e}")
    except Exception as e:
        print(f"   ⚠️ Unexpected error type: {type(e).__name__}: {e}")

    # Show cache status
    print(f"
📊 Final cache status: {client}")
    
    print(f"
🎉 Enhanced demo completed!")


def error_handling_showcase():
    """Demonstrate comprehensive error handling."""
    from qdash_client import QDashClient, QDashHTTPError, QDashConnectionError, QDashAuthError
    
    print("
" + "=" * 60)
    print("🔥 Error Handling Showcase")
    print("=" * 60)
    
    # Different error scenarios
    scenarios = [
        ("Invalid URL", {"base_url": "http://invalid-host:9999"}),
        ("Wrong port", {"base_url": "http://localhost:9999"}),
        ("Valid config", {"base_url": "http://localhost:2004", "username": "orangekame3"}),
    ]
    
    for name, config in scenarios:
        print(f"
🧪 Testing: {name}")
        try:
            client = QDashClient(**config)
            
            # Test health check
            if client.is_healthy():
                print("   ✅ API is healthy")
                
                # Try actual API call
                result = client.call('settings.fetch_config')
                print("   ✅ API call successful")
            else:
                print("   ❌ API health check failed")
                
        except QDashConnectionError as e:
            print(f"   🔴 Connection failed: {e}")
        except QDashHTTPError as e:
            print(f"   🔴 HTTP error {e.status_code}: {e}")
        except Exception as e:
            print(f"   🔴 Unexpected error: {type(e).__name__}: {e}")


def performance_comparison():
    """Compare performance between cached and non-cached access."""
    from qdash_client import QDashClient
    import time
    
    print("
" + "=" * 60) 
    print("⚡ Performance Comparison")
    print("=" * 60)
    
    client = QDashClient(base_url="http://localhost:2004", username="orangekame3")
    
    print("
🔬 Module access performance:")
    times = []
    
    # Test multiple accesses to same module
    for i in range(5):
        start = time.time()
        menu_module = client.menu
        elapsed = time.time() - start
        times.append(elapsed)
        print(f"   Access {i+1}: {elapsed:.6f}s")
    
    print(f"   Average: {sum(times)/len(times):.6f}s")
    print(f"   First vs Last: {times[0]/times[-1]:.1f}x speedup")
    
    print("
🎯 Method wrapper performance:")
    method_times = []
    
    # Test multiple accesses to same method
    for i in range(5):
        start = time.time()
        method = client.menu.list_menu
        elapsed = time.time() - start
        method_times.append(elapsed)
        print(f"   Method access {i+1}: {elapsed:.6f}s")
    
    print(f"   Method average: {sum(method_times)/len(method_times):.6f}s")
    print(f"   Method first vs last: {method_times[0]/method_times[-1]:.1f}x speedup")


if __name__ == "__main__":
    main()
    error_handling_showcase()
    performance_comparison()