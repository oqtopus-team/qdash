# Python Sandbox

The Python sandbox runs model-generated analysis in a disposable worker with an operating-system
isolation boundary; the API fails closed when that boundary is unavailable.

## Request Flow

1. The Agent Runtime exposes `run_python` from `agent-runtime/src/python-tool.ts`.
2. The tool sends source code to the authenticated API sandbox endpoint.
3. `src/qdash/copilot/tooling/sandbox.py` validates the code and starts a worker under
   Bubblewrap (`bwrap`).
4. `sandbox_worker.py` applies process limits and calls the execution logic in
   `sandbox_core.py`.
5. The API returns text and an optional Plotly chart specification to the runtime.

The runtime does not execute Python itself. If `bwrap` is missing, the API returns an error
instead of falling back to an unisolated process.

## Isolation Layers

| Layer | Enforcement |
| --- | --- |
| Syntax and imports | AST validation in both parent and worker processes |
| Python capabilities | Restricted builtins and an import allowlist |
| Operating system | Bubblewrap namespace with no network and a disposable writable directory |
| Filesystem | Required interpreter and library paths are mounted read-only |
| Process lifetime | Wall-clock timeout and worker process-group termination |
| Resources | Worker CPU and memory limits |
| Payloads | Input, output, and worker-response byte limits |

The allowlist contains numerical, statistical, serialization, and Plotly modules: NumPy, pandas,
SciPy, Plotly, `math`, `statistics`, `json`, `datetime`, `collections`, and `io`. Calls such as
`eval`, `exec`, `compile`, `open`, and `breakpoint` are rejected.

## Limits

| Limit | Value |
| --- | --- |
| Code execution | 5 seconds |
| Worker startup grace | 5 seconds |
| Worker memory | 1 GiB |
| Serialized input | 16 MiB |
| Text output | 100 KiB |
| Serialized worker response | 256 KiB |

Keep these values synchronized with `sandbox_core.py`. The worker environment also limits common
numerical libraries to one thread.

## Result Contract

Analysis code can print text or assign a `result` dictionary:

```python
result = {
    "output": "Fit completed",
    "chart": {"data": [], "layout": {"title": "Fit"}},
}
```

The chart can be one Plotly specification or a list of specifications. The runtime forwards a
valid chart to the chat UI. Data needed by the calculation must be included in the generated code;
`run_python` does not provide filesystem, network, or shell access.

## Change and Test the Sandbox

Keep validation rules and limits in `src/qdash/copilot/tooling/sandbox_core.py`, and keep process
isolation in `sandbox.py` and `sandbox_worker.py`. Run:

```bash
uv run pytest tests/qdash/copilot/test_sandbox.py -v
task ci-agent-runtime
```

Tests cover forbidden operations, allowed scientific modules, size limits, timeout and process
cleanup, cancellation, serialization, and Plotly results.
