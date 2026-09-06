from __future__ import annotations

import json
from collections import Counter
from importlib.resources import files
from pathlib import Path
from typing import Any

from storycanon.db import Canon

TYPE_COLORS = {
    "character": "#7dd3fc",
    "location": "#86efac",
    "thread": "#fbbf24",
    "secret": "#e879f9",
    "faction": "#c4b5fd",
    "item": "#fdba74",
    "rule": "#94a3b8",
    "event": "#fca5a5",
    "plant": "#fb7185",
}


def graph_payload(canon: Canon, *, include_closed: bool = True) -> dict[str, Any]:
    return desk_payload(canon, include_closed=include_closed)


def desk_payload(canon: Canon, *, include_closed: bool = True) -> dict[str, Any]:
    title = canon.meta("title") or str(canon.cfg.get("title") or "Untitled")
    premise = canon.meta("premise") or str(canon.cfg.get("premise") or "")
    last = canon.last_chapter_n()
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    seen_slugs: set[str] = set()

    with canon.connect() as conn:
        entities = list(conn.execute("SELECT * FROM entities"))
        edge_sql = (
            "SELECT e.*, s.slug AS src_slug, d.slug AS dst_slug "
            "FROM edges e JOIN entities s ON s.id = e.src_id JOIN entities d ON d.id = e.dst_id"
        )
        if not include_closed:
            edge_sql += " WHERE e.to_chapter IS NULL"
        edge_rows = list(conn.execute(edge_sql))
        plants = [dict(r) for r in conn.execute("SELECT * FROM plants")]
        knowledge = list(conn.execute("SELECT * FROM knowledge"))
        beats = [dict(r) for r in conn.execute("SELECT * FROM beats ORDER BY chapter, sort")]
        flags = [
            dict(r)
            for r in conn.execute(
                "SELECT type, severity, chapter, body, status FROM flags WHERE status = 'open'"
            )
        ]
        chapters = [dict(r) for r in conn.execute("SELECT * FROM chapters ORDER BY n")]

    degree: Counter[str] = Counter()
    for row in edge_rows:
        degree[row["src_slug"]] += 1
        degree[row["dst_slug"]] += 1

    for row in entities:
        attrs = json.loads(row["attrs_json"] or "{}")
        aliases = json.loads(row["aliases_json"] or "[]")
        etype = row["type"]
        dead = row["status"] in {"dead", "destroyed"}
        nodes.append(
            {
                "id": row["slug"],
                "label": row["name"],
                "type": etype,
                "status": row["status"],
                "summary": row["summary"] or "",
                "aliases": aliases,
                "attrs": attrs,
                "last_seen": row["last_seen_chapter"],
                "first_chapter": row["first_chapter"],
                "color": TYPE_COLORS.get(etype, "#d4b07a"),
                "dim": dead,
                "degree": int(degree[row["slug"]]),
            }
        )
        seen_slugs.add(row["slug"])

    for plant in plants:
        if plant["slug"] in seen_slugs:
            continue
        paid = plant["paid_chapter"] is not None
        due = (not paid) and plant["planted_chapter"] + plant["due_after"] <= (last or 0) + 1
        nodes.append(
            {
                "id": plant["slug"],
                "label": plant["slug"].replace("-", " ").title(),
                "type": "plant",
                "status": "paid" if paid else "due" if due else "planted",
                "summary": plant["note"] or "",
                "aliases": [],
                "attrs": {
                    "kind": plant["kind"],
                    "planted": plant["planted_chapter"],
                    "due_after": plant["due_after"],
                    "paid": plant["paid_chapter"],
                },
                "last_seen": plant["paid_chapter"] or plant["planted_chapter"],
                "first_chapter": plant["planted_chapter"],
                "color": TYPE_COLORS["plant"],
                "dim": paid,
                "degree": int(degree[plant["slug"]]),
            }
        )
        seen_slugs.add(plant["slug"])

    names = {n["id"]: n["label"] for n in nodes}
    for i, row in enumerate(edge_rows):
        closed = row["to_chapter"] is not None
        edges.append(
            {
                "id": f"e{i}",
                "source": row["src_slug"],
                "target": row["dst_slug"],
                "rel": row["rel"],
                "from_chapter": row["from_chapter"],
                "to_chapter": row["to_chapter"],
                "evidence": row["evidence_chapter"],
                "note": row["note"] or "",
                "closed": closed,
            }
        )

    beats_by_ch: dict[int, list[dict[str, Any]]] = {}
    for beat in beats:
        beat["entity_name"] = names.get(beat.get("entity_slug") or "", beat.get("entity_slug"))
        beats_by_ch.setdefault(beat["chapter"], []).append(beat)

    chapter_list = []
    for ch in chapters:
        chapter_list.append(
            {
                "n": ch["n"],
                "title": ch.get("title") or "",
                "pov": ch.get("pov") or "",
                "location": ch.get("location") or "",
                "summary": ch.get("summary") or "",
                "present": json.loads(ch.get("present_json") or "[]"),
                "word_count": ch.get("word_count") or 0,
                "beats": beats_by_ch.get(ch["n"], []),
            }
        )

    threads = [n for n in nodes if n["type"] == "thread"]
    due_plants = [
        p
        for p in plants
        if p["paid_chapter"] is None
        and p["planted_chapter"] + p["due_after"] <= (last or 0) + 1
    ]
    type_counts = Counter(n["type"] for n in nodes)

    return {
        "title": title,
        "premise": premise,
        "chapters": last,
        "nodes": nodes,
        "edges": edges,
        "chapter_list": chapter_list,
        "beats": beats,
        "plants": plants,
        "threads": threads,
        "flags": flags,
        "knowledge_count": len(knowledge),
        "include_closed": include_closed,
        "stats": {
            "characters": type_counts.get("character", 0),
            "locations": type_counts.get("location", 0),
            "threads": type_counts.get("thread", 0),
            "secrets": type_counts.get("secret", 0),
            "beats": len(beats),
            "due_plants": len(due_plants),
            "open_flags": len(flags),
        },
    }


def write_graph(canon: Canon, *, include_closed: bool = True) -> Path:
    payload = desk_payload(canon, include_closed=include_closed)
    out_dir = canon.canon_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "graph.json"
    html_path = out_dir / "graph.html"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    template = files("storycanon").joinpath("data/desk.html").read_text(encoding="utf-8")
    blob = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c")
    html = template.replace("/*__STORYCANON_DATA__*/ null", blob)
    html_path.write_text(html, encoding="utf-8")
    # Easy-open copy at project root of the canon folder's parent
    easy = canon.root / "storycanon-desk.html"
    easy.write_text(html, encoding="utf-8")
    return html_path


def open_graph(path: Path) -> None:
    import webbrowser

    webbrowser.open(path.resolve().as_uri())
