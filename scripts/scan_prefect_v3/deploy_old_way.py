import ast
import os
from pathlib import Path
from collections import defaultdict

from common import print_with_border
from config import TARGET_DIR


RISKY_IMPORT_PREFIXES = {
    "prefect.deployments",
    "prefect.deployments.deployments",
}

RISKY_CLASSES = {
    "Deployment",
}

RISKY_DEPLOY_KEYWORDS = {
    "work_queue",
    "infrastructure",
    "run_config",
    "schedule",
    "image",
}


def scan_deploy_v3_candidates() -> None:
    """
    Detect patterns that likely need migration to:
      - Prefect v3 YAML deployments
      - WorkPool + Worker model
      - New deployment API
    """

    findings: dict[str, list[str]] = defaultdict(list)

    class DeployVisitor(ast.NodeVisitor):
        def __init__(self, path: Path):
            self.path = path

        # --- 1) Old deployment imports ---
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

        # --- 2) Deployment(...) instantiation ---
        def visit_Call(self, node: ast.Call):
            # Deployment(...)
            if isinstance(node.func, ast.Name) and node.func.id in RISKY_CLASSES:
                findings["old_deployment_api"].append(
                    f"{self.path}:{node.lineno} -> uses Deployment(...)"
                )

            # something like: prefect.deployments.Deployment(...)
            if isinstance(node.func, ast.Attribute):
                if node.func.attr in RISKY_CLASSES:
                    findings["old_deployment_api"].append(
                        f"{self.path}:{node.lineno} -> uses {node.func.attr}(...)"
                    )

                # flow.deploy(...) / flow.serve(...)
                if node.func.attr in {"deploy", "serve"}:
                    findings["python_deploy_api"].append(
                        f"{self.path}:{node.lineno} -> calls flow.{node.func.attr}()"
                    )

            # --- 3) Old deployment keywords ---
            for kw in node.keywords:
                if isinstance(kw.arg, str) and kw.arg in RISKY_DEPLOY_KEYWORDS:
                    findings["v2_style_args"].append(
                        f"{self.path}:{node.lineno} -> uses '{kw.arg}' argument"
                    )

            self.generic_visit(node)

    root = TARGET_DIR
    print()
    print(f"Scanning for v3 deployment migration candidates in: {os.path.abspath(root)}")

    for py in root.rglob("*.py"):
        try:
            tree = ast.parse(py.read_text())
        except Exception:
            continue

        visitor = DeployVisitor(py)
        visitor.visit(tree)

    print()
    print_with_border("🔷 DEPLOYMENT MIGRATION CANDIDATES (Prefect v3)")

    if not findings:
        print("✅ No legacy deployment patterns detected — good for YAML migration 🎉")
    else:
        for kind, locations in findings.items():
            print(f"\n⚠️ {kind}")
            for loc in locations:
                print(f" - {loc}")

    print()


if __name__ == "__main__":
    scan_deploy_v3_candidates()
