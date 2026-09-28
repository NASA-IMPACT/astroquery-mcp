"""Generate reference docs (Sphinx site + GitHub wiki) from live docstrings.

Nothing here is hand-maintained: MCP tools come from the FastMCP registry in
server.py, and archive functions come from introspection.discover_all_functions(),
i.e. exactly what the running server exposes.

- Sphinx site (docs/reference/): archive functions use autodoc `automethod`, so Sphinx renders
  the upstream numpy/RST docstrings natively (napoleon + intersphinx links to astropy).
- GitHub wiki (build/wiki/): wikis can't run Sphinx, so docstrings are rendered to Markdown here.

Usage:
    uv run python3 scripts/gen_docs.py --version v0.2.0
"""

import argparse
import asyncio
import inspect
import json
import logging
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import docstring_parser

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Display metadata only. Modules missing here still get documented with a fallback title.
MODULE_META = {
    "simbad": ("SIMBAD", "CDS astronomical database: basic data, cross-identifications, bibliography and measurements for objects outside the solar system."),
    "ned": ("NED", "NASA/IPAC Extragalactic Database for galaxies and extragalactic objects."),
    "vizier": ("VizieR", "CDS service giving access to published astronomical catalogs and data tables."),
    "ads": ("ADS", "NASA Astrophysics Data System literature search. See also the `ads_query_compact` and `ads_get_paper` tools."),
    "mast": ("MAST Observations", "Mikulski Archive for Space Telescopes observations (HST, JWST, TESS, Kepler, ...)."),
    "mast_catalogs": ("MAST Catalogs", "Catalogs hosted at MAST (HSC, Pan-STARRS, TIC, GAIA, ...)."),
    "heasarc": ("HEASARC", "High Energy Astrophysics Science Archive (X-ray and gamma-ray missions)."),
    "irsa": ("IRSA", "NASA/IPAC Infrared Science Archive."),
    "nea": ("NASA Exoplanet Archive", "Confirmed exoplanets, host stars and mission data."),
    "gaia": ("Gaia", "ESA Gaia mission archive (astrometry, photometry, spectra)."),
    "sdss": ("SDSS", "Sloan Digital Sky Survey imaging and spectroscopy."),
    "alma": ("ALMA", "Atacama Large Millimeter/submillimeter Array science archive."),
    "esa_hubble": ("ESA Hubble", "ESA Hubble Space Telescope archive (eHST)."),
    "esa_jwst": ("ESA JWST", "ESA James Webb Space Telescope archive."),
    "xmm_newton": ("XMM-Newton", "ESA XMM-Newton Science Archive."),
    "coordinates": ("Coordinates (SkyCoord)", "Astropy `SkyCoord` helpers: name resolution, constellations, cross-matching."),
}


# ---------------------------------------------------------------------------
# Docstring -> Markdown
# ---------------------------------------------------------------------------

_RST_SUBS = [
    (re.compile(r"``([^`]+)``"), r"`\1`"),                                   # ``literal``
    (re.compile(r":\w+(?::\w+)?:`[^`<]*<([^>]+)>`"), r"`\1`"),               # :role:`text <target>`
    (re.compile(r":\w+(?::\w+)?:`~?(?:[\w.]+\.)?([\w]+)`"), r"`\1`"),        # :role:`~a.b.C`
    (re.compile(r"`([^`<]+?)\s*<(https?://[^>]+)>`__?"), r"[\1](\2)"),      # `text <url>`_
    (re.compile(r"`~(?:[\w.]+\.)?(\w+)`"), r"`\1`"),                         # `~a.b.C`
    (re.compile(r"\s*# doctest:.*$", re.M), ""),
]


def rst_to_md(text: str | None) -> str:
    """Best-effort conversion of RST inline markup to Markdown."""
    if not text:
        return ""
    for pattern, repl in _RST_SUBS:
        text = pattern.sub(repl, text)
    text = re.sub(r"^\.\. (\w+)::\s*(.*)$", lambda m: f"**{m.group(1).capitalize()}:** {m.group(2)}", text, flags=re.M)
    return text.strip()


def cell(text: Any) -> str:
    """Make text safe for a single Markdown table cell."""
    text = rst_to_md(str(text)) if text not in (None, "") else ""
    return re.sub(r"\s*\n\s*", " ", text).replace("|", "\\|")


def github_slug(title: str) -> str:
    """Heading anchor as GitHub renders it (used by Sphinx/MyST too, so links match)."""
    return re.sub(r"[^\w\- ]", "", title.strip().lower()).replace(" ", "-")


def code_block(text: str, lang: str = "python") -> str:
    return f"```{lang}\n{text.strip()}\n```"


def render_examples(text: str) -> str:
    # Doctest-style examples are mostly code; prose lines are kept as comments.
    return code_block(rst_to_md(text), "pycon" if ">>>" in text else "python")


