"""The dependency rule of the layers (see miningcat/__init__.py): each layer only imports the layers below it."""
import ast
from pathlib import Path

import pytest

PACKAGE = Path(__file__).parent.parent / "miningcat"

# What each layer may import from the package (besides itself).
ALLOWED = {
    "domain": set(),
    "infrastructure": {"domain", "config"},
    "application": {"domain", "infrastructure", "config"},
    "interfaces": {"domain", "infrastructure", "application", "config"},
    "config": set(),
}


def imported_layers(path: Path) -> set[str]:
    layers = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        elif isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        else:
            continue
        for name in names:
            parts = name.split(".")
            if parts[0] == "miningcat" and len(parts) > 1:
                layers.add(parts[1])
    return layers


@pytest.mark.parametrize("layer", sorted(ALLOWED))
def test_layer_only_imports_the_layers_below(layer):
    violations = []
    for path in sorted((PACKAGE / layer).rglob("*.py")):
        forbidden = imported_layers(path) - ALLOWED[layer] - {layer}
        if forbidden:
            violations.append(f"{path.relative_to(PACKAGE)} imports {', '.join(sorted(forbidden))}")
    assert not violations, "\n".join(violations)


def test_no_module_outside_the_package():
    """src/ only holds the package and its tests."""
    assert sorted(p.name for p in PACKAGE.parent.iterdir() if not p.name.startswith(".") and p.name != "__pycache__") \
        == ["miningcat", "tests"]
