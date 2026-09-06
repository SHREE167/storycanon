from __future__ import annotations

import json
import re
from collections import defaultdict, deque

from storycanon.db import Canon
from storycanon.models import slugify


def get_entity_text(canon: Canon, name: str) -> str:
    matches = canon.resolve_all(name)
    if not matches:
        ent = canon.resolve(name)
        matches = [ent] if ent else []
    if not matches:
        return f"No entity matches `{name}`."
    if len(matches) > 1:
        names = ", ".join(f"{e.name} (`{e.slug}`)" for e in matches)
        return f"Ambiguous: {names}"
    ent = matches[0]
    lines = ent.sheet_lines()
    with canon.connect() as conn:
        edges = conn.execute(
            """
            SELECT e.rel, s.slug AS src, s.name AS src_name,
                   d.slug AS dst, d.name AS dst_name, e.evidence_chapter
            FROM edges e
            JOIN entities s ON s.id = e.src_id
            JOIN entities d ON d.id = e.dst_id
            WHERE (e.src_id = ? OR e.dst_id = ?) AND e.to_chapter IS NULL
            ORDER BY e.rel, e.evidence_chapter
            """,
            (ent.id, ent.id),
        ).fetchall()
        if ent.type == "character":
            secrets = conn.execute(
                """
                SELECT s.name, k.known_since_chapter
                FROM knowledge k JOIN entities s ON s.id = k.secret_id
                WHERE k.character_id = ?
                """,
                (ent.id,),
            ).fetchall()
            if secrets:
                lines.append("knows:")
                for row in secrets:
                    lines.append(f"- {row['name']} (ch.{row['known_since_chapter']})")
        if ent.type == "secret":
            knowers = conn.execute(
                """
                SELECT c.name, k.known_since_chapter
                FROM knowledge k JOIN entities c ON c.id = k.character_id
                WHERE k.secret_id = ?
                """,
                (ent.id,),
            ).fetchall()
            if knowers:
                lines.append("known by:")
                for row in knowers:
                    lines.append(f"- {row['name']} (ch.{row['known_since_chapter']})")
    if edges:
        lines.append("open edges:")
        for edge in edges[:40]:
            lines.append(
                f"- {edge['src_name']} --{edge['rel']}--> {edge['dst_name']} "
                f"(ch.{edge['evidence_chapter']})"
            )
    return "\n".join(lines)


def shortest_path(canon: Canon, a: str, b: str) -> str:
    src = canon.resolve(a)
    dst = canon.resolve(b)
    if src is None:
        return f"No entity matches `{a}`."
    if dst is None:
        return f"No entity matches `{b}`."
    if src.id == dst.id:
        return f"{src.name} is {dst.name}."

    entities, edges = canon.iter_open_graph()
    adj: dict[int, list[tuple[int, str, int]]] = defaultdict(list)
    for sid, rel, did, ev in edges:
        adj[sid].append((did, rel, ev))
        adj[did].append((sid, rel, ev))

    prev: dict[int, tuple[int, str, int]] = {}
    q = deque([src.id])
    seen = {src.id}
    found = False
    while q:
        cur = q.popleft()
        if cur == dst.id:
            found = True
            break
        for nxt, rel, ev in adj[cur]:
            if nxt not in seen:
                seen.add(nxt)
                prev[nxt] = (cur, rel, ev)
                q.append(nxt)
    if not found:
        return f"No open-canon path between {src.name} and {dst.name}."

    hops: list[str] = []
    node = dst.id
    while node != src.id:
        parent, rel, ev = prev[node]
        hops.append(
            f"{entities[parent].name} --{rel}--> {entities[node].name} (ch.{ev})"
        )
        node = parent
    hops.reverse()
    return f"Path ({len(hops)} hops):\n" + "\n".join(hops)