@dataclass
class ParamRow:
    name: str
    type: str
    default: str
    required: bool
    description: str


def params_table(rows: list[ParamRow]) -> str:
    if not rows:
        return "_No parameters._"
    lines = ["| Parameter | Type | Default | Description |", "|---|---|---|---|"]
    for r in rows:
        name = f"`{r.name}`" + (" **(required)**" if r.required else "")
        default = f"`{r.default}`" if r.default else ""
        lines.append(f"| {name} | {cell(r.type)} | {cell(default)} | {cell(r.description)} |")
    return "\n".join(lines)


_NUMPY_HEADER = re.compile(r"^([A-Z][A-Za-z ]+)\n-{3,}\s*$", re.M)
_GOOGLE_HEADER = re.compile(r"^([A-Z][A-Za-z ]+):\s*$")
# Sections already rendered from the parsed docstring (params table, returns, raises).
_PARSED_SECTIONS = {"parameters", "other parameters", "args", "arguments", "returns", "raises", "yields", "attributes"}


def raw_sections(raw: str) -> list[tuple[str, str]]:
    """Split a numpy- or Google-style docstring into (header, body) pairs, keeping bodies verbatim.

    docstring_parser fragments doctest examples and drops non-standard sections
    (e.g. "Token savings:"), so everything except params/returns/raises is read from here.
    """
    if _NUMPY_HEADER.search(raw):
        chunks = _NUMPY_HEADER.split(raw)[1:]
        return [(h.strip(), b.strip("\n")) for h, b in zip(chunks[::2], chunks[1::2])]
    sections: list[tuple[str, list[str]]] = []
    for line in raw.splitlines():
        m = _GOOGLE_HEADER.match(line)
        if m:
            sections.append((m.group(1), []))
        elif sections and (not line.strip() or line[:1].isspace()):
            sections[-1][1].append(line)
        elif sections:
            sections.append(("", [line]))  # unindented text ends the section
    return [(h, inspect.cleandoc("\n".join(b))) for h, b in sections if h]


def render_docstring_body(doc: docstring_parser.Docstring, rows: list[ParamRow], raw: str) -> list[str]:
    out = []
    if doc.long_description:
        out.append(rst_to_md(doc.long_description))
    out += ["**Parameters**", params_table(rows)]
    if doc.returns and (doc.returns.description or doc.returns.type_name):
        ret_type = f"`{doc.returns.type_name}` — " if doc.returns.type_name else ""
        out += ["**Returns**", rst_to_md(ret_type + (doc.returns.description or ""))]
    if doc.raises:
        out += ["**Raises**", "\n".join(f"- `{r.type_name}`: {cell(r.description)}" for r in doc.raises)]
    for header, body in raw_sections(raw):
        if header.lower() in _PARSED_SECTIONS or not body.strip():
            continue
        is_code = header.lower().startswith("example") or ">>>" in body
        out += [f"**{header}**", render_examples(body) if is_code else rst_to_md(body)]
    return out


# ---------------------------------------------------------------------------
# Data collection
# ---------------------------------------------------------------------------

def collect_tools() -> tuple[str, list[dict]]:
    import server

    registry = asyncio.run(server.mcp.get_tools())
    tools = []
    for name, tool in registry.items():
        schema = tool.parameters or {}
        tools.append({
            "name": name,
            "doc": tool.description or "",
            "properties": schema.get("properties", {}),
            "required": set(schema.get("required", [])),
            "output_schema": tool.output_schema or {},
        })
    return server.mcp.instructions or "", tools


def schema_type(prop: dict) -> str:
    if "enum" in prop:
        return " \\| ".join(json.dumps(v) for v in prop["enum"])
    if "anyOf" in prop:
        return " or ".join(schema_type(p) for p in prop["anyOf"])
    return prop.get("type", "any")


def collect_archives() -> dict[str, list]:
    from introspection import discover_all_functions

    return discover_all_functions()


# ---------------------------------------------------------------------------
# Page rendering. `link(page_id, anchor)` abstracts over MkDocs vs wiki URLs.
# ---------------------------------------------------------------------------

LinkFn = Callable[[str, str], str]


def title_for(module: str) -> str:
    return MODULE_META.get(module, (module.replace("_", " ").title(), ""))[0]


