from __future__ import annotations

import json
from pathlib import Path

from storycanon.brief import assemble_brief
from storycanon.db import Canon, find_root
from storycanon.export_bible import export_bible
from storycanon.ingest import ingest_chapter
from storycanon.models import parse_delta
from storycanon.arcs import list_arcs, upsert_arc
from storycanon.auditor import audit_delta, auditor_prompt, load_prose
from storycanon.query import beats_text, get_entity_text, query_canon, shortest_path, status_text
from storycanon.truth import set_truth
from storycanon.viz import write_graph


def _canon() -> Canon:
    return Canon(find_root())


def tool_init_project(premise: str, title: str = "Untitled Novel") -> str:
    canon = Canon(find_root())
    if canon.exists() and canon.db_path.exists():
        # still allow filling dirs
        pass
    canon.init_project(premise=premise, title=title)
    return f"Initialized StoryCanon project at {canon.root} ({title})."


def tool_brief_chapter(
    n: int,
    pov: str | None = None,
    present: str | None = None,
    location: str | None = None,
    token_budget: int | None = None,
) -> str:
    present_list = [p.strip() for p in (present or "").split(",") if p.strip()]
    payload = assemble_brief(
        _canon(),
        n,
        pov=pov,
        present=present_list or None,
        location=location,
        token_budget=token_budget,
    )
    return payload["markdown"]


def tool_ingest_chapter(
    n: int,
    delta_json: str,
    chapter_path: str | None = None,
    strict: bool | None = None,
    force: bool = False,
) -> str:
    canon = _canon()
    data = json.loads(delta_json)
    if "chapter" not in data:
        data["chapter"] = n
    if int(data["chapter"]) != n:
        return f"delta.chapter ({data['chapter']}) does not match n ({n})."
    delta = parse_delta(data)
    path = Path(chapter_path) if chapter_path else None
    result = ingest_chapter(canon, delta, path, strict=strict, force=force)
    return result.render()


def tool_get_entity(name: str) -> str:
    return get_entity_text(_canon(), name)


def tool_query_canon(question: str) -> str:
    return query_canon(_canon(), question)


def tool_path(a: str, b: str) -> str:
    return shortest_path(_canon(), a, b)


def tool_status() -> str:
    return status_text(_canon())


def tool_set_truth(
    slug: str,
    name: str | None = None,
    type: str | None = None,
    status: str | None = None,
    summary: str | None = None,
    attrs_json: str | None = None,
    aliases: str | None = None,
    create_type: str | None = None,
) -> str:
    attrs = json.loads(attrs_json) if attrs_json else None
    alias_list = [a.strip() for a in (aliases or "").split(",") if a.strip()]
    return set_truth(
        _canon(),
        slug,
        name=name,
        type=type,
        status=status,
        summary=summary,
        attrs=attrs,
        aliases=alias_list or None,
        create_type=create_type,
    )


def tool_export_bible() -> str:
    path = export_bible(_canon())
    return f"Wrote markdown bible under {path}"


def tool_visualize(include_closed: bool = True) -> str:
    path = write_graph(_canon(), include_closed=include_closed)
    return f"Wrote the story desk to {path} (graph, timeline, beats, cast). Open that HTML file in a browser."


def tool_list_beats(chapter: int | None = None) -> str:
    return beats_text(_canon(), chapter)


def tool_auditor_prompt(n: int, chapter_path: str | None = None) -> str:
    canon = _canon()
    path = Path(chapter_path) if chapter_path else None
    prose = load_prose(canon, n, path)
    return auditor_prompt(canon, n, prose)


def tool_audit_chapter(n: int, delta_json: str) -> str:
    data = json.loads(delta_json)
    if "chapter" not in data:
        data["chapter"] = n
    result = audit_delta(_canon(), data)
    return result.render()


def tool_list_arcs() -> str:
    rows = list_arcs(_canon())
    if not rows:
        return "No arcs. Use set_arc to add one."
    return json.dumps(rows, indent=2, default=str)


def tool_set_arc(
    title: str,
    start_chapter: int | None = None,
    target_end_chapter: int | None = None,
    climax_chapter: int | None = None,
    status: str = "active",
    summary: str = "",
    arc_id: int | None = None,
) -> str:
    arc = upsert_arc(
        _canon(),
        title,
        start_chapter=start_chapter,
        target_end_chapter=target_end_chapter,
        climax_chapter=climax_chapter,
        status=status,
        summary=summary,
        arc_id=arc_id,
    )
    return json.dumps(arc, indent=2, default=str)


def build_server():
    try:
        from mcp.server.mcpserver import MCPServer as Server
    except ImportError:  # mcp 1.x
        from mcp.server.fastmcp import FastMCP as Server

    mcp = Server("storycanon")

    mcp.tool(name="init_project", description="Create a StoryCanon project from a premise.")(
        tool_init_project
    )
    mcp.tool(
        name="brief_chapter",
        description=(
            "Return a token-capped continuity briefing for chapter N. "
            "Call this BEFORE writing the chapter. present is a comma-separated slug list."
        ),
    )(tool_brief_chapter)
    mcp.tool(
        name="ingest_chapter",
        description=(
            "Commit chapter N to canon. delta_json is the structured delta "
            "(present, location, summary, updates, threads, plants, learned). "
            "Chapter is not canon until this returns OK."
        ),
    )(tool_ingest_chapter)
    mcp.tool(
        name="get_entity",
        description="Current sheet for a character, place, thread, secret, or other entity.",
    )(tool_get_entity)
    mcp.tool(
        name="query_canon",
        description="Ask canon: where is X, who knows Y, open threads, keyword search.",
    )(tool_query_canon)
    mcp.tool(name="path", description="Shortest open-canon path between two names.")(tool_path)
    mcp.tool(
        name="status",
        description="Open threads, due Chekhov guns, flags, stale characters.",
    )(tool_status)
    mcp.tool(
        name="set_truth",
        description="Showrunner override: create or patch an entity without ingesting a chapter.",
    )(tool_set_truth)
    mcp.tool(name="export_bible", description="Export sqlite canon to bible/ markdown snapshots.")(
        tool_export_bible
    )
    mcp.tool(
        name="visualize",
        description="Write the story desk HTML: graph, timeline, beats board, cast, threads.",
    )(tool_visualize)
    mcp.tool(
        name="list_beats",
        description="List story beats (plants, reveals, thread moves). Optional chapter filter.",
    )(tool_list_beats)
    mcp.tool(
        name="auditor_prompt",
        description=(
            "Build the auditor extraction prompt for chapter N. "
            "The DRAFTER must not write delta.json. A separate auditor reads the chapter prose "
            "and this prompt, then returns delta JSON."
        ),
    )(tool_auditor_prompt)
    mcp.tool(
        name="audit_chapter",
        description=(
            "Diff an auditor-extracted delta against canon (locations, injuries, secrets, "
            "illegal power-system jumps). Does not ingest. Call before ingest_chapter."
        ),
    )(tool_audit_chapter)
    mcp.tool(name="list_arcs", description="List macro-arcs (pacing milestones).")(tool_list_arcs)
    mcp.tool(
        name="set_arc",
        description="Create or update a macro-arc (title, start, target end, climax chapter).",
    )(tool_set_arc)

    return mcp


def run_mcp() -> None:
    build_server().run()