def status_text(canon: Canon) -> str:
    last = canon.last_chapter_n()
    stale_after = int(canon.cfg.get("stale_after") or 20)
    lines = [
        f"# Status — {canon.meta('title') or canon.cfg.get('title')}",
        f"Chapters ingested: {last}",
        "",
        "## Open threads",
    ]
    threads = [e for e in canon.list_entities("thread") if e.status == "active"]
    if threads:
        for t in threads:
            lines.append(f"- **{t.name}** (`{t.slug}`) last seen ch.{t.last_seen_chapter}: {t.summary}")
    else:
        lines.append("- none")

    with canon.connect() as conn:
        due = conn.execute(
            """
            SELECT * FROM plants
            WHERE paid_chapter IS NULL AND planted_chapter + due_after <= ?
            """,
            (last + 1,),
        ).fetchall()
        flags = conn.execute(
            "SELECT * FROM flags WHERE status = 'open' ORDER BY id DESC LIMIT 20"
        ).fetchall()
        stale = conn.execute(
            """
            SELECT * FROM entities
            WHERE type = 'character' AND status IN ('alive','active')
              AND last_seen_chapter IS NOT NULL
              AND ? - last_seen_chapter >= ?
            ORDER BY last_seen_chapter
            """,
            (last, stale_after),
        ).fetchall()

    lines += ["", "## Due plants"]
    if due:
        for p in due:
            lines.append(
                f"- `{p['slug']}` planted ch.{p['planted_chapter']} "
                f"(due since ch.{p['planted_chapter'] + p['due_after']})"
            )
    else:
        lines.append("- none")

    lines += ["", "## Open flags"]
    if flags:
        for f in flags:
            lines.append(f"- [{f['severity']}/{f['type']}] ch.{f['chapter']}: {f['body']}")
    else:
        lines.append("- none")

    lines += ["", "## Stale living characters"]
    if stale:
        for r in stale:
            lines.append(f"- {r['name']} last seen ch.{r['last_seen_chapter']}")
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def beats_text(canon: Canon, chapter: int | None = None, limit: int = 80) -> str:
    last = canon.last_chapter_n()
    with canon.connect() as conn:
        if chapter is not None:
            rows = conn.execute(
                "SELECT * FROM beats WHERE chapter = ? ORDER BY sort",
                (chapter,),
            ).fetchall()
            heading = f"# Beats — chapter {chapter}"
        else:
            rows = conn.execute(
                "SELECT * FROM beats ORDER BY chapter, sort LIMIT ?",
                (limit,),
            ).fetchall()
            heading = f"# Beats — {canon.meta('title') or 'canon'} ({last} chapters)"
    if not rows:
        return heading + "\n\nNo beats recorded yet. Ingest a chapter.\n"
    lines = [heading, ""]
    current = None
    for row in rows:
        if row["chapter"] != current:
            current = row["chapter"]
            lines.append(f"## ch.{current}")
        slug = f" `{row['entity_slug']}`" if row["entity_slug"] else ""
        lines.append(f"- [{row['kind']}] {row['text']}{slug}")
    return "\n".join(lines) + "\n"


def query_canon(canon: Canon, question: str) -> str:
    q = question.strip()
    lower = q.lower()

    m = re.search(r"where is (.+?)\??$", lower)
    if m:
        return get_entity_text(canon, m.group(1).strip())

    m = re.search(r"who knows (.+?)\??$", lower)
    if m:
        ent = canon.resolve(m.group(1).strip())
        if not ent:
            return f"No entity matches `{m.group(1).strip()}`."
        with canon.connect() as conn:
            rows = conn.execute(
                """
                SELECT c.name, k.known_since_chapter
                FROM knowledge k JOIN entities c ON c.id = k.character_id
                WHERE k.secret_id = ?
                """,
                (ent.id,),
            ).fetchall()
        if not rows:
            return f"Nobody tracked knows `{ent.name}`."
        return f"Who knows {ent.name}:\n" + "\n".join(
            f"- {r['name']} (ch.{r['known_since_chapter']})" for r in rows
        )

    if "open thread" in lower or "active thread" in lower:
        threads = [e for e in canon.list_entities("thread") if e.status == "active"]
        if not threads:
            return "No active threads."
        return "Active threads:\n" + "\n".join(
            f"- {t.name}: {t.summary}" for t in threads
        )

    if lower in {"status", "state", "where are we"}:
        return status_text(canon)

    if "beat" in lower:
        m = re.search(r"ch(?:apter)?\s*(\d+)", lower)
        return beats_text(canon, int(m.group(1)) if m else None)

    # Keyword hunt over names + summaries
    tokens = [t for t in re.findall(r"[a-z0-9]+", lower) if len(t) > 2]
    stop = {"the", "and", "what", "who", "how", "does", "about", "with"}
    tokens = [t for t in tokens if t not in stop]
    if not tokens:
        return status_text(canon)

    hits: list[str] = []
    for ent in canon.list_entities():
        blob = " ".join(
            [
                ent.slug,
                ent.name.lower(),
                " ".join(a.lower() for a in ent.aliases),
                ent.summary.lower(),
                json.dumps(ent.attrs).lower(),
            ]
        )
        if all(t in blob for t in tokens) or any(t in ent.slug or t in ent.name.lower() for t in tokens):
            hits.append(f"- {ent.name} (`{ent.slug}`, {ent.type}): {ent.summary}")
    if not hits:
        return f"Nothing in canon matched `{question}`. Try a name, or `status`."
    return f"Matches for `{question}`:\n" + "\n".join(hits[:20])
