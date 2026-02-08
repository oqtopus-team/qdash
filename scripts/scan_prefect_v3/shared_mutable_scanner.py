import ast
from pathlib import Path
from collections import defaultdict

from common import print_with_border
from config import TARGET_DIR


def scan_shared_mutable() -> None:
    """
    Detect risky shared mutable objects accessed from @task
    """

    findings: dict[str, list[str]] = defaultdict(list)

    class SharedMutableVisitor(ast.NodeVisitor):
        def __init__(self, path: Path):
            self.path = path
            self.global_mutables: set[str] = set()
            self.in_task = False

        def visit_Assign(self, node: ast.Assign):
            """
            Global mutable
            Examples:
              CACHE = {}
              DATA = []
            """
            if isinstance(node.value, (ast.Dict, ast.List, ast.Set)):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        self.global_mutables.add(target.id)
            self.generic_visit(node)

        def visit_FunctionDef(self, node: ast.FunctionDef):
            # Check if @task decorator is present
            has_task = any(
                isinstance(d, ast.Name) and d.id == "task"
                for d in node.decorator_list
            )

            if not has_task:
                self.generic_visit(node)
                return

            self.in_task = True

            # Check if global mutable is accessed within the task
            for sub in ast.walk(node):
                if isinstance(sub, ast.Name) and sub.id in self.global_mutables:
                    findings["shared_mutable_access"].append(
                        f"{self.path}:{sub.lineno} -> "
                        f"access to shared mutable '{sub.id}' in task '{node.name}'"
                    )

            self.generic_visit(node)
            self.in_task = False

    for py in TARGET_DIR.rglob("*.py"):
        try:
            tree = ast.parse(py.read_text())
        except Exception:
            continue

        visitor = SharedMutableVisitor(py)
        visitor.visit(tree)


    print()
    print_with_border("🟡 SHARED MUTABLE RISKS (Prefect v3)")
    print(f"Target: {TARGET_DIR}")

    if not findings:
        print("✅ No shared mutable risks found")
    else:
        for kind, locations in findings.items():
            print(f"\n⚠️ {kind}")
            for loc in locations:
                print(f" - {loc}")

    print()


if __name__ == "__main__":
    scan_shared_mutable()
