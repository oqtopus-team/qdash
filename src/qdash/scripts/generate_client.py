#!/usr/bin/env python3
"""Generate Python client from QDash OpenAPI specification using openapi-python-client."""

import json
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests


@dataclass
class ClientConfig:
    """Configuration for client generation."""

    api_port: str = "5715"
    api_host: str = "localhost"
    client_name: str = "QDashClient"
    package_name: str = "qdash_client"
    output_dir: Optional[str] = None

    @classmethod
    def from_env(cls) -> "ClientConfig":
        """Create config from environment variables."""
        return cls(
            api_port=os.getenv("API_PORT", "5715"),
            api_host=os.getenv("API_HOST", "localhost"),
            client_name=os.getenv("CLIENT_NAME", "QDashClient"),
            package_name=os.getenv("PACKAGE_NAME", "qdash_client"),
            output_dir=os.getenv("CLIENT_OUTPUT_DIR"),
        )

    @property
    def api_url(self) -> str:
        """Get the full API URL."""
        return f"http://{self.api_host}:{self.api_port}"

    @property
    def openapi_url(self) -> str:
        """Get the OpenAPI spec URL."""
        return f"{self.api_url}/openapi.json"


def validate_api_url(url: str) -> bool:
    """Validate API URL format and prevent injection."""
    try:
        parsed = urlparse(url)
        return parsed.scheme in ["http", "https"] and bool(parsed.netloc)
    except Exception:
        return False


def validate_api_health(api_url: str) -> bool:
    """Validate that the API is healthy and accessible."""
    try:
        # Try health endpoint first, fallback to docs
        for endpoint in ["/health", "/docs", ""]:
            try:
                response = requests.get(f"{api_url}{endpoint}", timeout=10)
                if response.status_code == 200:
                    return True
            except requests.RequestException:
                continue
        return False
    except Exception:
        return False


def validate_openapi_spec(spec: dict) -> bool:
    """Validate the OpenAPI specification structure."""
    required_fields = ["openapi", "info", "paths"]
    return all(field in spec for field in required_fields)


