"""Tests for the metric script import and builtin guardrails."""

from __future__ import annotations

import pytest

from qdash.api.metric_runtime import policy, sdk, worker
from qdash.api.metric_runtime.policy import ScriptPolicyError, diagnostic, validate_imports


@pytest.fixture(autouse=True)
def _public_module() -> None:
    worker.install_public_module()


@pytest.mark.parametrize(
    "source",
    [
        "import numpy as np\n",
        "import scipy.stats\n",
        "from math import sqrt\n",
        "import statistics\n",
        "from qdash_metrics import metric, Parameter\n",
    ],
)
def test_allowed_imports(source):
    validate_imports(source)


@pytest.mark.parametrize(
    ("source", "line"),
    [
        ("import os\n", 1),
        ("x = 1\nimport subprocess\n", 2),
        ("from qdash_metrics import _private\n", 1),
        ("import qdash_metrics.sdk\n", 1),
        ("import numpy._core\n", 1),
        ("from . import sibling\n", 1),
        ("def f():\n    import socket\n", 2),
        ("from qdash.api import main\n", 1),
    ],
)
def test_rejected_imports_report_lines(source, line):
    with pytest.raises(ScriptPolicyError) as info:
        validate_imports(source)
    assert info.value.line == line
    detail = diagnostic(info.value)
    assert detail["line"] == line
    assert "not allowed" in detail["message"] or "public API" in detail["message"]


@pytest.mark.parametrize("name", ["open", "exec", "eval", "compile", "input", "breakpoint"])
def test_disabled_builtins(name):
    source = f"from qdash_metrics import metric\n{name}\n"
    with pytest.raises(NameError) as info:
        sdk.load_source(source)
    assert diagnostic(info.value)["line"] == 2


def test_dynamic_import_is_checked():
    source = "__import__('os')\n"
    with pytest.raises(ScriptPolicyError):
        sdk.load_source(source)


def test_numpy_internals_load_at_runtime():
    source = (
        "import numpy as np\n"
        "from qdash_metrics import metric\n"
        "TOTAL = float(np.array([1.0, 2.0]).sum())\n"
        "@metric(title='x', unit='GHz')\n"
        "def x(target, ctx):\n"
        "    return TOTAL\n"
    )
    assert list(sdk.load_source(source)) == ["x"]


def test_diagnostics_for_syntax_and_runtime_errors():
    with pytest.raises(SyntaxError) as syntax:
        sdk.load_source("def broken(:\n")
    assert diagnostic(syntax.value)["line"] == 1
    assert "column" in diagnostic(syntax.value)

    source = (
        "from qdash_metrics import metric\n"
        "@metric(title='x', unit='GHz')\n"
        "def x(target, ctx):\n"
        "    return 1 / 0\n"
    )
    function = sdk.load_source(source)["x"].function
    with pytest.raises(ZeroDivisionError) as runtime:
        function("0", None)
    detail = diagnostic(runtime.value)
    assert detail == {"message": "ZeroDivisionError: division by zero", "line": 4, "function": "x"}
    assert policy.error_message(runtime.value).endswith("(line 4, x)")


def test_load_source_rejects_invalid_scripts():
    with pytest.raises(ValueError, match="No metrics found"):
        sdk.load_source("x = 1\n")
    with pytest.raises(ValueError, match="titles"):
        sdk.load_source(
            "from qdash_metrics import metric\n"
            "@metric(title=' ', unit='GHz')\n"
            "def x(target, ctx):\n    return 1\n"
        )
    with pytest.raises(ValueError, match="Parameter values"):
        sdk.load_source(
            "from qdash_metrics import metric\n"
            "@metric(title='x', unit='GHz', parameters={'a': 1})\n"
            "def x(target, ctx):\n    return 1\n"
        )
