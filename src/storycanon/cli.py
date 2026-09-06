from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from storycanon import __version__
from storycanon.brief import assemble_brief
from storycanon.db import Canon, find_root
from storycanon.export_bible import export_bible
from storycanon.ingest import ingest_chapter
from storycanon.install import OPENAI_TOOLS, install_project
from storycanon.models import DELTA_JSON_SCHEMA, parse_delta
from storycanon.query import beats_text, get_entity_text, query_canon, shortest_path, status_text
from storycanon.truth import set_truth
from storycanon.viz import open_graph, write_graph

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Local continuity engine for long AI-written novels — canon, beats, and a story desk.",
)
console = Console()


def _canon() -> Canon:
    return Canon(find_root())


def _refresh_desk(canon: Canon) -> None:
    try:
        write_graph(canon)
    except Exception as exc:
        console.print(f"[dim]desk not refreshed: {exc}[/dim]")


@app.command()
def version() -> None:
    """Print version."""
    console.print(__version__)


@app.command()
def init(
    premise: str = typer.Argument(..., help="One-paragraph premise"),
    title: str = typer.Option("Untitled Novel", "--title", "-t"),
) -> None:
    """Create a novel project in the current directory."""
    canon = Canon(Path.cwd())
    canon.init_project(premise=premise, title=title)
    _refresh_desk(canon)
    console.print(
        Panel.fit(
            f"[bold]{title}[/bold]\n{premise}\n\n[dim]{canon.root}[/dim]",
            title="StoryCanon",
            border_style="gold1",
        )
    )


