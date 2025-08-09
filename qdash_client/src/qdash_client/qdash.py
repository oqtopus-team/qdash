"""Enhanced QDash client with automatic API endpoint discovery, caching, and proper error handling."""

from typing import Optional, Dict, Any, Union, Callable, Set, List
import inspect
import functools
import threading
import importlib
from .client import Client
from . import api
from .exceptions import QDashHTTPError, QDashConnectionError, QDashTimeoutError, create_http_error


class APIModule:
    """Wrapper for API modules to provide convenient access with caching and proper error handling."""
    
    def __init__(self, module, client, client_instance):
        self._module = module
        self._client = client  # Raw client
        self._client_instance = client_instance  # QDashClient instance
        self._cache = {}  # Method wrapper cache
        self._lock = threading.Lock()  # Thread-safe caching
        
    def __getattr__(self, name: str):
        """Get API function with caching and proper error handling."""
        # Check cache first
        if name in self._cache:
            return self._cache[name]
            
        # Get the original function
        if not hasattr(self._module, name):
            raise AttributeError(f"'{self._module.__name__}' has no attribute '{name}'")
            
        func = getattr(self._module, name)
        
        # Only wrap callable functions that have sync_detailed or sync
        if not callable(func):
            return func
            
        # Thread-safe cache population
        with self._lock:
            # Double-check after acquiring lock
            if name in self._cache:
                return self._cache[name]
                
            wrapper = self._create_wrapper(func, name)
            self._cache[name] = wrapper
            return wrapper
    
    def __dir__(self) -> List[str]:
        """Return list of available methods for IDE autocompletion."""
        methods = []
        for attr_name in dir(self._module):
            if not attr_name.startswith('_'):
                attr = getattr(self._module, attr_name)
                if callable(attr) and (hasattr(attr, 'sync_detailed') or hasattr(attr, 'sync')):
                    methods.append(attr_name)
        return sorted(methods)
    
    def _create_wrapper(self, func, func_name: str):
        """Create optimized wrapper with proper error handling and signature preservation."""
        # Determine which method to use
        target_func = None
        if hasattr(func, 'sync_detailed'):
            target_func = func.sync_detailed
        elif hasattr(func, 'sync'):
            target_func = func.sync
        else:
            return func  # Return as-is if not a generated API function
        
        # Get original signature and create modified version (without client param)
        try:
            original_sig = inspect.signature(target_func)
            params = [p for p in original_sig.parameters.values() if p.name != 'client']
            new_sig = original_sig.replace(parameters=params)
        except (ValueError, TypeError):
            new_sig = None
        
        def wrapper(*args, **kwargs):
            """Wrapper that auto-injects client and handles errors properly."""
            try:
                # Inject client
                kwargs['client'] = self._client
                
                # Call the original function
                response = target_func(*args, **kwargs)
                
                # Handle response based on type
                return self._client_instance._handle_response(response, func_name)
                
            except Exception as e:
                # Convert known exceptions to QDash exceptions
                return self._client_instance._handle_exception(e, func_name, args, kwargs)
        
        # Preserve function metadata for better IDE support
        try:
            functools.update_wrapper(wrapper, target_func)
            if new_sig:
                wrapper.__signature__ = new_sig
            # Copy docstring if available
            if hasattr(func, '__doc__') and func.__doc__:
                wrapper.__doc__ = func.__doc__
        except (AttributeError, TypeError):
            pass  # Ignore metadata copying errors
            
        return wrapper


