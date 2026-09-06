from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path

from storycanon.db import find_root
from storycanon.models import DELTA_JSON_SCHEMA

OPENAI_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "init_project",
            "description": "Create a StoryCanon project in the current directory from a premise.",
            "parameters": {
                "type": "object",
                "required": ["premise"],
                "properties": {
                    "premise": {"type": "string"},
                    "title": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "brief_chapter",
            "description": "Token-capped continuity briefing for chapter N. Call BEFORE writing.",
            "parameters": {
                "type": "object",
                "required": ["n"],
                "properties": {
                    "n": {"type": "integer"},
                    "pov": {"type": "string"},
                    "present": {"type": "string", "description": "comma-separated slugs"},
                    "location": {"type": "string"},
                    "token_budget": {"type": "integer"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ingest_chapter",
            "description": "Commit chapter N + structured delta. Not canon until OK.",
            "parameters": {
                "type": "object",
                "required": ["n", "delta_json"],
                "properties": {
                    "n": {"type": "integer"},
                    "delta_json": {"type": "string", "description": "JSON object matching the delta schema"},
                    "chapter_path": {"type": "string"},
                    "strict": {"type": "boolean"},
                    "force": {"type": "boolean"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_entity",
            "description": "Current sheet for an entity by name or slug.",
            "parameters": {
                "type": "object",
                "required": ["name"],
                "properties": {"name": {"type": "string"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_canon",
            "description": "Ask: where is X, who knows Y, open threads, keyword search.",
            "parameters": {
                "type": "object",
                "required": ["question"],
                "properties": {"question": {"type": "string"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "path",
            "description": "Shortest open-canon path between two names.",
            "parameters": {
                "type": "object",
                "required": ["a", "b"],
                "properties": {"a": {"type": "string"}, "b": {"type": "string"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "status",
            "description": "Open threads, due plants, flags, stale characters.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_truth",
            "description": "Showrunner override to create or patch an entity.",
            "parameters": {
                "type": "object",
                "required": ["slug"],
                "properties": {
                    "slug": {"type": "string"},
                    "name": {"type": "string"},
                    "type": {"type": "string"},
                    "status": {"type": "string"},
                    "summary": {"type": "string"},
                    "attrs_json": {"type": "string"},
                    "aliases": {"type": "string"},
                    "create_type": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "visualize",
            "description": "Write the story desk HTML: graph, timeline, beats board, cast, threads.",
            "parameters": {
                "type": "object",
                "properties": {
                    "include_closed": {
                        "type": "boolean",
                        "description": "Include past/closed edges as dashed lines (default true).",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_beats",
            "description": "List story beats (plants, reveals, thread moves). Optional chapter filter.",
            "parameters": {
                "type": "object",
                "properties": {"chapter": {"type": "integer"}},
            },
        },
    },
]


def _skill_text() -> str:
    here = Path(__file__).resolve().parent
    for candidate in (
        here.parents[2] / "skills" / "storycanon" / "SKILL.md",
        here / "data" / "SKILL.md",
    ):
        if candidate.exists():
            return candidate.read_text(encoding="utf-8")
    return files("storycanon").joinpath("data/SKILL.md").read_text(encoding="utf-8")


def install_project(root: Path | None = None) -> list[str]:
    root = find_root(root)
    written: list[str] = []

    skill_dir = root / ".agents" / "skills" / "storycanon"
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_path = skill_dir / "SKILL.md"
    skill_path.write_text(_skill_text(), encoding="utf-8")
    written.append(str(skill_path))

    mcp_path = root / ".agents" / "mcp_config.json"
    mcp_cfg = {}
    if mcp_path.exists():
        try:
            mcp_cfg = json.loads(mcp_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            mcp_cfg = {}
    servers = mcp_cfg.setdefault("mcpServers", {})
    servers["storycanon"] = {
        "command": "storycanon",
        "args": ["mcp"],
    }
    mcp_path.write_text(json.dumps(mcp_cfg, indent=2) + "\n", encoding="utf-8")
    written.append(str(mcp_path))

    gemini_dir = root / ".gemini"
    gemini_dir.mkdir(exist_ok=True)
    gemini_settings = gemini_dir / "settings.json"
    settings: dict = {}
    if gemini_settings.exists():
        try:
            settings = json.loads(gemini_settings.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            settings = {}
    mcp_servers = settings.setdefault("mcpServers", {})
    mcp_servers["storycanon"] = {"command": "storycanon", "args": ["mcp"]}
    gemini_settings.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    written.append(str(gemini_settings))

    tools_dir = root / ".storycanon"
    tools_dir.mkdir(exist_ok=True)
    tools_path = tools_dir / "tools.json"
    tools_path.write_text(
        json.dumps(
            {"tools": OPENAI_TOOLS, "delta_schema": DELTA_JSON_SCHEMA},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    written.append(str(tools_path))

    agents = root / "AGENTS.md"
    block = (
        "\n## StoryCanon\n\n"
        "This is a long-form novel project. Use the `storycanon` MCP tools.\n"
        "Never write chapter N without `brief_chapter`. "
        "Never treat a chapter as canon until `ingest_chapter` returns OK.\n"
    )
    if agents.exists():
        text = agents.read_text(encoding="utf-8")
        if "StoryCanon" not in text:
            agents.write_text(text.rstrip() + "\n" + block, encoding="utf-8")
            written.append(str(agents))
    else:
        agents.write_text("# Agents\n" + block, encoding="utf-8")
        written.append(str(agents))

    return written
