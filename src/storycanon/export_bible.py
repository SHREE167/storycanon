from __future__ import annotations

from pathlib import Path

from storycanon.db import Canon


def export_bible(canon: Canon) -> Path:
    root = canon.bible_dir
    root.mkdir(parents=True, exist_ok=True)
    (root / "characters").mkdir(exist_ok=True)
    (root / "threads").mkdir(exist_ok=True)
    (root / "world").mkdir(exist_ok=True)

    title = canon.meta("title") or canon.cfg.get("title") or "Untitled"
    premise = canon.meta("premise") or canon.cfg.get("premise") or ""
    (root / "premise.md").write_text(
        f"# {title}\n\n{premise}\n", encoding="utf-8"
    )

    folders = {
        "character": root / "characters",
        "thread": root / "threads",
        "location": root / "world",
        "faction": root / "world",
        "item": root / "world",
        "rule": root / "world",
        "secret": root / "world",
        "event": root / "world",
    }
    for ent in canon.list_entities():
        dest_dir = folders.get(ent.type, root / "world")
        body = "\n".join(ent.sheet_lines()) + "\n"
        (dest_dir / f"{ent.slug}.md").write_text(body, encoding="utf-8")

    chapters = canon.recent_chapters(10_000)
    timeline = [f"# Timeline — {title}\n"]
    for ch in chapters:
        timeline.append(f"## ch.{ch['n']} — {ch.get('title') or ''}".rstrip(" —"))
        meta = []
        if ch.get("pov"):
            meta.append(f"POV: {ch['pov']}")
        if ch.get("location"):
            meta.append(f"at {ch['location']}")
        if meta:
            timeline.append("*" + " · ".join(meta) + "*")
        timeline.append(ch.get("summary") or "")
        timeline.append("")
    (root / "timeline.md").write_text("\n".join(timeline), encoding="utf-8")
    return root
