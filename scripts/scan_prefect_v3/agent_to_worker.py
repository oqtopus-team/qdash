import ast
import os
from pathlib import Path
from collections import defaultdict

from common import print_with_border
from config import TARGET_DIR


RISKY_IMPORT_PREFIXES = {
    "prefect.agent",
    "prefect.infrastructure",
    "prefect.workers.block",
    "prefect.workers.cloud",
}

RISKY_CLASSES = {
    "PrefectAgent",
    "KubernetesJob",
    "Infrastructure",
    "BlockWorker",
    "BlockWorkerJobConfiguration",
}


def scan_agent_to_worker() -> None:
    """
    Detect code patterns that likely need to be migrated
    from Prefect Agent -> Worker + WorkPool in Prefect v3
    """

    findings: dict[str, list[str]] = defaultdict(list)

    class AgentWorkerVisitor(ast.NodeVisitor):
        def __init__(self, path: Path):
            self.path = path

        # --- 1) Risky Import ---
        def visit_Import(self, node: ast.Import):
            for alias in node.names:
                name = alias.name
                for p in RISKY_IMPORT_PREFIXES:
                    if name.startswith(p):
                        findings["risky_import"].append(
                            f"{self.path}:{node.lineno} -> import {name}"
                        )
            self.generic_visit(node)

        def visit_ImportFrom(self, node: ast.ImportFrom):
            module = node.module or ""
            for p in RISKY_IMPORT_PREFIXES:
                if module.startswith(p):
                    findings["risky_import"].append(
                        f"{self.path}:{node.lineno} -> from {module} import ..."
                    )
            self.generic_visit(node)

        # --- 2) PrefectAgent / KubernetesJob instantiation ---
        def visit_Call(self, node: ast.Call):
            # Class instantiation like: PrefectAgent(...)
            if isinstance(node.func, ast.Name) and node.func.id in RISKY_CLASSES:
                findings["risky_instantiation"].append(
                    f"{self.path}:{node.lineno} -> instantiates {node.func.id}"
                )

            # something like: prefect.agent.PrefectAgent(...)
            if isinstance(node.func, ast.Attribute):
                full_name = node.func.attr
                if full_name in RISKY_CLASSES:
                    findings["risky_instantiation"].append(
                        f"{self.path}:{node.lineno} -> instantiates {full_name}"
                    )

            self.generic_visit(node)

    root = TARGET_DIR
    print()
    print(f"Scanning for Agent → Worker migration risks in: {os.path.abspath(root)}")

    for py in root.rglob("*.py"):
        try:
            tree = ast.parse(py.read_text())
        except Exception:
            continue

        visitor = AgentWorkerVisitor(py)
        visitor.visit(tree)

    print()
    print_with_border("🟣 AGENT → WORKER MIGRATION CANDIDATES (Prefect v3)")

    if not findings:
        print("✅ No Agent usage detected — looks clean for Worker migration 🎉")
    else:
        for kind, locations in findings.items():
            print(f"\n⚠️ {kind}")
            for loc in locations:
                print(f" - {loc}")

    print()


if __name__ == "__main__":
    scan_agent_to_worker()
