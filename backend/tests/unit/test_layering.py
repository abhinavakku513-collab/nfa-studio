import ast
import importlib.util
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "nfa_studio"

# spec Figure 2: the automata core is pure and never reaches the web layer or the LLM.
CORE_PACKAGES = ("core", "ir", "compile", "reference", "verify")
FORBIDDEN = (
    "fastapi",
    "starlette",
    "uvicorn",
    "httpx",
    "anthropic",
    "nfa_studio.api",
    "nfa_studio.interpret.llm_adapter",
)


def imported_modules(source: str, package: str) -> set[str]:
    """Absolute names of every module imported by `source`, which lives in `package`."""
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = importlib.util.resolve_name("." * node.level + (node.module or ""), package)
            names.add(base)
            names.update(f"{base}.{alias.name}" for alias in node.names)
    return names


def forbidden_imports(source: str, package: str) -> list[str]:
    return sorted(
        name
        for name in imported_modules(source, package)
        if any(name == f or name.startswith(f + ".") for f in FORBIDDEN)
    )


@pytest.mark.parametrize("subpackage", CORE_PACKAGES)
def test_core_packages_do_not_import_web_or_llm(subpackage: str) -> None:
    for path in sorted((PACKAGE_ROOT / subpackage).rglob("*.py")):
        package = ".".join(path.relative_to(PACKAGE_ROOT.parent).parent.parts)
        bad = forbidden_imports(path.read_text(encoding="utf-8"), package)
        assert not bad, f"{path.relative_to(PACKAGE_ROOT)} imports {bad}"


@pytest.mark.parametrize(
    "source",
    [
        "import fastapi",
        "from starlette.requests import Request",
        "from ..api import routes",
        "from ..interpret.llm_adapter import propose_ir",
        "from nfa_studio.interpret import llm_adapter",
    ],
)
def test_guard_catches_forbidden_imports(source: str) -> None:
    assert forbidden_imports(source, "nfa_studio.core")


def test_guard_allows_core_imports() -> None:
    source = "from ..ir.limits import LIMITS\nfrom nfa_studio.interpret import lexicon"
    assert forbidden_imports(source, "nfa_studio.core") == []
