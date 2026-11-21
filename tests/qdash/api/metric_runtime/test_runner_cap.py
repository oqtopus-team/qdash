import json
import select
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import pytest

from qdash.api.metric_runtime import executor
from tests.qdash.api.metric_runtime.test_broker import HISTORY_ARGS, FakeTaskResults, make_broker


def test_real_runner_cap_is_propagated_to_broker():
    bun = shutil.which("bun")
    if bun is None:
        pytest.skip("Bun is required for the real metric runner")
    repo = Path(__file__).resolve().parents[4]
    with tempfile.TemporaryDirectory(prefix="qr1888-", dir="/tmp") as temp:
        root = Path(temp)
        worker = root / "worker"
        call = "CALL " + json.dumps({"op": "history", "args": HISTORY_ARGS})
        worker.write_text("#!/bin/sh\nprintf '%s\\n' '" + call + "'\nsleep 20\n")
        worker.chmod(0o700)
        ts = root / "runner.ts"
        ts.write_text(
            "import {startMetricRunner} from "
            + json.dumps(str(repo / "agent-runtime/metric-runner/runner.ts"))
            + ";\n"
            + "const runner = await startMetricRunner("
            + json.dumps(
                {
                    "socketPath": str(root / "sock"),
                    "isolateUsers": False,
                    "python": str(worker),
                    "pythonPath": "",
                    "jobRoot": str(root / "jobs"),
                    "maxTimeoutSeconds": 1,
                }
            )
            + ');\nconsole.log("READY");\nprocess.on("SIGTERM",()=>void runner.close().then(()=>process.exit(0)));\n'
        )
        # Fixed test program in a private temporary directory; no user input.
        process = subprocess.Popen(  # noqa: S603
            [bun, str(ts)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )
        try:
            assert process.stdout is not None
            startup_deadline = time.monotonic() + 10
            while True:
                assert select.select(
                    [process.stdout], [], [], max(0, startup_deadline - time.monotonic())
                )[0], "runner startup timed out"
                line = process.stdout.readline()
                assert line, "runner did not start"
                if line.strip() == "READY":
                    break

            class SlowResults(FakeTaskResults):
                def find(self, query, **kwargs):
                    result = super().find(query, **kwargs)
                    time.sleep(1.4)
                    return result

            data = SlowResults()
            started = time.monotonic()
            with pytest.raises(executor.WorkerFailure) as failure:
                executor.run_worker(
                    {
                        "mode": "evaluate",
                        "source": "",
                        "metric_id": "test",
                        "chip_id": "chip-1",
                        "start": HISTORY_ARGS["start"],
                        "end": HISTORY_ARGS["end"],
                        "params": {},
                    },
                    broker=make_broker(data),
                    settings=executor.RuntimeSettings(
                        mode="socket", socket_path=str(root / "sock"), timeout_seconds=3
                    ),
                )
            elapsed = time.monotonic() - started
            remaining = data.remaining[0]
            assert remaining is not None and 0 < remaining <= 1
            assert 0 < data.kwargs[0]["max_time_ms"] <= 1000
            assert elapsed > 1.4
            assert "1 s time limit" in str(failure.value)
            # A deliberately noncooperative driver proves cancellation cannot preempt Python.
        finally:
            process.terminate()
            output, _ = process.communicate(timeout=5)
            print(output)
