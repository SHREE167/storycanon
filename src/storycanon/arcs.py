from __future__ import annotations

from typing import Any

from storycanon.db import Canon


def list_arcs(canon: Canon) -> list[dict[str, Any]]:
    with canon.connect() as conn:
        rows = conn.execute(
            "SELECT * FROM arcs ORDER BY COALESCE(start_chapter, 0), id"
        ).fetchall()
        return [dict(r) for r in rows]


def upsert_arc(
    canon: Canon,
    title: str,
    *,
    start_chapter: int | None = None,
    target_end_chapter: int | None = None,
    climax_chapter: int | None = None,
    status: str = "active",
    summary: str = "",
    arc_id: int | None = None,
) -> dict[str, Any]:
    with canon.connect() as conn:
        if arc_id is not None:
            conn.execute(
                """
                UPDATE arcs SET title=?, start_chapter=?, target_end_chapter=?,
                  climax_chapter=?, status=?, summary=?
                WHERE id=?
                """,
                (
                    title,
                    start_chapter,
                    target_end_chapter,
                    climax_chapter,
                    status,
                    summary,
                    arc_id,
                ),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM arcs WHERE id=?", (arc_id,)).fetchone()
        else:
            cur = conn.execute(
                """
                INSERT INTO arcs(title, start_chapter, target_end_chapter, climax_chapter, status, summary)
                VALUES(?,?,?,?,?,?)
                """,
                (title, start_chapter, target_end_chapter, climax_chapter, status, summary),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM arcs WHERE id=?", (cur.lastrowid,)).fetchone()
        return dict(row)


def current_arc(canon: Canon, chapter: int) -> dict[str, Any] | None:
    arcs = [a for a in list_arcs(canon) if (a.get("status") or "active") != "resolved"]
    in_window: list[dict[str, Any]] = []
    overdue: list[dict[str, Any]] = []
    for arc in arcs:
        start = int(arc.get("start_chapter") or 1)
        end = arc.get("target_end_chapter")
        if chapter < start:
            continue
        if end is not None and chapter > int(end):
            overdue.append(arc)
            continue
        in_window.append(arc)
    pool = in_window or overdue
    if not pool:
        return None
    pool.sort(key=lambda a: (int(a.get("start_chapter") or 0), int(a.get("id") or 0)))
    return pool[-1]


def arc_stage(arc: dict[str, Any], chapter: int) -> dict[str, Any]:
    start = int(arc.get("start_chapter") or 1)
    end = arc.get("target_end_chapter")
    climax = arc.get("climax_chapter")
    to_climax = None if climax is None else int(climax) - chapter
    to_end = None if end is None else int(end) - chapter
    span = None
    if climax is not None:
        span = max(1, int(climax) - start)
        progress = max(0.0, min(1.0, (chapter - start) / span))
    elif end is not None:
        span = max(1, int(end) - start)
        progress = max(0.0, min(1.0, (chapter - start) / span))
    else:
        progress = 0.0

    if climax is not None and chapter == int(climax):
        stage = "climax"
    elif climax is not None and chapter > int(climax):
        stage = "falling"
    elif end is not None and chapter > int(end):
        stage = "overdue"
    elif progress < 0.33:
        stage = "setup"
    elif progress < 0.66:
        stage = "rising"
    else:
        stage = "approach-climax"

    return {
        "title": arc.get("title"),
        "status": arc.get("status"),
        "stage": stage,
        "chapter": chapter,
        "start_chapter": start,
        "target_end_chapter": end,
        "climax_chapter": climax,
        "chapters_to_climax": to_climax,
        "chapters_to_end": to_end,
        "progress": round(progress, 3),
        "summary": arc.get("summary") or "",
    }


def briefing_block(canon: Canon, chapter: int) -> str:
    arc = current_arc(canon, chapter)
    if not arc:
        return ""
    info = arc_stage(arc, chapter)
    lines = [
        "## Macro-arc",
        f"**{info['title']}** ({info['status']}) "
        f"ch.{info['start_chapter']}–{info['target_end_chapter'] or '?'}",
        f"Stage: **{info['stage']}** (this is chapter {chapter}).",
    ]
    if info["chapters_to_climax"] is not None:
        n = info["chapters_to_climax"]
        if n > 0:
            lines.append(
                f"{n} chapter(s) until climax (ch.{info['climax_chapter']}). "
                "Do not fire the arc climax yet."
            )
        elif n == 0:
            lines.append("This chapter is the planned climax. Pay off the arc's central promise.")
        else:
            lines.append(
                f"Climax was planned at ch.{info['climax_chapter']} ({abs(n)} chapter(s) ago). "
                "Falling action or overdue — do not reopen the same peak."
            )
    if info["summary"]:
        lines.append(info["summary"])
    lines.append("")
    return "\n".join(lines)
