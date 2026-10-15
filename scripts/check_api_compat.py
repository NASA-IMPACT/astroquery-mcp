"""Check that every third-party name the code uses exists in the installed package versions.

Reads the source with `ast` (nothing is executed) and collects:
  - imports:            `from astropy.table import Table`, `import numpy as np`
  - attribute chains:   `u.arcmin`, `SkyCoord.from_name`, `np.integer`
  - keyword arguments:  `SkyCoord(ra=..., frame=...)`, `stop_after_attempt(...)`
Each one is then resolved against whatever is installed in the running interpreter.
Run it inside an environment holding the minimum supported versions to prove the floors in
pyproject.toml are real:

    uv run python3 scripts/check_api_compat.py

Names reached through runtime values (e.g. `coord.ra.deg` on a SkyCoord instance) cannot be
resolved statically; the test suite covers those when run in the same environment.
"""

import ast
import importlib
import importlib.metadata
import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# import name -> distribution name
THIRD_PARTY = {
    "astropy": "astropy", "astroquery": "astroquery", "fastmcp": "fastmcp", "httpx": "httpx", "mcp": "mcp",
    "numpy": "numpy", "pydantic": "pydantic", "pytest": "pytest", "tenacity": "tenacity", "yaml": "pyyaml",
}
SKIP_DIRS = {".venv", "docs", "build", "scripts", ".git"}


def source_files() -> list[Path]:
    return sorted(
        p for p in ROOT.rglob("*.py")
        if not SKIP_DIRS & set(p.relative_to(ROOT).parts)
    )


def dotted(node: ast.AST) -> list[str] | None:
    """`a.b.c` -> ["a", "b", "c"]; None if the chain does not start at a plain name."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    return [node.id, *reversed(parts)]


def collect(path: Path) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """Return ({dotted name: {locations}}, {dotted callable: {keyword names}})."""
    tree = ast.parse(path.read_text(), filename=str(path))
    aliases: dict[str, str] = {}
    names: dict[str, set[str]] = {}
    kwargs: dict[str, set[str]] = {}

    def use(name: str, node: ast.AST) -> None:
        names.setdefault(name, set()).add(f"{path.relative_to(ROOT)}:{node.lineno}")

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[0] in THIRD_PARTY:
                    aliases[a.asname or a.name.split(".")[0]] = a.name if a.asname else a.name.split(".")[0]
                    use(a.name, node)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            if node.module.split(".")[0] in THIRD_PARTY:
                for a in node.names:
                    aliases[a.asname or a.name] = f"{node.module}.{a.name}"
                    use(f"{node.module}.{a.name}", node)

    def resolve(node: ast.AST) -> str | None:
        chain = dotted(node)
        if chain and chain[0] in aliases:
            return ".".join([aliases[chain[0]], *chain[1:]])
        return None

    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and not isinstance(getattr(node, "ctx", None), ast.Store):
            if (name := resolve(node)) is not None:
                use(name, node)
        elif isinstance(node, ast.Call) and node.keywords:
            if (name := resolve(node.func)) is not None:
                kwargs.setdefault(name, set()).update(k.arg for k in node.keywords if k.arg)
    return names, kwargs


def lookup(name: str):
    """Import the longest importable module prefix of `name`, then getattr the rest."""
    parts = name.split(".")
    for i in range(len(parts), 0, -1):
        try:
            obj = importlib.import_module(".".join(parts[:i]))
        except ImportError:
            continue
        for attr in parts[i:]:
            obj = getattr(obj, attr)
        return obj
    raise ImportError(name)


def accepts(obj, keywords: set[str]) -> set[str]:
    """Return the keywords `obj` would reject (empty if it takes **kwargs or has no signature)."""
    try:
        params = inspect.signature(obj).parameters.values()
    except (TypeError, ValueError):
        return set()
    if any(p.kind is p.VAR_KEYWORD for p in params):
        return set()
    return keywords - {p.name for p in params}


def main() -> int:
    names: dict[str, set[str]] = {}
    kwargs: dict[str, set[str]] = {}
    for path in source_files():
        n, k = collect(path)
        for key, locs in n.items():
            names.setdefault(key, set()).update(locs)
        for key, kws in k.items():
            kwargs.setdefault(key, set()).update(kws)

    versions = {}
    for dist in sorted(THIRD_PARTY.values()):
        try:
            versions[dist] = importlib.metadata.version(dist)
        except importlib.metadata.PackageNotFoundError:
            versions[dist] = "not installed"
    print(f"Python {sys.version.split()[0]}; " + ", ".join(f"{p} {v}" for p, v in versions.items()))

    failures = []
    for name in sorted(names):
        try:
            obj = lookup(name)
        except (ImportError, AttributeError) as e:
            failures.append(f"MISSING  {name}  ({type(e).__name__}: {e})  used at {', '.join(sorted(names[name]))}")
            continue
        if bad := accepts(obj, kwargs.get(name, set())):
            failures.append(f"BAD KWARG  {name}({', '.join(sorted(bad))}=...)  used at {', '.join(sorted(names[name]))}")

    print(f"Checked {len(names)} names and keyword arguments for {len(kwargs)} callables.")
    for line in failures:
        print(line)
    print("OK" if not failures else f"{len(failures)} problem(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
