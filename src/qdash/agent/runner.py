"""Codex app-server runtime adapter for workflow authoring jobs."""

from __future__ import annotations

import json
import logging
import select
import shutil
import subprocess
import time
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from qdash.agent.events import DiffEvent, StatusEvent, SummaryDeltaEvent

logger = logging.getLogger("uvicorn.app")


class AgentRunnerError(RuntimeError):
    """Raised when an agent runtime cannot complete a workflow editing job."""


class CodexAppServerRunner:
    """Run Codex app-server against an isolated workflow workspace."""

    def __init__(
        self,
        *,
        codex_bin: str | None = None,
        timeout_seconds: int = 300,
    ) -> None:
        resolved_codex_bin = codex_bin or shutil.which("codex")
        if resolved_codex_bin is None:
            raise AgentRunnerError("Codex CLI was not found on the agent host.")
        self._command = [resolved_codex_bin, "app-server", "--listen", "stdio://"]
        self._timeout_seconds = timeout_seconds

    @property
    def command(self) -> list[str]:
        """Command used to start the Codex runtime."""
        return list(self._command)

    def run(self, workspace: Path, prompt: str) -> str:
        """Run one Codex app-server turn and return streamed assistant text."""
        summary_parts: list[str] = []
        for event in self.stream(workspace, prompt):
            if event["type"] == "summary_delta":
                summary_parts.append(cast("str", event["delta"]))

        return "".join(summary_parts).strip() or "Codex app-server edited the workflow."

    def stream(
        self, workspace: Path, prompt: str
    ) -> Iterator[StatusEvent | SummaryDeltaEvent | DiffEvent]:
        """Run one Codex app-server turn and stream summary/diff events."""
        yield {
            "type": "status",
            "stage": "start",
            "message": "Starting Codex app-server",
        }
        try:
            process = subprocess.Popen(
                self._command,
                cwd=workspace,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
        except OSError as exc:
            raise AgentRunnerError(f"Failed to start Codex app-server: {exc}")

        yield {
            "type": "status",
            "stage": "connect",
            "message": "Connected to Codex app-server over stdio",
        }
        next_id = 1
        deadline = time.monotonic() + self._timeout_seconds

        def send(method: str, params: dict[str, Any] | None) -> int:
            nonlocal next_id
            request_id = next_id
            next_id += 1
            message: dict[str, Any] = {"id": request_id, "method": method}
            if params is not None:
                message["params"] = params
            if process.stdin is None:
                raise AgentRunnerError("Codex app-server stdin is unavailable.")
            process.stdin.write(json.dumps(message) + "\n")
            process.stdin.flush()
            return request_id

        def read_message() -> dict[str, Any]:
            if process.stdout is None:
                raise AgentRunnerError("Codex app-server stdout is unavailable.")
            while time.monotonic() < deadline:
                readable, _, _ = select.select([process.stdout], [], [], 0.5)
                if not readable:
                    if process.poll() is not None:
                        break
                    continue
                line = process.stdout.readline()
                if not line:
                    break
                try:
                    return cast("dict[str, Any]", json.loads(line))
                except json.JSONDecodeError:
                    logger.debug("Ignoring non-JSON Codex app-server output: %s", line.rstrip())
            raise AgentRunnerError("Codex app-server editing timed out.")

        def handle_notification(message: dict[str, Any]) -> None:
            method = message.get("method")
            params = cast("dict[str, Any]", message.get("params") or {})
            if method == "error":
                raise AgentRunnerError(f"Codex app-server error: {params}")

        def wait_for_response(request_id: int) -> dict[str, Any]:
            while True:
                message = read_message()
                if "method" in message:
                    handle_notification(message)
                    continue
                if message.get("id") != request_id:
                    continue
                if "error" in message:
                    raise AgentRunnerError(f"Codex app-server error: {message['error']}")
                return cast("dict[str, Any]", message.get("result") or {})

        try:
            yield {
                "type": "status",
                "stage": "initialize",
                "message": "Initializing Codex runtime",
            }
            initialize_id = send(
                "initialize",
                {
                    "clientInfo": {
                        "name": "qdash",
                        "title": "QDash",
                        "version": "0.0.1",
                    },
                    "capabilities": {
                        "experimentalApi": True,
                        "requestAttestation": False,
                    },
                },
            )
            wait_for_response(initialize_id)
            yield {
                "type": "status",
                "stage": "initialize",
                "message": "Codex runtime initialized",
            }

            yield {
                "type": "status",
                "stage": "workspace",
                "message": "Opening isolated workflow workspace",
            }
            thread_id = send(
                "thread/start",
                {
                    "cwd": str(workspace),
                    "runtimeWorkspaceRoots": [str(workspace)],
                    "approvalPolicy": "never",
                    "sandbox": "workspace-write",
                    "ephemeral": True,
                    "developerInstructions": (
                        "You are editing a temporary QDash workflow workspace. "
                        "Edit only the requested Python workflow file. "
                        "Do not install packages, run hardware, or deploy workflows."
                    ),
                },
            )
            thread_result = wait_for_response(thread_id)
            thread = cast("dict[str, Any]", thread_result.get("thread") or {})
            app_thread_id = thread.get("id")
            if not isinstance(app_thread_id, str):
                raise AgentRunnerError("Codex app-server did not start a thread.")
            yield {
                "type": "status",
                "stage": "workspace",
                "message": "Temporary workflow workspace is ready",
            }

            yield {
                "type": "status",
                "stage": "turn",
                "message": "Sending edit request to Codex",
            }
            turn_id = send(
                "turn/start",
                {
                    "threadId": app_thread_id,
                    "input": [
                        {
                            "type": "text",
                            "text": prompt,
                            "text_elements": [],
                        }
                    ],
                    "cwd": str(workspace),
                    "runtimeWorkspaceRoots": [str(workspace)],
                    "approvalPolicy": "never",
                    "sandboxPolicy": {
                        "type": "workspaceWrite",
                        "writableRoots": [str(workspace)],
                        "networkAccess": False,
                        "excludeTmpdirEnvVar": False,
                        "excludeSlashTmp": False,
                    },
                },
            )
            wait_for_response(turn_id)
            yield {
                "type": "status",
                "stage": "thinking",
                "message": "Codex is reading the workflow and planning the edit",
            }

            while True:
                message = read_message()
                if "method" not in message:
                    continue
                method = message.get("method")
                params = cast("dict[str, Any]", message.get("params") or {})
                handle_notification(message)
                if method == "item/agentMessage/delta":
                    delta = params.get("delta")
                    if isinstance(delta, str):
                        yield {"type": "summary_delta", "delta": delta}
                elif method == "turn/diff/updated":
                    diff = params.get("diff")
                    if isinstance(diff, str):
                        yield {
                            "type": "status",
                            "stage": "editing",
                            "message": "Codex produced a code diff",
                        }
                        yield {"type": "diff", "diff": diff}
                elif method == "turn/completed":
                    turn = cast("dict[str, Any]", params.get("turn") or {})
                    if turn.get("status") == "failed":
                        raise AgentRunnerError(f"Codex turn failed: {turn.get('error')}")
                    yield {
                        "type": "status",
                        "stage": "complete",
                        "message": "Codex finished the edit turn",
                    }
                    break

        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
            if process.stderr is not None:
                stderr = process.stderr.read().strip()
                if stderr:
                    logger.debug("Codex app-server stderr: %s", stderr[-2000:])
