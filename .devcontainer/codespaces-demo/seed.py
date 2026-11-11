"""Seed the Fake backend demo through the public API.

demo.sh runs this inside the api container, which has the initial administrator
credentials from .env. It creates a virtual 64-qubit chip, saves the Fake Backend
Calibration template as a flow, and starts one run on four MUXes, so Execution,
Task Results and Chip have data to explore. Each step is skipped when its result
already exists, so the script is safe to rerun. Only the standard library is used.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

BASE_URL = os.environ.get("QDASH_DEMO_BASE_URL", "http://caddy/api")
if urllib.parse.urlsplit(BASE_URL).scheme not in {"http", "https"}:
    sys.exit(f"[qdash-demo] QDASH_DEMO_BASE_URL must be an http(s) URL: {BASE_URL}")
CHIP_ID = "demo-64q"
FLOW_NAME = "demo_fake_calibration"
TEMPLATE_ID = "fake_calibration"
# 16 of the 64 qubits keep the first run short; run the rest from the UI.
SEED_MUX_IDS = [0, 1, 2, 3]


def request(
    method: str,
    path: str,
    *,
    body: dict[str, Any] | None = None,
    form: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, Any]:
    """Send one request and return the status code and decoded JSON body."""
    data = None
    all_headers = dict(headers or {})
    if body is not None:
        data = json.dumps(body).encode()
        all_headers["Content-Type"] = "application/json"
    elif form is not None:
        data = urllib.parse.urlencode(form).encode()
        all_headers["Content-Type"] = "application/x-www-form-urlencoded"
    # BASE_URL is checked to be http(s) at import.
    url = BASE_URL + path
    req = urllib.request.Request(url, data=data, method=method, headers=all_headers)  # noqa: S310
    try:
        with urllib.request.urlopen(req, timeout=60) as response:  # noqa: S310
            status, raw = response.status, response.read()
    except urllib.error.HTTPError as error:
        status, raw = error.code, error.read()
    try:
        return status, json.loads(raw) if raw else None
    except json.JSONDecodeError:
        return status, raw.decode(errors="replace")


def expect(status: int, payload: Any, step: str) -> Any:
    """Stop with the API's answer when a step fails."""
    if not 200 <= status < 300:
        sys.exit(f"[qdash-demo] {step} failed: HTTP {status}: {payload}")
    return payload


def login() -> tuple[dict[str, str], str]:
    """Sign in as the initial administrator, waiting for the API to come up."""
    form = {
        "username": os.environ["QDASH_ADMIN_USERNAME"],
        "password": os.environ["QDASH_ADMIN_PASSWORD"],
    }
    for _ in range(90):
        try:
            status, payload = request("POST", "/auth/login", form=form)
        except OSError:
            status, payload = 0, None
        if status == 200:
            return {
                "Authorization": f"Bearer {payload['access_token']}",
                "X-Project-Id": payload["default_project_id"],
            }, payload["username"]
        if status == 401:
            sys.exit("[qdash-demo] Sign-in failed: QDASH_ADMIN_PASSWORD in .env does not match")
        time.sleep(5)
    sys.exit("[qdash-demo] The API did not answer in time; check `docker compose logs api`")


def main() -> None:
    headers, username = login()

    status, _ = request("GET", f"/chips/{CHIP_ID}", headers=headers)
    if status == 404:
        expect(
            *request(
                "POST",
                "/chips",
                body={"chip_id": CHIP_ID, "size": 64, "config": {"preset": "fake"}},
                headers=headers,
            ),
            "Create chip",
        )
        print(f"[qdash-demo] Created chip {CHIP_ID}")
    else:
        expect(status, None, "Read chip")

    status, _ = request("GET", f"/flows/{FLOW_NAME}", headers=headers)
    if status == 404:
        template = expect(
            *request("GET", f"/flows/templates/{TEMPLATE_ID}", headers=headers), "Read template"
        )
        expect(
            *request(
                "POST",
                "/flows",
                body={
                    "name": FLOW_NAME,
                    "description": "Demo run of the Fake Backend Calibration template",
                    "code": template["code"],
                    "flow_function_name": template["function_name"],
                    "chip_id": CHIP_ID,
                    # As saved by New Flow: the flow's own defaults target the demo chip.
                    "default_parameters": {"username": username, "chip_id": CHIP_ID},
                    "tags": ["demo"],
                    "create_only": True,
                },
                headers=headers,
            ),
            "Save flow",
        )
        print(f"[qdash-demo] Saved flow {FLOW_NAME}")
    else:
        expect(status, None, "Read flow")

    executions = expect(
        *request("GET", f"/executions?chip_id={CHIP_ID}&limit=1", headers=headers),
        "List executions",
    )
    if executions["executions"]:
        latest = executions["executions"][0]
        print(
            f"[qdash-demo] Latest chip run {latest['execution_id']}: {latest['status']}; "
            "no new run started"
        )
        if latest["status"] in {"failed", "cancelled"}:
            print(
                "[qdash-demo] Open Execution to inspect the failed or cancelled run, "
                f"then run {FLOW_NAME} again from Workflow. Restart does not retry runs."
            )
        return
    run = expect(
        *request(
            "POST",
            f"/flows/{FLOW_NAME}/execute",
            body={"target_override": {"mux_ids": SEED_MUX_IDS}},
            headers=headers,
        ),
        "Execute flow",
    )
    print(f"[qdash-demo] Started run {run['execution_id']} on MUX {SEED_MUX_IDS}")
    print("[qdash-demo] The run continues in the background; check its status in Execution")


if __name__ == "__main__":
    main()
