#!/usr/bin/env python3
"""
QDash Python Client Configuration Examples

This demonstrates various client configurations for different environments
and use cases including production, development, testing, and advanced scenarios.
"""

import os
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any
import logging

try:
    from qdash.client import Client, AuthenticatedClient
    from qdash.client.errors import UnexpectedStatus
except ImportError as e:
    print("❌ QDash client not found!")
    print("First generate the client: generate-python-client")
    print("Or install QDash with client dependencies: pip install 'git+https://github.com/oqtopus-team/qdash.git[client]'")
    print(f"Error details: {e}")
    exit(1)


class QDashClientConfig:
    """Configuration manager for QDash clients in different environments."""

    @staticmethod
    def development_client() -> Client:
        """
        Development environment client configuration.
        
        Features:
        - Local API server
        - Extended timeouts for debugging
        - Detailed error reporting
        """
        return Client(
            base_url=os.getenv("QDASH_API_URL", "http://localhost:5715"),
            timeout=30.0,  # Extended timeout for development
            raise_on_unexpected_status=True,  # Raise exceptions for debugging
        )

    @staticmethod
    def production_client(api_token: str, username: str) -> AuthenticatedClient:
        """
        Production environment client configuration.
        
        Features:
        - HTTPS endpoint
        - Authentication required
        - Optimized timeouts
        - Custom headers for tracking
        
        Args:
            api_token: Production API token
            username: Username for X-Username header
        """
        return AuthenticatedClient(
            base_url=os.getenv("QDASH_API_URL", "https://qdash.example.com"),
            token=api_token,
            headers={
                "X-Username": username,
                "X-Client-Version": "1.0.0",
                "X-Environment": "production",
            },
            timeout=15.0,  # Production timeout
            raise_on_unexpected_status=False,  # Handle errors gracefully
        )

    @staticmethod
    def testing_client() -> Client:
        """
        Testing environment client configuration.
        
        Features:
        - Mock/test API endpoints
        - Short timeouts for fast tests
        - No authentication needed
        """
        return Client(
            base_url=os.getenv("QDASH_TEST_URL", "http://localhost:5716"),
            timeout=5.0,  # Short timeout for tests
            raise_on_unexpected_status=False,
        )

    @staticmethod
    def staging_client(api_token: str) -> AuthenticatedClient:
        """
        Staging environment client configuration.
        
        Features:
        - Staging API endpoint
        - Authentication with staging token
        - Moderate timeouts
        """
        return AuthenticatedClient(
            base_url=os.getenv("QDASH_STAGING_URL", "https://staging.qdash.example.com"),
            token=api_token,
            headers={
                "X-Environment": "staging",
                "X-Client-Source": "python-client",
            },
            timeout=20.0,
        )

    @staticmethod
    def custom_client(
        base_url: str,
        timeout: float = 10.0,
        custom_headers: Optional[Dict[str, str]] = None,
        auth_token: Optional[str] = None,
        username: Optional[str] = None,
    ) -> Client:
        """
        Custom client configuration for specific needs.
        
        Args:
            base_url: API base URL
            timeout: Request timeout in seconds
            custom_headers: Additional headers to send
            auth_token: Optional authentication token
            username: Optional username for X-Username header
        """
        headers = custom_headers or {}
        
        if username:
            headers["X-Username"] = username
            
        if auth_token:
            return AuthenticatedClient(
                base_url=base_url,
                token=auth_token,
                headers=headers,
                timeout=timeout,
            )
        else:
            return Client(
                base_url=base_url,
                timeout=timeout,
                headers=headers,
            )


class ClientWithRetryLogic:
    """Enhanced client wrapper with built-in retry logic and error handling."""

    def __init__(self, client: Client, max_retries: int = 3):
        self.client = client
        self.max_retries = max_retries
        self.logger = logging.getLogger(__name__)

    async def request_with_retry(self, request_func, *args, **kwargs):
        """
        Execute a request with exponential backoff retry logic.
        
        Args:
            request_func: The client method to call
            *args, **kwargs: Arguments to pass to the client method
        """
        last_exception = None
        
        for attempt in range(self.max_retries):
            try:
                response = await request_func(*args, **kwargs)
                
                # Handle different status codes
                if response.status_code == 200:
                    return response
                elif response.status_code == 429:  # Rate limited
                    retry_after = response.headers.get("Retry-After", "1")
                    wait_time = min(int(retry_after), 60)  # Cap at 60 seconds
                    self.logger.warning(f"Rate limited, waiting {wait_time}s")
                    await asyncio.sleep(wait_time)
                elif response.status_code in [503, 502, 504]:  # Service issues
                    if attempt < self.max_retries - 1:
                        wait_time = (2 ** attempt) + 1  # Exponential backoff
                        self.logger.warning(f"Service unavailable, retrying in {wait_time}s")
                        await asyncio.sleep(wait_time)
                    else:
                        return response
                else:
                    # For other status codes, don't retry
                    return response
                    
            except (ConnectionError, TimeoutError) as e:
                last_exception = e
                if attempt < self.max_retries - 1:
                    wait_time = (2 ** attempt) + 1
                    self.logger.warning(f"Connection failed, retrying in {wait_time}s: {e}")
                    await asyncio.sleep(wait_time)
                else:
                    raise e
            except Exception as e:
                self.logger.error(f"Unexpected error: {e}")
                raise e
        
        if last_exception:
            raise last_exception