class QDashClient(Client):
    """Enhanced QDash client with automatic API discovery, caching, and robust error handling."""
    
    def __init__(
        self,
        base_url: str = "http://localhost:5715",
        username: Optional[str] = None,
        **kwargs
    ):
        """Initialize QDash client with sensible defaults.
        
        Args:
            base_url: QDash API base URL (default: http://localhost:5715)
            username: Username for X-Username header authentication
            **kwargs: Additional arguments passed to base Client
        """
        headers = kwargs.pop("headers", {})
        if username:
            headers["X-Username"] = username
            
        super().__init__(
            base_url=base_url,
            headers=headers,
            raise_on_unexpected_status=kwargs.pop("raise_on_unexpected_status", True),
            **kwargs
        )
        
        # Module cache and thread safety
        self._modules = {}
        self._module_lock = threading.Lock()
        self._known_modules = None  # Lazy-loaded set of available modules
        
        # Response handling configuration
        self._success_codes = {200, 201, 202, 204}  # Configurable success codes
        
    def __getattr__(self, name: str):
        """Lazy-load and cache API modules with thread safety."""
        # Special methods that should not be proxied
        if name.startswith('_') or name in ('call', 'list_endpoints', 'is_healthy'):
            raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")
        
        # Check cache first
        if name in self._modules:
            return self._modules[name]
        
        # Thread-safe module loading
        with self._module_lock:
            # Double-check after acquiring lock
            if name in self._modules:
                return self._modules[name]
            
            # Try to import the module
            try:
                module = importlib.import_module(f'qdash_client.api.{name}')
            except ImportError:
                raise AttributeError(f"No API module named '{name}' found")
            
            # Create and cache the module proxy
            proxy = APIModule(module, self, self)
            self._modules[name] = proxy
            return proxy
    
    def __dir__(self) -> List[str]:
        """Return list of available API modules for IDE autocompletion."""
        modules = ['call', 'list_endpoints', 'is_healthy']  # Always available methods
        
        # Add dynamically discovered modules
        if self._known_modules is None:
            self._discover_modules()
        
        modules.extend(sorted(self._known_modules))
        return modules
    
    def _discover_modules(self):
        """Discover available API modules without importing them all."""
        import pkgutil
        self._known_modules = set()
        
        try:
            for importer, modname, ispkg in pkgutil.iter_modules(api.__path__):
                if not modname.startswith('_'):
                    self._known_modules.add(modname)
        except (ImportError, AttributeError):
            # Fallback: use known common modules
            self._known_modules = {
                'chip', 'menu', 'calibration', 'auth', 'parameter', 
                'settings', 'execution', 'file', 'task', 'tag', 
                'device_topology', 'backend'
            }
    
    def _handle_response(self, response, func_name: str = "unknown"):
        """Handle response with proper error checking and parsing."""
        # If it's not a response object, return as-is
        if not hasattr(response, 'status_code'):
            return response
        
        # Check for success status codes
        if response.status_code in self._success_codes:
            # Return parsed response if available, otherwise the response itself
            return getattr(response, 'parsed', response)
        
        # Create and raise appropriate HTTP error
        raise create_http_error(response)
    
    def _handle_exception(self, exception: Exception, func_name: str, args, kwargs) -> None:
        """Convert known exceptions to QDash exceptions and re-raise."""
        # Convert httpx exceptions to QDash exceptions
        import httpx
        
        if isinstance(exception, httpx.TimeoutException):
            raise QDashTimeoutError(f"Request timeout in {func_name}") from exception
        elif isinstance(exception, httpx.ConnectError):
            raise QDashConnectionError(f"Connection failed in {func_name}") from exception
        elif isinstance(exception, QDashHTTPError):
            # Already a QDash error, re-raise as-is
            raise exception
        else:
            # Re-raise other exceptions unchanged
            raise exception
    
    def call(self, endpoint_path: str, *args, **kwargs) -> Any:
        """Generic method to call any API endpoint by string path.
        
        Args:
            endpoint_path: Path like 'chip.list_chips' or 'menu.get_menu_by_name'
            *args, **kwargs: Arguments to pass to the endpoint
            
        Returns:
            Parsed response data
            
        Raises:
            QDashHTTPError: For HTTP errors
            QDashConnectionError: For connection issues
            QDashTimeoutError: For timeout issues
            ValueError: For invalid endpoint paths
            
        Example:
            client.call('chip.list_chips')
            client.call('chip.fetch_chip', chip_id='64Qv1')
            client.call('menu.get_menu_by_name', name='my_menu')
        """
        try:
            # Parse the endpoint path
            parts = endpoint_path.split('.')
            if len(parts) != 2:
                raise ValueError("endpoint_path must be in format 'module.function'")
            
            module_name, func_name = parts
            
            # Get the API module and call the function
            api_module = getattr(self, module_name)
            func = getattr(api_module, func_name)
            return func(*args, **kwargs)
            
        except AttributeError as e:
            if "has no attribute" in str(e):
                raise ValueError(f"API endpoint '{endpoint_path}' not found") from e
            raise
    
    def is_healthy(self) -> bool:
        """Check if the QDash API is healthy and responding."""
        try:
            # Try a simple API call to check health
            self.call('settings.fetch_config')
            return True
        except Exception:
            return False
    
    def list_endpoints(self) -> Dict[str, List[str]]:
        """List all available API endpoints with their functions."""
        if self._known_modules is None:
            self._discover_modules()
        
        endpoints = {}
        for module_name in self._known_modules:
            try:
                # Get the module proxy (this will create it if needed)
                module_proxy = getattr(self, module_name)
                # Get the list of available methods
                methods = dir(module_proxy)
                if methods:
                    endpoints[module_name] = methods
            except (ImportError, AttributeError):
                # Skip modules that can't be loaded
                continue
                
        return endpoints
    
    def configure_success_codes(self, codes: Set[int]) -> None:
        """Configure which HTTP status codes should be considered successful.
        
        Args:
            codes: Set of HTTP status codes to treat as successful
        """
        self._success_codes = set(codes)
    
    def __repr__(self) -> str:
        return f"QDashClient(base_url='{self._base_url}', modules_cached={len(self._modules)})""""Enhanced QDash client with automatic API endpoint discovery, caching, and proper error handling."""

