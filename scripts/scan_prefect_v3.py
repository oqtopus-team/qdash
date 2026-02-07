import ast
from pathlib import Path
from collections import defaultdict
import re

def print_with_border(msg: str) -> None:
    print(f"========== {msg} ==========")

def scan_risky_import() -> None:
    """
    Scan for Prefect 3.0 risky imports

    Refer to:
    https://github.com/PrefectHQ/prefect/blob/main/src/prefect/_internal/compatibility/migration.py
    """

    # from prefect._internal.compatibility.migration import (
    #     MOVED_IN_V3,
    #     REMOVED_IN_V3,
    # )

    MOVED_IN_V3 = {
        "prefect.deployments.deployments:load_flow_from_flow_run": "prefect.flows:load_flow_from_flow_run",
        "prefect.deployments:load_flow_from_flow_run": "prefect.flows:load_flow_from_flow_run",
        "prefect.variables:get": "prefect.variables:Variable.get",
        "prefect.engine:pause_flow_run": "prefect.flow_runs:pause_flow_run",
        "prefect.engine:resume_flow_run": "prefect.flow_runs:resume_flow_run",
        "prefect.engine:suspend_flow_run": "prefect.flow_runs:suspend_flow_run",
        "prefect.client:get_client": "prefect.client.orchestration:get_client",
    }

    upgrade_guide_msg = "Refer to the upgrade guide for more information: https://docs.prefect.io/v3/how-to-guides/migrate/upgrade-agents-to-workers."

    REMOVED_IN_V3 = {
        "prefect.client.schemas.objects:MinimalDeploymentSchedule": "Use `prefect.client.schemas.actions.DeploymentScheduleCreate` instead.",
        "prefect.context:PrefectObjectRegistry": upgrade_guide_msg,
        "prefect.deployments.deployments:Deployment": "Use `flow.serve()`, `flow.deploy()`, or `prefect deploy` instead.",
        "prefect.deployments:Deployment": "Use `flow.serve()`, `flow.deploy()`, or `prefect deploy` instead.",
        "prefect.filesystems:GCS": "Use `prefect_gcp.GcsBucket` instead.",
        "prefect.filesystems:Azure": "Use `prefect_azure.AzureBlobStorageContainer` instead.",
        "prefect.filesystems:S3": "Use `prefect_aws.S3Bucket` instead.",
        "prefect.filesystems:GitHub": "Use `prefect_github.GitHubRepository` instead.",
        "prefect.engine:_out_of_process_pause": "Use `prefect.flow_runs.pause_flow_run` instead.",
        "prefect.engine:_in_process_pause": "Use `prefect.flow_runs.pause_flow_run` instead.",
        "prefect.agent:PrefectAgent": "Use workers instead. " + upgrade_guide_msg,
        "prefect.infrastructure:KubernetesJob": "Use workers instead. " + upgrade_guide_msg,
        "prefect.infrastructure.base:Infrastructure": "Use the `BaseWorker` class to create custom infrastructure integrations instead. "
        + upgrade_guide_msg,
        "prefect.workers.block:BlockWorkerJobConfiguration": upgrade_guide_msg,
        "prefect.workers.cloud:BlockWorker": upgrade_guide_msg,
    }

    MOVED_MODULES = {k.split(":")[0] for k in MOVED_IN_V3}
    REMOVED_MODULES = {k.split(":")[0] for k in REMOVED_IN_V3}

    def scan_file(path: Path) -> tuple[list[tuple[Path, str]], list[tuple[Path, str]]]:
        text = path.read_text()
        try:
            tree = ast.parse(text)
        except Exception:
            return [], []

        moved_hits = []
        removed_hits = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name

                    for m in MOVED_MODULES:
                        if name.startswith(m):
                            moved_hits.append((path, name))

                    for r in REMOVED_MODULES:
                        if name.startswith(r):
                            removed_hits.append((path, name))

            if isinstance(node, ast.ImportFrom):
                module = node.module or ""

                for m in MOVED_MODULES:
                    if module.startswith(m):
                        moved_hits.append((path, module))

                for r in REMOVED_MODULES:
                    if module.startswith(r):
                        removed_hits.append((path, module))

        return moved_hits, removed_hits


    root = Path(".")
    moved = defaultdict(list)
    removed = defaultdict(list)
    for py in root.rglob("*.py"):
        m_hits, r_hits = scan_file(py)
        for p, imp in m_hits:
            moved[imp].append(str(p))
        for p, imp in r_hits:
            removed[imp].append(str(p))
    print()
    print_with_border("🔶 MOVED_IN_V3")
    if not moved:
        print("✅ No issues found")
    else:
        for imp, files in moved.items():
            print(f"\n{imp}")
            for f in files:
                print(f" - {f}")
    print()
    print_with_border("🔴 REMOVED_IN_V3")
    if not removed:
        print("✅ No issues found")
    else:
        for imp, files in removed.items():
            print(f"\n{imp}")
            for f in files:
                print(f" - {f}")
    print()

def has_prefect_import(path: Path) -> bool:
    try:
        tree = ast.parse(path.read_text())
    except Exception:
        return False

    for node in ast.walk(tree):
        # import prefect
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "prefect" or alias.name.startswith("prefect."):
                    return True

        # from prefect import ...
        if isinstance(node, ast.ImportFrom):
            if node.module and (node.module == "prefect" or node.module.startswith("prefect.")):
                return True

    return False

def scan_flow_error() -> None:
    PATTERNS = {
        "raise_on_failure": r"raise_on_failure",
        "return_state": r"return_state",
        "try_except": r"try:",
        "state_check": r"is_failed|is_successful|State",
    }

    TARGET_DIRS = ["src/qdash/workflow"]

    root = Path(".")

    hits_by_pattern = defaultdict(list)

    for py in root.rglob("*.py"):
        if not any(str(py).startswith(td) for td in TARGET_DIRS):
            continue

        text = py.read_text()
        if "@flow" not in text:
            continue

        for name, pattern in PATTERNS.items():
            if re.search(pattern, text):
                hits_by_pattern[name].append(str(py))

    print()
    print_with_border("⚠️  Flow Error Behavior Risks (v3)")
    print()

    for name in PATTERNS.keys():
        print_with_border(name)

        files = hits_by_pattern.get(name, [])

        if not files:
            print("✅ No issues found")
        else:
            for f in files:
                print(f" - {f}")
        print()

if __name__ == "__main__":
    # scan_risky_import()
    scan_flow_error()