class EnvironmentAwareClient:
    """Client that automatically adapts to different environments."""

    def __init__(self):
        self.environment = os.getenv("ENVIRONMENT", "development").lower()
        self.client = self._create_client()

    def _create_client(self) -> Client:
        """Create appropriate client based on environment."""
        if self.environment == "production":
            api_token = os.getenv("QDASH_API_TOKEN")
            username = os.getenv("QDASH_USERNAME", "python-client")
            if not api_token:
                raise ValueError("QDASH_API_TOKEN required for production")
            return QDashClientConfig.production_client(api_token, username)
        
        elif self.environment == "staging":
            api_token = os.getenv("QDASH_STAGING_TOKEN")
            if not api_token:
                raise ValueError("QDASH_STAGING_TOKEN required for staging")
            return QDashClientConfig.staging_client(api_token)
        
        elif self.environment == "testing":
            return QDashClientConfig.testing_client()
        
        else:  # development
            return QDashClientConfig.development_client()

    def get_client(self) -> Client:
        """Get the configured client."""
        return self.client


def load_config_from_file(config_path: str) -> Dict[str, Any]:
    """
    Load client configuration from a JSON or YAML file.
    
    Args:
        config_path: Path to configuration file
        
    Returns:
        Configuration dictionary
    """
    config_file = Path(config_path)
    
    if not config_file.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    if config_file.suffix.lower() == '.json':
        import json
        return json.load(config_file.open())
    elif config_file.suffix.lower() in ['.yaml', '.yml']:
        import yaml
        return yaml.safe_load(config_file.open())
    else:
        raise ValueError(f"Unsupported config file format: {config_file.suffix}")


async def example_configuration_usage():
    """Demonstrate various client configurations."""
    print("🌟 QDash Client Configuration Examples")
    print("=" * 50)

    # Example 1: Development client
    print("\n🛠️  Development Configuration")
    dev_client = QDashClientConfig.development_client()
    print(f"Base URL: {dev_client.base_url}")
    print(f"Timeout: {dev_client.timeout}s")

    # Example 2: Production client (with mock credentials)
    print("\n🚀 Production Configuration")
    try:
        # In real usage, these would come from secure environment variables
        prod_client = QDashClientConfig.production_client(
            api_token="prod-token-123",
            username="quantum-engineer"
        )
        print(f"Base URL: {prod_client.base_url}")
        print(f"Headers: {prod_client.headers}")
    except Exception as e:
        print(f"Production config error: {e}")

    # Example 3: Environment-aware client
    print("\n🌍 Environment-Aware Configuration")
    try:
        env_client = EnvironmentAwareClient()
        print(f"Environment: {env_client.environment}")
        print(f"Client type: {type(env_client.get_client()).__name__}")
    except Exception as e:
        print(f"Environment config error: {e}")

    # Example 4: Custom configuration
    print("\n🎛️  Custom Configuration")
    custom_client = QDashClientConfig.custom_client(
        base_url="https://custom.qdash.example.com",
        timeout=25.0,
        custom_headers={
            "X-Custom-Header": "custom-value",
            "X-Lab-ID": "quantum-lab-1",
        },
        username="custom-user"
    )
    print(f"Base URL: {custom_client.base_url}")
    print(f"Timeout: {custom_client.timeout}s")
    if hasattr(custom_client, 'headers'):
        print(f"Custom headers: {custom_client.headers}")

    # Example 5: Client with retry logic
    print("\n🔄 Client with Retry Logic")
    base_client = QDashClientConfig.development_client()
    retry_client = ClientWithRetryLogic(base_client, max_retries=3)
    print(f"Max retries: {retry_client.max_retries}")

    print("\n✨ Configuration examples completed!")
    print("\n📖 Key Configuration Features:")
    print("   • Environment-specific settings")
    print("   • Authentication and security")
    print("   • Timeout and retry configuration")
    print("   • Custom headers and metadata")
    print("   • File-based configuration support")


if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Run examples
    asyncio.run(example_configuration_usage())