from typing import Optional, Dict, Any, Union, Callable, Set, List
import inspect
import functools
import threading
import importlib
from .client import Client
from . import api
from .exceptions import QDashHTTPError, QDashConnectionError, QDashTimeoutError, create_http_error


class APIModule:
    """Wrapper for API modules to provide convenient access with caching and proper error handling."""
    
    def __init__(self, module, client, client_instance):
        self._module = module
        self._client = client  # Raw client
        self._client_instance = client_instance  # QDashClient instance
        self._cache = {}  # Method wrapper cache
        self._lock = threading.Lock()  # Thread-safe caching
        
    def __getattr__(self, name: str):
        """Get API function with caching and proper error handling."""
        # Check cache first
        if name in self._cache:
            return self._cache[name]
            
        # Get the original function
        if not hasattr(self._module, name):
            raise AttributeError(f"'{self._module.__name__}' has no attribute '{name}'")
            
        func = getattr(self._module, name)
        
        # Only wrap callable functions that have sync_detailed or sync
        if not callable(func):
            return func
            
        # Thread-safe cache population
        with self._lock:
            # Double-check after acquiring lock
            if name in self._cache:
                return self._cache[name]
                
            wrapper = self._create_wrapper(func, name)
            self._cache[name] = wrapper
            return wrapper
    
    def __dir__(self) -> List[str]:
        """Return list of available methods for IDE autocompletion."""
        methods = []
        for attr_name in dir(self._module):
            if not attr_name.startswith('_'):
                attr = getattr(self._module, attr_name)
                if callable(attr) and (hasattr(attr, 'sync_detailed') or hasattr(attr, 'sync')):
                    methods.append(attr_name)
        return sorted(methods)
    
    def _create_wrapper(self, func, func_name: str):
        """Create optimized wrapper with proper error handling and signature preservation."""
        # Determine which method to use
        target_func = None
        if hasattr(func, 'sync_detailed'):
            target_func = func.sync_detailed
        elif hasattr(func, 'sync'):
            target_func = func.sync
        else:
            return func  # Return as-is if not a generated API function
        
        # Get original signature and create modified version (without client param)
        try:
            original_sig = inspect.signature(target_func)
            params = [p for p in original_sig.parameters.values() if p.name != 'client']
            new_sig = original_sig.replace(parameters=params)
        except (ValueError, TypeError):
            new_sig = None
        
        def wrapper(*args, **kwargs):
            """Wrapper that auto-injects client and handles errors properly."""
            try:
                # Inject client
                kwargs['client'] = self._client
                
                # Call the original function
                response = target_func(*args, **kwargs)
                
                # Handle response based on type
                return self._client_instance._handle_response(response, func_name)
                
            except Exception as e:
                # Convert known exceptions to QDash exceptions
                return self._client_instance._handle_exception(e, func_name, args, kwargs)
        
        # Preserve function metadata for better IDE support
        try:
            functools.update_wrapper(wrapper, target_func)
            if new_sig:
                wrapper.__signature__ = new_sig
            # Copy docstring if available
            if hasattr(func, '__doc__') and func.__doc__:
                wrapper.__doc__ = func.__doc__
        except (AttributeError, TypeError):
            pass  # Ignore metadata copying errors
            
        return wrapper