def render_tool(t: dict) -> str:
    doc = docstring_parser.parse(t["doc"])
    descs = {p.arg_name: p.description for p in doc.params}
    rows = [
        ParamRow(
            name=name,
            type=schema_type(prop),
            default=json.dumps(prop["default"]) if "default" in prop else "",
            required=name in t["required"],
            description=descs.get(name, prop.get("description", "")),
        )
        for name, prop in t["properties"].items()
    ]
    parts = [f"## `{t['name']}`", rst_to_md(doc.short_description or "")]
    parts += render_docstring_body(doc, rows, t["doc"])
    # Only typed returns (e.g. Pydantic models) produce a useful schema; plain dict[str, Any] has no properties.
    if t["output_schema"].get("properties"):
        parts += ["**Output schema**", code_block(json.dumps(t["output_schema"], indent=2), "json")]
    return "\n\n".join(p for p in parts if p)


def render_tools_page(instructions: str, tools: list[dict]) -> str:
    parts = [
        "# MCP Tools",
        f"The server registers **{len(tools)} MCP tools**. The `astroquery_*` tools are generic: "
        "they can discover and call any archive function listed under Archives. "
        "The `ads_*` tools are optimized shortcuts for literature search.",
        "| Tool | Summary |\n|---|---|\n" + "\n".join(
            f"| [`{t['name']}`](#{t['name']}) | {cell(docstring_parser.parse(t['doc']).short_description)} |"
            for t in tools
        ),
    ]
    parts += [render_tool(t) for t in tools]
    parts += [
        "## Server instructions",
        "This text is sent to the AI client when it connects, to explain how to use the tools.",
        code_block(instructions.strip(), "markdown"),
    ]
    return "\n\n".join(parts) + "\n"


def call_example(module: str, fn) -> str:
    sig = inspect.signature(fn.callable)
    required = {
        n: f"<{n}>"
        for n, p in sig.parameters.items()
        if n not in ("self", "cls")
        and p.default is inspect.Parameter.empty
        and p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)
    }
    return code_block(
        f'astroquery_execute(\n    module_name="{module}",\n    function_name="{fn.method_name}",\n'
        f"    params={json.dumps(required)},\n)"
    )


def autodoc_directive(module: str, fn) -> str:
    """autodoc directive + importable path (astroquery exposes instances, e.g. Simbad = SimbadClass())."""
    import importlib

    from introspection import ASTROQUERY_MODULES

    mod_path, _, attr = ASTROQUERY_MODULES[module].rpartition(".")
    obj = getattr(importlib.import_module(mod_path), attr)
    owner = obj if isinstance(obj, type) else type(obj)
    kind = "autoproperty" if isinstance(inspect.getattr_static(owner, fn.method_name, None), property) else "automethod"
    return f".. {kind}:: {owner.__module__}.{owner.__qualname__}.{fn.method_name}"


def render_function(module: str, fn, sphinx: bool = False) -> str:
    if sphinx:
        return "\n\n".join([
            f"### `{fn.method_name}`",
            "**Call via MCP**",
            call_example(module, fn),
            f"```{{eval-rst}}\n{autodoc_directive(module, fn)}\n   :no-index:\n```",
        ])
    raw = inspect.getdoc(fn.callable) or ""
    try:
        doc = docstring_parser.parse(raw)
    except Exception:
        doc = docstring_parser.Docstring()
        doc.short_description = raw
    descs = {p.arg_name: p.description for p in doc.params}
    types = {p.arg_name: p.type_name for p in doc.params}
    sig = inspect.signature(fn.callable)
    rows = []
    for name, p in sig.parameters.items():
        if name in ("self", "cls"):
            continue
        variadic = p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD)
        shown = ("*" if p.kind == p.VAR_POSITIONAL else "**" if variadic else "") + name
        rows.append(ParamRow(
            name=shown,
            type=types.get(name) or fn_type(fn, name),
            default="" if p.default is inspect.Parameter.empty else repr(p.default),
            required=p.default is inspect.Parameter.empty and not variadic,
            description=descs.get(name, ""),
        ))
    params = [p for p in sig.parameters.values() if p.name not in ("self", "cls")]
    parts = [
        f"### `{fn.method_name}`",
        rst_to_md(doc.short_description or "_No description in upstream docstring._"),
        code_block(f"{fn.class_name}.{fn.method_name}{sig.replace(parameters=params)}"),
        "**Call via MCP**",
        call_example(module, fn),
    ]
    parts += render_docstring_body(doc, rows, raw)
    return "\n\n".join(p for p in parts if p)


def fn_type(fn, name: str) -> str:
    for p in fn.parameters:
        if p.name == name and p.type_hint != "Any":
            return p.type_hint
    return ""


