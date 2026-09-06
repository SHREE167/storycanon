from __future__ import annotations

from storycanon.install import OPENAI_TOOLS
from storycanon.serve import build_server, tool_brief_chapter, tool_status


def test_tool_names_are_stable():
    names = {t["function"]["name"] for t in OPENAI_TOOLS}
    assert names == {
        "init_project",
        "brief_chapter",
        "ingest_chapter",
        "get_entity",
        "query_canon",
        "path",
        "status",
        "set_truth",
        "visualize",
        "list_beats",
    }


def test_mcp_server_lists_core_tools():
    import asyncio

    server = build_server()
    listed = server.list_tools()
    if hasattr(listed, "__await__"):
        listed = asyncio.run(listed)
    names = {t.name for t in listed}
    assert {
        "brief_chapter",
        "ingest_chapter",
        "get_entity",
        "query_canon",
        "status",
    } <= names


def test_tool_wrappers_use_project(project, monkeypatch):
    monkeypatch.chdir(project.root)
    text = tool_status()
    assert "Chapters ingested: 0" in text
    brief = tool_brief_chapter(1)
    assert "chapter 1" in brief.lower()