@app.command()
def brief(
    n: int = typer.Argument(..., min=1),
    pov: Optional[str] = typer.Option(None),
    present: Optional[str] = typer.Option(None, help="comma-separated slugs"),
    location: Optional[str] = typer.Option(None),
    budget: Optional[int] = typer.Option(None, "--budget", help="token budget"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Token-capped continuity briefing for chapter N."""
    present_list = [p.strip() for p in (present or "").split(",") if p.strip()]
    payload = assemble_brief(
        _canon(),
        n,
        pov=pov,
        present=present_list or None,
        location=location,
        token_budget=budget,
    )
    if json_out:
        console.print_json(data=payload)
    else:
        console.print(payload["markdown"], markup=False)


@app.command()
def ingest(
    n: int = typer.Argument(..., min=1),
    chapter_path: Optional[Path] = typer.Argument(None),
    delta: Optional[Path] = typer.Option(None, "--delta", help="JSON file"),
    delta_json: Optional[str] = typer.Option(None, "--delta-json"),
    lenient: bool = typer.Option(False, "--lenient"),
    force: bool = typer.Option(False, "--force"),
    viz: bool = typer.Option(True, "--viz/--no-viz", help="Refresh the story desk HTML"),
) -> None:
    """Commit chapter N + structured delta into canon."""
    if not delta and not delta_json:
        raise typer.BadParameter("pass --delta FILE or --delta-json '{...}'")
    if delta:
        data = json.loads(Path(delta).read_text(encoding="utf-8"))
    else:
        data = json.loads(delta_json or "{}")
    if "chapter" not in data:
        data["chapter"] = n
    parsed = parse_delta(data)
    if parsed.chapter != n:
        raise typer.BadParameter(f"delta.chapter ({parsed.chapter}) != {n}")
    canon = _canon()
    result = ingest_chapter(
        canon,
        parsed,
        chapter_path,
        strict=not lenient,
        force=force,
    )
    style = "green" if result.ok else "red"
    console.print(Panel(Text(result.render()), title="ingest", border_style=style))
    if result.ok and viz:
        _refresh_desk(canon)
    if not result.ok:
        raise typer.Exit(code=1)


@app.command("get")
def get_cmd(name: str) -> None:
    """Print the current sheet for an entity."""
    console.print(get_entity_text(_canon(), name), markup=False)


@app.command()
def query(question: str) -> None:
    """Ask canon a question."""
    console.print(query_canon(_canon(), question), markup=False)


@app.command("path")
def path_cmd(a: str, b: str) -> None:
    """Shortest open-canon path between two names."""
    console.print(shortest_path(_canon(), a, b), markup=False)


@app.command()
def status() -> None:
    """Open threads, due plants, flags, stale characters."""
    console.print(status_text(_canon()), markup=False)


@app.command()
def beats(
    chapter: Optional[int] = typer.Option(None, "--chapter", "-c"),
) -> None:
    """List recorded story beats (plants, reveals, thread moves)."""
    console.print(beats_text(_canon(), chapter), markup=False)


@app.command("auditor-prompt")
def auditor_prompt_cmd(
    n: int = typer.Argument(..., min=1),
    chapter_path: Optional[Path] = typer.Argument(None),
) -> None:
    """Print the auditor extraction prompt for chapter N (drafter must not write the delta)."""
    from storycanon.auditor import auditor_prompt, load_prose

    canon = _canon()
    prose = load_prose(canon, n, chapter_path)
    console.print(auditor_prompt(canon, n, prose), markup=False)


@app.command()
def audit(
    n: int = typer.Argument(..., min=1),
    delta: Optional[Path] = typer.Option(None, "--delta"),
    delta_json: Optional[str] = typer.Option(None, "--delta-json"),
) -> None:
    """Diff an auditor-extracted delta against canon. Does not ingest."""
    from storycanon.auditor import audit_delta

    if not delta and not delta_json:
        raise typer.BadParameter("pass --delta FILE or --delta-json '{...}'")
    data = json.loads(Path(delta).read_text(encoding="utf-8") if delta else delta_json or "{}")
    if "chapter" not in data:
        data["chapter"] = n
    result = audit_delta(_canon(), data)
    console.print(Panel(Text(result.render()), title="audit", border_style="green" if result.ok else "red"))
    if not result.ok:
        raise typer.Exit(code=1)


@app.command("plugin-init")
def plugin_init_cmd(name: str = typer.Argument("cultivation")) -> None:
    """Copy a bundled progression plugin into plugins/."""
    from storycanon.progression import copy_bundled_plugin

    path = copy_bundled_plugin(_canon(), name)
    console.print(f"Wrote {path}")


@app.command("arc-add")
def arc_add_cmd(
    title: str,
    start: Optional[int] = typer.Option(None, "--start"),
    end: Optional[int] = typer.Option(None, "--end"),
    climax: Optional[int] = typer.Option(None, "--climax"),
    status: str = typer.Option("active"),
    summary: str = typer.Option("", "--summary"),
) -> None:
    """Register a macro-arc (pacing target for briefings)."""
    from storycanon.arcs import upsert_arc

    arc = upsert_arc(
        _canon(),
        title,
        start_chapter=start,
        target_end_chapter=end,
        climax_chapter=climax,
        status=status,
        summary=summary,
    )
    console.print(json.dumps(arc, indent=2, default=str))


@app.command()
def arcs() -> None:
    """List macro-arcs."""
    from storycanon.arcs import list_arcs

    rows = list_arcs(_canon())
    if not rows:
        console.print("No arcs. Add one with `storycanon arc-add \"Title\" --start 1 --end 40 --climax 35`.")
        return
    table = Table(title="Arcs")
    table.add_column("id")
    table.add_column("title")
    table.add_column("start")
    table.add_column("end")
    table.add_column("climax")
    table.add_column("status")
    for row in rows:
        table.add_row(
            str(row["id"]),
            str(row["title"]),
            str(row.get("start_chapter") or ""),
            str(row.get("target_end_chapter") or ""),
            str(row.get("climax_chapter") or ""),
            str(row.get("status") or ""),
        )
    console.print(table)


@app.command("set-truth")
def set_truth_cmd(
    slug: str,
    name: Optional[str] = typer.Option(None),
    type: Optional[str] = typer.Option(None, "--type"),
    status: Optional[str] = typer.Option(None),
    summary: Optional[str] = typer.Option(None),
    attrs_json: Optional[str] = typer.Option(None, "--attrs"),
    aliases: Optional[str] = typer.Option(None),
    create_type: Optional[str] = typer.Option(None, "--create"),
) -> None:
    """Showrunner override: create or patch an entity."""
    attrs = json.loads(attrs_json) if attrs_json else None
    alias_list = [a.strip() for a in (aliases or "").split(",") if a.strip()]
    canon = _canon()
    console.print(
        set_truth(
            canon,
            slug,
            name=name,
            type=type,
            status=status,
            summary=summary,
            attrs=attrs,
            aliases=alias_list or None,
            create_type=create_type,
        )
    )
    _refresh_desk(canon)


@app.command("export-bible")
def export_bible_cmd() -> None:
    """Write bible/ markdown from sqlite canon."""
    path = export_bible(_canon())
    console.print(f"Wrote {path}")


@app.command()
def viz(
    open_browser: bool = typer.Option(True, "--open/--no-open", help="Open the desk in the browser"),
    history: bool = typer.Option(
        True, "--history/--no-history", help="Include past (closed) edges as dashed lines"
    ),
) -> None:
    """Build the interactive story desk (graph, timeline, beats, cast)."""
    canon = _canon()
    path = write_graph(canon, include_closed=history)
    easy = canon.root / "storycanon-desk.html"
    console.print(f"Desk: [bold]{path}[/bold]")
    if easy.exists():
        console.print(f"Copy: {easy}")
    if open_browser:
        open_graph(path)


@app.command()
def desk(
    open_browser: bool = typer.Option(True, "--open/--no-open"),
) -> None:
    """Alias for viz — open the story desk."""
    canon = _canon()
    path = write_graph(canon)
    console.print(f"Desk: [bold]{path}[/bold]")
    if open_browser:
        open_graph(path)


@app.command()
def mcp() -> None:
    """Start the MCP stdio server for agents."""
    from storycanon.serve import run_mcp

    run_mcp()


@app.command()
def install() -> None:
    """Wire MCP + skill files into the current novel project (Antigravity, Gemini, generic)."""
    written = install_project()
    table = Table(title="Agent files")
    table.add_column("path")
    for item in written:
        table.add_row(item)
    console.print(table)


@app.command("tools-json")
def tools_json() -> None:
    """Print OpenAI/OpenRouter-compatible tool definitions."""
    console.print_json(data={"tools": OPENAI_TOOLS, "delta_schema": DELTA_JSON_SCHEMA})