def render_archive_page(module: str, functions: list, sphinx: bool = False) -> str:
    title, blurb = MODULE_META.get(module, (title_for(module), ""))
    from introspection import ASTROQUERY_MODULES

    class_path = ASTROQUERY_MODULES.get(module, "")
    functions = sorted(functions, key=lambda f: f.method_name)
    parts = [
        f"# {title}",
        blurb,
        f"- **Module name:** `{module}`\n- **Python class:** `{class_path}`\n- **Functions:** {len(functions)}",
        "Call any function below with the `astroquery_execute` MCP tool. "
        "Descriptions are taken from the upstream astroquery/astropy docstrings.",
        "| Function | Summary |\n|---|---|\n" + "\n".join(
            f"| [`{f.method_name}`](#{f.method_name}) | {cell(f.description)} |" for f in functions
        ),
        "## Functions",
    ]
    parts += [render_function(module, f, sphinx) for f in functions]
    return "\n\n".join(p for p in parts if p) + "\n"


def render_archives_index(archives: dict[str, list], link: LinkFn, toctree: str = "") -> str:
    total = sum(len(v) for v in archives.values())
    rows = "\n".join(
        f"| [{title_for(m)}]({link('archive:' + m, '')}) | `{m}` | {len(fns)} | {cell(MODULE_META.get(m, ('', ''))[1])} |"
        for m, fns in archives.items()
    )
    return (
        "# Archives\n\n"
        f"The server exposes **{total} functions** across **{len(archives)} modules**. "
        "Use the module name as `module_name` in `astroquery_execute`.\n\n"
        "| Archive | Module name | Functions | Description |\n|---|---|---|---|\n"
        f"{rows}\n"
        f"{toctree}"
    )


# ---------------------------------------------------------------------------
# Output targets
# ---------------------------------------------------------------------------

def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def build_site(out: Path, instructions, tools, archives) -> None:
    """Write generated MyST pages into the Sphinx source tree (docs/reference/)."""
    def link(page_id: str, anchor: str) -> str:
        kind, _, name = page_id.partition(":")
        return {"archive": f"{name}.md"}[kind] + (f"#{anchor}" if anchor else "")

    ref = out / "reference"
    shutil.rmtree(ref, ignore_errors=True)
    toctree = "\n```{toctree}\n:hidden:\n\n" + "\n".join(archives) + "\n```\n"
    write(ref / "tools.md", render_tools_page(instructions, tools))
    write(ref / "archives" / "index.md", render_archives_index(archives, link, toctree))
    for m, fns in archives.items():
        write(ref / "archives" / f"{m}.md", render_archive_page(m, fns, sphinx=True))


def wiki_page(module: str) -> str:
    return "Archive-" + re.sub(r"[^A-Za-z0-9]+", "-", title_for(module)).strip("-")


def build_wiki(out: Path, version: str, home_md: str, instructions, tools, archives) -> None:
    """Write a flat set of pages for the GitHub wiki (separate git repo)."""
    def link(page_id: str, anchor: str) -> str:
        kind, _, name = page_id.partition(":")
        return {"archive": wiki_page(name)}[kind] + (f"#{anchor}" if anchor else "")

    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    # Wiki pages get their title from the filename, so drop the leading H1.
    strip_h1 = lambda s: re.sub(r"\A# .*\n+", "", s)
    write(out / "Home.md", strip_h1(home_md))
    write(out / "MCP-Tools.md", strip_h1(render_tools_page(instructions, tools)))
    write(out / "Archives.md", strip_h1(render_archives_index(archives, link)))
    for m, fns in archives.items():
        write(out / f"{wiki_page(m)}.md", strip_h1(render_archive_page(m, fns)))

    sidebar = [f"**astroquery-mcp {version}**", "", "- [[Home]]", "- [[MCP Tools|MCP-Tools]]", "- [[Archives]]"]
    sidebar += [f"  - [[{title_for(m)}|{wiki_page(m)}]]" for m in archives]
    write(out / "_Sidebar.md", "\n".join(sidebar) + "\n")
    write(out / "_Footer.md", "Auto-generated from source docstrings on each release. Do not edit here — changes are overwritten.\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", default="dev", help="Release version shown in the docs")
    parser.add_argument("--docs-dir", type=Path, default=ROOT / "docs")
    parser.add_argument("--wiki-dir", type=Path, default=ROOT / "build" / "wiki")
    args = parser.parse_args()

    # Importing server/astroquery is noisy (and auth logs token hints); keep output clean.
    logging.disable(logging.CRITICAL)
    instructions, tools = collect_tools()
    archives = collect_archives()
    logging.disable(logging.NOTSET)

    build_site(args.docs_dir, instructions, tools, archives)
    home = re.sub(r"```\{toctree\}.*?```\n?", "", (args.docs_dir / "index.md").read_text(), flags=re.S)
    home = home.replace("reference/tools.md", "MCP-Tools").replace("reference/archives/index.md", "Archives")
    build_wiki(args.wiki_dir, args.version, home, instructions, tools, archives)

    total = sum(len(v) for v in archives.values())
    print(f"Generated docs for {len(tools)} MCP tools and {total} functions in {len(archives)} archives ({args.version})")


if __name__ == "__main__":
    main()
