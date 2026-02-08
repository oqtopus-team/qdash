import ast
from pathlib import Path
from collections import defaultdict
import re

from common import print_with_border
from config import TARGET_DIR


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
    scan_flow_error()