class QDashClient(Client):
    """Enhanced QDash client with automatic API discovery, caching, and robust error handling."""
    
    def __init__(
        self,
        base_url: str = "http://localhost:5715",
        username: Optional[str] = None,
        **kwargs
    ):
        """Initialize QDash client with sensible defaults.
        
        Args:
            base_url: QDash API base URL (default: http://localhost:5715)
            username: Username for X-Username header authentication
            **kwargs: Additional arguments passed to base Client
        """
        headers = kwargs.pop("headers", {})
        if username:
            headers["X-Username"] = username
            
        super().__init__(
            base_url=base_url,
            headers=headers,
            raise_on_unexpected_status=kwargs.pop("raise_on_unexpected_status", True),
            **kwargs
        )
        
        # Module cache and thread safety
        self._modules = {}
        self._module_lock = threading.Lock()
        self._known_modules = None  # Lazy-loaded set of available modules
        
        # Response handling configuration
        self._success_codes = {200, 201, 202, 204}  # Configurable success codes
        
    def __getattr__(self, name: str):
        """Lazy-load and cache API modules with thread safety."""
        # Special methods that should not be proxied
        if name.startswith('_') or name in ('call', 'list_endpoints', 'is_healthy'):
            raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")
        
        # Check cache first
        if name in self._modules:
            return self._modules[name]
        
        # Thread-safe module loading
        with self._module_lock:
            # Double-check after acquiring lock
            if name in self._modules:
                return self._modules[name]
            
            # Try to import the module
            try:
                module = importlib.import_module(f'qdash_client.api.{name}')
            except ImportError:
                raise AttributeError(f"No API module named '{name}' found")
            
            # Create and cache the module proxy
            proxy = APIModule(module, self, self)
            self._modules[name] = proxy
            return proxy
    
    def __dir__(self) -> List[str]:
        """Return list of available API modules for IDE autocompletion."""
        modules = ['call', 'list_endpoints', 'is_healthy']  # Always available methods
        
        # Add dynamically discovered modules
        if self._known_modules is None:
            self._discover_modules()
        
        modules.extend(sorted(self._known_modules))
        return modules
    
    def _discover_modules(self):
        """Discover available API modules without importing them all."""
        import pkgutil
        self._known_modules = set()
        
        try:
            for importer, modname, ispkg in pkgutil.iter_modules(api.__path__):
                if not modname.startswith('_'):
                    self._known_modules.add(modname)
        except (ImportError, AttributeError):
            # Fallback: use known common modules
            self._known_modules = {
                'chip', 'menu', 'calibration', 'auth', 'parameter', 
                'settings', 'execution', 'file', 'task', 'tag', 
                'device_topology', 'backend'
            }
    
    def _handle_response(self, response, func_name: str = "unknown"):
        """Handle response with proper error checking and parsing."""
        # If it's not a response object, return as-is
        if not hasattr(response, 'status_code'):
            return response
        
        # Check for success status codes
        if response.status_code in self._success_codes:
            # Return parsed response if available, otherwise the response itself
            return getattr(response, 'parsed', response)
        
        # Create and raise appropriate HTTP error
        raise create_http_error(response)
    
    def _handle_exception(self, exception: Exception, func_name: str, args, kwargs) -> None:
        """Convert known exceptions to QDash exceptions and re-raise."""
        # Convert httpx exceptions to QDash exceptions
        import httpx
        
        if isinstance(exception, httpx.TimeoutException):
            raise QDashTimeoutError(f"Request timeout in {func_name}") from exception
        elif isinstance(exception, httpx.ConnectError):
            raise QDashConnectionError(f"Connection failed in {func_name}") from exception
        elif isinstance(exception, QDashHTTPError):
            # Already a QDash error, re-raise as-is
            raise exception
        else:
            # Re-raise other exceptions unchanged
            raise exception
    
    def call(self, endpoint_path: str, *args, **kwargs) -> Any:
        """Generic method to call any API endpoint by string path.
        
        Args:
            endpoint_path: Path like 'chip.list_chips' or 'menu.get_menu_by_name'
            *args, **kwargs: Arguments to pass to the endpoint
            
        Returns:
            Parsed response data
            
        Raises:
            QDashHTTPError: For HTTP errors
            QDashConnectionError: For connection issues
            QDashTimeoutError: For timeout issues
            ValueError: For invalid endpoint paths
            
        Example:
            client.call('chip.list_chips')
            client.call('chip.fetch_chip', chip_id='64Qv1')
            client.call('menu.get_menu_by_name', name='my_menu')
        """
        try:
            # Parse the endpoint path
            parts = endpoint_path.split('.')
            if len(parts) != 2:
                raise ValueError("endpoint_path must be in format 'module.function'")
            
            module_name, func_name = parts
            
            # Get the API module and call the function
            api_module = getattr(self, module_name)
            func = getattr(api_module, func_name)
            return func(*args, **kwargs)
            
        except AttributeError as e:
            if "has no attribute" in str(e):
                raise ValueError(f"API endpoint '{endpoint_path}' not found") from e
            raise
    
    def is_healthy(self) -> bool:
        """Check if the QDash API is healthy and responding."""
        try:
            # Try a simple API call to check health
            self.call('settings.fetch_config')
            return True
        except Exception:
            return False
    
    def list_endpoints(self) -> Dict[str, List[str]]:
        """List all available API endpoints with their functions."""
        if self._known_modules is None:
            self._discover_modules()
        
        endpoints = {}
        for module_name in self._known_modules:
            try:
                # Get the module proxy (this will create it if needed)
                module_proxy = getattr(self, module_name)
                # Get the list of available methods
                methods = dir(module_proxy)
                if methods:
                    endpoints[module_name] = methods
            except (ImportError, AttributeError):
                # Skip modules that can't be loaded
                continue
                
        return endpoints
    
    def configure_success_codes(self, codes: Set[int]) -> None:
        """Configure which HTTP status codes should be considered successful.
        
        Args:
            codes: Set of HTTP status codes to treat as successful
        """
        self._success_codes = set(codes)
    
    def __repr__(self) -> str:
        return f"QDashClient(base_url='{self._base_url}', modules_cached={len(self._modules)})"