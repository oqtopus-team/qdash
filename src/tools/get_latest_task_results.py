#!/usr/bin/env python3
"""Script to get latest task results and JSON figures from QDash API.

This script replicates the UI chip page functionality for fetching
the latest task results by chip_id, date, and task name.

Environment Variables (.env file):
    QDASH_API_TOKEN          - API access token for Bearer authentication
    CF-Access-Client-ID      - Cloudflare Access Client ID
    CF-Access-Client-Secret  - Cloudflare Access Client Secret
    CF-Access-Domain         - Cloudflare Access Domain (e.g., qdash-dev.example.com)
                               Auto-constructs base URL as https://{domain}/api

Usage:
    # With .env file configured, just run:
    python get_latest_task_results.py --chip-id 64Q --task CheckRabi

    # Get latest results (table format) - local API
    python get_latest_task_results.py --chip-id 64Q --task CheckRabi --token YOUR_API_TOKEN

    # Override base URL explicitly
    python get_latest_task_results.py --chip-id 64Q --task CheckRabi \\
        --base-url "https://qdash-dev.example.com/api"

    # Get historical results for a specific date
    python get_latest_task_results.py --chip-id 64Q --task CheckRabi --date 20241213

    # Get coupling task results
    python get_latest_task_results.py --chip-id 64Q --task CheckCZ --type coupling

    # Output as JSON
    python get_latest_task_results.py --chip-id 64Q --task CheckRabi --output json

    # Download JSON figures to a directory
    python get_latest_task_results.py --chip-id 64Q --task CheckRabi --download-figures ./figures

    # Download JSON figures for specific qubit IDs
    python get_latest_task_results.py --chip-id 64Q --task CheckRabi --download-figures ./figures --qids 0,1,2
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Literal

import requests
from dotenv import load_dotenv

# Load .env file from project root
load_dotenv()


def get_api_base_url() -> str:
    """Get API base URL from environment or default.

    Priority:
    1. API_BASE_URL environment variable
    2. CF-Access-Domain (constructs https://{domain}/api)
    3. Default localhost with API_PORT
    """
    if os.getenv("API_BASE_URL"):
        return os.getenv("API_BASE_URL")

    cf_domain = os.getenv("CF_ACCESS_DOMAIN") or os.getenv("CF-Access-Domain")
    if cf_domain:
        # Remove trailing slash if present
        cf_domain = cf_domain.rstrip("/")
        # Add https:// if not present
        if not cf_domain.startswith("http"):
            cf_domain = f"https://{cf_domain}"
        return f"{cf_domain}/api"

    api_port = os.getenv("API_PORT", "2004")
    return f"http://localhost:{api_port}"


def _build_headers(
    token: str | None = None,
    project_id: str | None = None,
    cf_client_id: str | None = None,
    cf_client_secret: str | None = None,
) -> dict:
    """Build request headers with authentication.

    Parameters
    ----------
    token : str | None
        QDash API access token (Bearer token)
    project_id : str | None
        Project ID header
    cf_client_id : str | None
        Cloudflare Access Client ID (for external access via Cloudflare)
    cf_client_secret : str | None
        Cloudflare Access Client Secret

    """
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if project_id:
        headers["X-Project-Id"] = project_id
    # Cloudflare Access Service Token headers
    if cf_client_id:
        headers["CF-Access-Client-Id"] = cf_client_id
    if cf_client_secret:
        headers["CF-Access-Client-Secret"] = cf_client_secret
    return headers


def get_latest_qubit_task_results(
    base_url: str,
    chip_id: str,
    task: str,
    headers: dict,
) -> dict:
    """Get latest qubit task results."""
    url = f"{base_url}/task-results/qubits/latest"
    params = {"chip_id": chip_id, "task": task}
    response = requests.get(url, params=params, headers=headers)
    response.raise_for_status()
    return response.json()


def get_historical_qubit_task_results(
    base_url: str,
    chip_id: str,
    task: str,
    date: str,
    headers: dict,
) -> dict:
    """Get historical qubit task results for a specific date."""
    url = f"{base_url}/task-results/qubits/history"
    params = {"chip_id": chip_id, "task": task, "date": date}
    response = requests.get(url, params=params, headers=headers)
    response.raise_for_status()
    return response.json()


def get_latest_coupling_task_results(
    base_url: str,
    chip_id: str,
    task: str,
    headers: dict,
) -> dict:
    """Get latest coupling task results."""
    url = f"{base_url}/task-results/couplings/latest"
    params = {"chip_id": chip_id, "task": task}
    response = requests.get(url, params=params, headers=headers)
    response.raise_for_status()
    return response.json()


def get_historical_coupling_task_results(
    base_url: str,
    chip_id: str,
    task: str,
    date: str,
    headers: dict,
) -> dict:
    """Get historical coupling task results for a specific date."""
    url = f"{base_url}/task-results/couplings/history"
    params = {"chip_id": chip_id, "task": task, "date": date}
    response = requests.get(url, params=params, headers=headers)
    response.raise_for_status()
    return response.json()


def get_figure_content(
    base_url: str,
    figure_path: str,
    headers: dict,
) -> bytes:
    """Get figure file content from API."""
    url = f"{base_url}/executions/figure"
    params = {"path": figure_path}
    response = requests.get(url, params=params, headers=headers)
    response.raise_for_status()
    return response.content


def get_task_results(
    chip_id: str,
    task: str,
    date: str | None = None,
    result_type: Literal["qubit", "coupling"] = "qubit",
    base_url: str | None = None,
    token: str | None = None,
    project_id: str | None = None,
    cf_client_id: str | None = None,
    cf_client_secret: str | None = None,
) -> dict:
    """Get task results from API.

    Parameters
    ----------
    chip_id : str
        Chip ID (e.g., "64Q")
    task : str
        Task name (e.g., "CheckRabi", "CheckRamsey")
    date : str | None
        Date in YYYYMMDD format. If None, get latest results.
    result_type : Literal["qubit", "coupling"]
        Type of results to fetch
    base_url : str | None
        API base URL. If None, uses environment variable or default.
    token : str | None
        API access token for Bearer authentication.
        Can also be set via QDASH_API_TOKEN environment variable.
    project_id : str | None
        Project ID for API request
    cf_client_id : str | None
        Cloudflare Access Client ID. Can also be set via CF_ACCESS_CLIENT_ID env var.
    cf_client_secret : str | None
        Cloudflare Access Client Secret. Can also be set via CF_ACCESS_CLIENT_SECRET env var.

    Returns
    -------
    dict
        Task results response from API

    """
    if base_url is None:
        base_url = get_api_base_url()

    if token is None:
        token = os.getenv("QDASH_API_TOKEN")
    if cf_client_id is None:
        cf_client_id = os.getenv("CF_ACCESS_CLIENT_ID") or os.getenv("CF-Access-Client-ID")
    if cf_client_secret is None:
        cf_client_secret = os.getenv("CF_ACCESS_CLIENT_SECRET") or os.getenv("CF-Access-Client-Secret")

    headers = _build_headers(
        token=token,
        project_id=project_id,
        cf_client_id=cf_client_id,
        cf_client_secret=cf_client_secret,
    )

    is_latest = date is None

    if result_type == "qubit":
        if is_latest:
            return get_latest_qubit_task_results(base_url, chip_id, task, headers)
        else:
            return get_historical_qubit_task_results(base_url, chip_id, task, date, headers)
    else:
        if is_latest:
            return get_latest_coupling_task_results(base_url, chip_id, task, headers)
        else:
            return get_historical_coupling_task_results(base_url, chip_id, task, date, headers)


def download_json_figures(
    results: dict,
    output_dir: str | Path,
    base_url: str | None = None,
    token: str | None = None,
    project_id: str | None = None,
    qids: list[str] | None = None,
    cf_client_id: str | None = None,
    cf_client_secret: str | None = None,
) -> dict[str, list[Path]]:
    """Download JSON figures for task results.

    Parameters
    ----------
    results : dict
        Task results from get_task_results()
    output_dir : str | Path
        Directory to save JSON figures
    base_url : str | None
        API base URL
    token : str | None
        API access token for Bearer authentication.
        Can also be set via QDASH_API_TOKEN environment variable.
    project_id : str | None
        Project ID for API request
    qids : list[str] | None
        Optional list of qubit IDs to filter. If None, download all.
    cf_client_id : str | None
        Cloudflare Access Client ID
    cf_client_secret : str | None
        Cloudflare Access Client Secret

    Returns
    -------
    dict[str, list[Path]]
        Mapping of qid to list of downloaded file paths

    """
    if base_url is None:
        base_url = get_api_base_url()

    if token is None:
        token = os.getenv("QDASH_API_TOKEN")
    if cf_client_id is None:
        cf_client_id = os.getenv("CF_ACCESS_CLIENT_ID") or os.getenv("CF-Access-Client-ID")
    if cf_client_secret is None:
        cf_client_secret = os.getenv("CF_ACCESS_CLIENT_SECRET") or os.getenv("CF-Access-Client-Secret")

    headers = _build_headers(
        token=token,
        project_id=project_id,
        cf_client_id=cf_client_id,
        cf_client_secret=cf_client_secret,
    )

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    task_name = results.get("task_name", "unknown")
    result_data = results.get("result", {})

    downloaded: dict[str, list[Path]] = {}

    for qid, task_result in result_data.items():
        if qids is not None and qid not in qids:
            continue

        json_figure_paths = task_result.get("json_figure_path", [])
        if not json_figure_paths:
            continue

        if isinstance(json_figure_paths, str):
            json_figure_paths = [json_figure_paths]

        downloaded[qid] = []

        for idx, figure_path in enumerate(json_figure_paths):
            if not figure_path:
                continue

            try:
                content = get_figure_content(base_url, figure_path, headers)

                # Create filename: task_qid_idx.json
                suffix = f"_{idx}" if len(json_figure_paths) > 1 else ""
                filename = f"{task_name}_{qid}{suffix}.json"
                output_path = output_dir / filename

                output_path.write_bytes(content)
                downloaded[qid].append(output_path)
                print(f"Downloaded: {output_path}")

            except requests.exceptions.HTTPError as e:
                print(f"Failed to download figure for {qid}: {e}", file=sys.stderr)
            except Exception as e:
                print(f"Error downloading figure for {qid}: {e}", file=sys.stderr)

    return downloaded


def get_json_figures(
    chip_id: str,
    task: str,
    date: str | None = None,
    result_type: Literal["qubit", "coupling"] = "qubit",
    base_url: str | None = None,
    token: str | None = None,
    project_id: str | None = None,
    qids: list[str] | None = None,
    cf_client_id: str | None = None,
    cf_client_secret: str | None = None,
) -> dict[str, list[dict]]:
    """Get JSON figure data for task results.

    Parameters
    ----------
    chip_id : str
        Chip ID (e.g., "64Q")
    task : str
        Task name (e.g., "CheckRabi", "CheckRamsey")
    date : str | None
        Date in YYYYMMDD format. If None, get latest results.
    result_type : Literal["qubit", "coupling"]
        Type of results to fetch
    base_url : str | None
        API base URL
    token : str | None
        API access token for Bearer authentication.
        Can also be set via QDASH_API_TOKEN environment variable.
    project_id : str | None
        Project ID for API request
    qids : list[str] | None
        Optional list of qubit IDs to filter. If None, get all.
    cf_client_id : str | None
        Cloudflare Access Client ID
    cf_client_secret : str | None
        Cloudflare Access Client Secret

    Returns
    -------
    dict[str, list[dict]]
        Mapping of qid to list of Plotly figure JSON data

    """
    if base_url is None:
        base_url = get_api_base_url()

    if token is None:
        token = os.getenv("QDASH_API_TOKEN")
    if cf_client_id is None:
        cf_client_id = os.getenv("CF_ACCESS_CLIENT_ID")
    if cf_client_secret is None:
        cf_client_secret = os.getenv("CF_ACCESS_CLIENT_SECRET")

    headers = _build_headers(
        token=token,
        project_id=project_id,
        cf_client_id=cf_client_id,
        cf_client_secret=cf_client_secret,
    )

    results = get_task_results(
        chip_id=chip_id,
        task=task,
        date=date,
        result_type=result_type,
        base_url=base_url,
        token=token,
        project_id=project_id,
        cf_client_id=cf_client_id,
        cf_client_secret=cf_client_secret,
    )

    result_data = results.get("result", {})
    figures: dict[str, list[dict]] = {}

    for qid, task_result in result_data.items():
        if qids is not None and qid not in qids:
            continue

        json_figure_paths = task_result.get("json_figure_path", [])
        if not json_figure_paths:
            continue

        if isinstance(json_figure_paths, str):
            json_figure_paths = [json_figure_paths]

        figures[qid] = []

        for figure_path in json_figure_paths:
            if not figure_path:
                continue

            try:
                content = get_figure_content(base_url, figure_path, headers)
                figure_data = json.loads(content)
                figures[qid].append(figure_data)
            except Exception as e:
                print(f"Error loading figure for {qid}: {e}", file=sys.stderr)

    return figures


def format_results_table(results: dict) -> str:
    """Format results as a readable table."""
    lines = []
    task_name = results.get("task_name", "Unknown")
    lines.append(f"Task: {task_name}")
    lines.append("=" * 100)

    result_data = results.get("result", {})
    if not result_data:
        lines.append("No results found.")
        return "\n".join(lines)

    # Header
    lines.append(f"{'ID':<10} {'Status':<12} {'Start':<20} {'End':<20} {'Figures':<10}")
    lines.append("-" * 100)

    for qid, task_result in sorted(result_data.items()):
        status = task_result.get("status", "N/A")
        start_at = task_result.get("start_at", "N/A")
        end_at = task_result.get("end_at", "N/A")

        # Count JSON figures
        json_figures = task_result.get("json_figure_path", [])
        if isinstance(json_figures, str):
            json_figures = [json_figures] if json_figures else []
        num_figures = len([f for f in json_figures if f])

        # Truncate timestamps for display
        if start_at and start_at != "N/A":
            start_at = start_at[:19] if len(start_at) > 19 else start_at
        if end_at and end_at != "N/A":
            end_at = end_at[:19] if len(end_at) > 19 else end_at

        lines.append(f"{qid:<10} {status:<12} {start_at:<20} {end_at:<20} {num_figures:<10}")

    # Summary
    total = len(result_data)
    completed = sum(1 for r in result_data.values() if r.get("status") == "completed")
    with_figures = sum(
        1
        for r in result_data.values()
        if r.get("json_figure_path") and any(r.get("json_figure_path", []))
    )
    lines.append("-" * 100)
    lines.append(f"Total: {total}, Completed: {completed}, With JSON figures: {with_figures}")

    return "\n".join(lines)


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Get latest task results and JSON figures from QDash API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--chip-id",
        required=True,
        help="Chip ID (e.g., 64Q)",
    )
    parser.add_argument(
        "--task",
        required=True,
        help="Task name (e.g., CheckRabi, CheckRamsey)",
    )
    parser.add_argument(
        "--date",
        default=None,
        help="Date in YYYYMMDD format (optional, defaults to latest)",
    )
    parser.add_argument(
        "--type",
        choices=["qubit", "coupling"],
        default="qubit",
        help="Result type: qubit or coupling (default: qubit)",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="API base URL (default: http://localhost:$API_PORT)",
    )
    parser.add_argument(
        "--token",
        default=None,
        help="API access token (or set QDASH_API_TOKEN env var)",
    )
    parser.add_argument(
        "--project-id",
        default=None,
        help="Project ID for API request",
    )
    parser.add_argument(
        "--output",
        choices=["json", "table"],
        default="table",
        help="Output format (default: table)",
    )
    parser.add_argument(
        "--download-figures",
        metavar="DIR",
        nargs="?",
        const=".tmp/figures",
        default=None,
        help="Download JSON figures to specified directory (default: .tmp/figures)",
    )
    parser.add_argument(
        "--qids",
        default=None,
        help="Comma-separated list of qubit/coupling IDs to filter (e.g., 0,1,2)",
    )
    parser.add_argument(
        "--cf-client-id",
        default=None,
        help="Cloudflare Access Client ID (or set CF_ACCESS_CLIENT_ID env var)",
    )
    parser.add_argument(
        "--cf-client-secret",
        default=None,
        help="Cloudflare Access Client Secret (or set CF_ACCESS_CLIENT_SECRET env var)",
    )

    args = parser.parse_args()

    qids = None
    if args.qids:
        qids = [q.strip() for q in args.qids.split(",")]

    try:
        results = get_task_results(
            chip_id=args.chip_id,
            task=args.task,
            date=args.date,
            result_type=args.type,
            base_url=args.base_url,
            token=args.token,
            project_id=args.project_id,
            cf_client_id=args.cf_client_id,
            cf_client_secret=args.cf_client_secret,
        )

        if args.output == "json":
            print(json.dumps(results, indent=2, ensure_ascii=False))
        else:
            print(format_results_table(results))

        # Download figures if requested
        if args.download_figures:
            print(f"\nDownloading JSON figures to: {args.download_figures}")
            downloaded = download_json_figures(
                results=results,
                output_dir=args.download_figures,
                base_url=args.base_url,
                token=args.token,
                project_id=args.project_id,
                qids=qids,
                cf_client_id=args.cf_client_id,
                cf_client_secret=args.cf_client_secret,
            )
            total_files = sum(len(files) for files in downloaded.values())
            print(f"\nDownloaded {total_files} files for {len(downloaded)} qubits/couplings")

    except requests.exceptions.HTTPError as e:
        print(f"HTTP Error: {e}", file=sys.stderr)
        if e.response is not None:
            print(f"Response: {e.response.text}", file=sys.stderr)
        sys.exit(1)
    except requests.exceptions.ConnectionError as e:
        print(f"Connection Error: {e}", file=sys.stderr)
        print("Make sure the QDash API server is running.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
