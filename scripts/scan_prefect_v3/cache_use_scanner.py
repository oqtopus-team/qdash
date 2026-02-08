import ast
import os
from pathlib import Path
from collections import defaultdict

from common import print_with_border
from config import TARGET_DIR


def scan_risky_cache_patterns() -> None:
    """
    Detect patterns that are likely problematic with Prefect 3 auto-caching:
      - mutable default arguments in @task
      - mutation of dict/list inside @task
      - use of map() with mutable objects
    """

    risky = defaultdict(list)

    class CacheRiskVisitor(ast.NodeVisitor):
        def __init__(self, path: Path):
            self.path = path
            self.in_task = False

        def visit_FunctionDef(self, node):
            has_task = any(
                isinstance(d, ast.Name) and d.id == "task"
                for d in node.decorator_list
            )

            if not has_task:
                self.generic_visit(node)
                return

            self.in_task = True

            for arg in node.args.defaults:
                if isinstance(arg, (ast.Dict, ast.List, ast.Set)):
                    risky["mutable_default_arg"].append(
                        f"{self.path}:{node.lineno} -> {node.name}"
                    )

            for sub in ast.walk(node):
                if isinstance(sub, ast.Subscript):
                    risky["mutation_in_task"].append(
                        f"{self.path}:{sub.lineno} -> possible mutation in {node.name}"
                    )

            self.generic_visit(node)
            self.in_task = False

        def visit_Call(self, node):
            if isinstance(node.func, ast.Attribute) and node.func.attr == "map":
                risky["task_map_usage"].append(
                    f"{self.path}:{node.lineno} -> uses .map()"
                )
            self.generic_visit(node)

    root = TARGET_DIR
    print()
    print(f"Scanning for risky cache patterns in Prefect 3 under: {os.path.abspath(root)}")
    for py in root.rglob("*.py"):
        try:
            tree = ast.parse(py.read_text())
        except Exception:
            continue

        visitor = CacheRiskVisitor(py)
        visitor.visit(tree)

    print()
    print_with_border("🟡 RISKY CACHE PATTERNS (Prefect v3)")
    if not risky:
        print("✅ No risky cache patterns detected")
    else:
        for kind, locations in risky.items():
            print(f"\n⚠️ {kind}")
            for loc in locations:
                print(f" - {loc}")
    print()

if __name__ == "__main__":
    scan_risky_cache_patterns()


