import ast
from pathlib import Path
from collections import defaultdict
from common import print_with_border


def _get_called_name(node: ast.AST) -> str | None:
    """Get the called function name from a Call node."""
    if isinstance(node, ast.Call):
        f = node.func
        if isinstance(f, ast.Attribute):
            return f.attr
        if isinstance(f, ast.Name):
            return f.id
    return None


class AsyncPrefectVisitor(ast.NodeVisitor):
    def __init__(self):
        self.issues: list[tuple[int, str]] = []

    def visit_FunctionDef(self, node: ast.FunctionDef):
        for n in ast.walk(node):
            if isinstance(n, ast.Await):
                self.issues.append(
                    (
                        n.lineno,
                        f"await inside sync function '{node.name}'",
                    )
                )

            if isinstance(n, ast.Call) and _get_called_name(n) == "submit":
                self.issues.append(
                    (
                        n.lineno,
                        f".submit() called inside sync function '{node.name}'",
                    )
                )

        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        for n in ast.walk(node):
            if isinstance(n, ast.Await) and isinstance(n.value, ast.Call):
                if _get_called_name(n.value) == "submit":
                    self.issues.append(
                        (
                            n.lineno,
                            f"await task.submit() in async function '{node.name}'",
                        )
                    )

        self.generic_visit(node)


def scan_file(path: Path) -> list[tuple[int, str]]:
    try:
        tree = ast.parse(path.read_text())
    except Exception:
        return []

    visitor = AsyncPrefectVisitor()
    visitor.visit(tree)
    return visitor.issues


def scan_risky_async() -> None:
    root = Path(".")
    findings: dict[str, list[str]] = defaultdict(list)

    for py in root.rglob("*.py"):
        issues = scan_file(py)
        for line, msg in issues:
            findings[str(py)].append(f"L{line}: {msg}")

    print()
    print_with_border("🟡 RISKY ASYNC USAGE (Prefect 3)")

    if not findings:
        print("✅ No issues found")
    else:
        for filepath, messages in sorted(findings.items()):
            print(f"\n{filepath}")
            for m in messages:
                print(f" - {m}")

    print()

if __name__ == "__main__":
    scan_risky_async()