def fetch_openapi_spec(url: str, max_retries: int = 3) -> dict:
    """Fetch OpenAPI spec with retries and better error handling."""
    for attempt in range(max_retries):
        try:
            print(f"📡 Fetching OpenAPI spec from: {url} (attempt {attempt + 1}/{max_retries})")
            response = requests.get(url, timeout=30, headers={"Accept": "application/json"})
            response.raise_for_status()

            spec = response.json()

            if not validate_openapi_spec(spec):
                raise ValueError("Invalid OpenAPI specification structure")

            print(f"✅ Successfully fetched OpenAPI spec (version: {spec.get('openapi', 'unknown')})")
            return spec

        except requests.exceptions.ConnectionError as e:
            if attempt < max_retries - 1:
                wait_time = 2**attempt
                print(f"⚠️  Connection failed, retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                raise ConnectionError(f"Failed to connect to API after {max_retries} attempts: {e}")
        except requests.exceptions.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON response from API: {e}")
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                raise ValueError(
                    f"OpenAPI spec not found at {url}. Make sure the API is running and exposes /openapi.json"
                )
            else:
                raise ValueError(f"HTTP error {e.response.status_code}: {e}")


def check_dependencies() -> bool:
    """Check if required tools are available."""
    try:
        result = subprocess.run(["openapi-python-client", "--version"], capture_output=True, check=True, text=True)
        print(f"✅ Found openapi-python-client: {result.stdout.strip()}")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def generate_client(config: ClientConfig) -> None:
    """Generate Python client using openapi-python-client."""
    if not validate_api_url(config.api_url):
        raise ValueError(f"Invalid API URL: {config.api_url}")

    if not validate_api_health(config.api_url):
        print(f"⚠️  API health check failed for {config.api_url}")
        print("   Proceeding anyway, but the API might not be fully ready...")

    if not check_dependencies():
        raise RuntimeError("openapi-python-client not found. Install with: " "pip install openapi-python-client")

    # Determine output directory - integrate into existing qdash package
    project_root = Path(__file__).parent.parent.parent.parent
    if config.output_dir:
        output_dir = Path(config.output_dir)
    else:
        # Generate into root level qdash_client package
        output_dir = project_root / "qdash_client"

    print(f"🎯 Target output directory: {output_dir}")

    # Fetch OpenAPI spec
    openapi_spec = fetch_openapi_spec(config.openapi_url)

    # Backup existing important files to prevent overwrite
    backups = {}
    
    # Read files to protect from .qdash-preserve file
    files_to_protect = [
        project_root / ".gitignore",
        project_root / "pyproject.toml"
    ]
    
    # Add files from preserve list
    preserve_file = output_dir / ".qdash-preserve"
    if preserve_file.exists():
        try:
            preserve_content = preserve_file.read_text(encoding='utf-8')
            for line in preserve_content.split('\n'):
                line = line.strip()
                if line and not line.startswith('#'):
                    # Handle relative paths from qdash_client directory
                    if line.startswith('../'):
                        file_path = output_dir / line
                    else:
                        file_path = output_dir / line
                    files_to_protect.append(file_path.resolve())
            print(f"📋 Loaded {len(files_to_protect)-2} files from preserve list")
        except Exception as e:
            print(f"⚠️  Failed to read preserve file: {e}")
    else:
        # Fallback to hardcoded list
        files_to_protect.extend([
            output_dir / "src" / "qdash_client" / "qdash.py",
            output_dir / "src" / "qdash_client" / "exceptions.py",
            project_root / "examples" / "enhanced_client_demo.py",
            project_root / "examples" / "automatic_api_demo.py",
            project_root / "examples" / "usage_comparison.md"
        ])
    
    print("🛡️  Backing up enhanced files...")
    for file_path in files_to_protect:
        if file_path.exists():
            try:
                backups[file_path] = file_path.read_text(encoding='utf-8')
                print(f"   ✅ Backed up: {file_path.relative_to(project_root)}")
            except Exception as e:
                print(f"   ⚠️  Failed to backup {file_path}: {e}")
    
    # Legacy backup variables for compatibility
    gitignore_backup = backups.get(project_root / ".gitignore")
    pyproject_backup = backups.get(project_root / "pyproject.toml")

    # Write spec to temporary file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(openapi_spec, f, indent=2)
        spec_file = f.name

    try:
        # Generate client using openapi-python-client
        config_file = project_root / ".openapi-python-client.yaml"
        cmd = [
            "openapi-python-client",
            "generate",
            "--path",
            spec_file,
            "--output-path",
            str(project_root),  # Generate in project root
            "--config",
            str(config_file),
            "--overwrite",
        ]

        print(f"🔧 Running: {' '.join(cmd)}")
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)

        if result.stdout:
            print("📄 Generator output:")
            print(result.stdout)
        if result.stderr:
            print("⚠️  Generator warnings:")
            print(result.stderr)

        # Validate generated client structure
        expected_files = [
            output_dir / "__init__.py",
            output_dir / "pyproject.toml",
            output_dir / "README.md",
            output_dir / "py.typed",
        ]

        missing_files = [f for f in expected_files if not f.exists()]
        if missing_files:
            print(f"⚠️  Some expected files are missing: {missing_files}")

        # Restore all backed up files
        print("🔄 Restoring enhanced files...")
        for file_path, content in backups.items():
            try:
                # Ensure parent directory exists
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(content, encoding='utf-8')
                print(f"   ✅ Restored: {file_path.relative_to(project_root)}")
            except Exception as e:
                print(f"   ❌ Failed to restore {file_path}: {e}")
                
        print("✨ Enhanced client files preserved!")

        print("✅ Python client generated successfully!")
        print(f"📁 Location: {output_dir}")
        print()
        print("🚀 To use the client:")
        print()
        print("   Option 1: Install standalone (recommended for client-only usage):")
        print(f"      pip install {output_dir}")
        print("      # Or from GitHub:")
        print("      pip install git+https://github.com/oqtopus-team/qdash.git#subdirectory=qdash_client")
        print()
        print("   Option 2: Use as part of qdash package:")
        print("      pip install git+https://github.com/oqtopus-team/qdash.git")
        print()
        print("   Import and use:")
        print("      # Standalone installation:")
        print("      from qdash_client import Client")
        print("      from qdash_client.api.chip import get_chips")
        print()
        print("      # Or when installed with full qdash:")
        print("      from qdash.client import Client")
        print("      from qdash.client.api.chip import get_chips")
        print()
        print(f"      client = Client(base_url='{config.api_url}')")
        print("      response = get_chips.sync_detailed(client=client)")
        print("      if response.status_code == 200:")
        print("          chips = response.parsed")
        print()
        print("✨ Features:")
        print("   • httpx for HTTP client")
        print("   • attrs models with type hints")
        print("   • Both sync and async support")
        print("   • Comprehensive error handling")
        print("   • Auto-generated from OpenAPI spec")

    except subprocess.CalledProcessError as e:
        print(f"❌ Error generating client: {e}")
        if e.stdout:
            print("📄 Output:", e.stdout)
        if e.stderr:
            print("❌ Error details:", e.stderr)
        raise
    finally:
        # Clean up temporary file
        try:
            os.unlink(spec_file)
        except OSError:
            pass  # Ignore cleanup errors


def main():
    """Main entry point for client generation."""
    try:
        print("🚀 QDash Python Client Generator")
        print("=" * 40)

        config = ClientConfig.from_env()

        print("📋 Configuration:")
        print(f"   • API URL: {config.api_url}")
        print(f"   • Package: {config.package_name}")
        print(f"   • Client: {config.client_name}")
        print("   • Generator: openapi-python-client (1.6k⭐)")
        print()

        generate_client(config)

    except KeyboardInterrupt:
        print("\n❌ Generation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Generation failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
