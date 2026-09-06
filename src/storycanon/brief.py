from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from storycanon.db import Canon
from storycanon.models import Entity, slugify


@dataclass
class ScoredEntity:
    entity: Entity
    score: int
    reasons: list[str] = field(default_factory=list)


def _approx_tokens(text: str) -> int:
    return max(1, len(text) // 3)


def _cut_to_budget(text: str, token_budget: int) -> tuple[str, bool]:
    char_budget = token_budget * 3
    if len(text) <= char_budget:
        return text, False
    cut = text[:char_budget].rfind("\n")
    if cut < 200:
        cut = char_budget
    kept = text[:cut].rstrip()
    notice = (
        f"\n\n[!] TRUNCATED: briefing hit the ~{token_budget}-token budget. "
        "Query specific entities with get_entity / query_canon instead of raising the budget."
    )
    return kept + notice, True


def assemble_brief(
    canon: Canon,
    chapter: int,
    *,
    pov: str | None = None,
    present: list[str] | None = None,
    location: str | None = None,
    token_budget: int | None = None,
) -> dict[str, Any]:
    budget = int(token_budget or canon.cfg.get("token_budget") or 4000)
    recent_window = int(canon.cfg.get("recent_window") or 5)
    last_n = canon.last_chapter_n()
    last = canon.get_chapter(last_n) if last_n else None

    pov_slug = slugify(pov) if pov else None
    if not pov_slug:
        pov_slug = (last or {}).get("pov") or canon.cfg.get("default_pov") or None
        if pov_slug:
            pov_slug = slugify(str(pov_slug))

    present_slugs = [slugify(s) for s in (present or []) if s]
    if not present_slugs and last:
        present_slugs = json.loads(last.get("present_json") or "[]")

    loc_slug = slugify(location) if location else None
    if not loc_slug and last:
        loc_slug = last.get("location")

    with canon.connect() as conn:
        entities = {
            r["slug"]: canon._row_to_entity(r)
            for r in conn.execute("SELECT * FROM entities")
        }
        open_flags = [
            dict(r)
            for r in conn.execute(
                "SELECT type, severity, chapter, body FROM flags WHERE status = 'open' "
                "ORDER BY id DESC LIMIT 20"
            )
        ]
        plants = [dict(r) for r in conn.execute("SELECT * FROM plants")]
        knowledge_rows = conn.execute(
            """
            SELECT c.slug AS who, s.slug AS secret, s.name AS secret_name,
                   k.known_since_chapter
            FROM knowledge k
            JOIN entities c ON c.id = k.character_id
            JOIN entities s ON s.id = k.secret_id
            """
        ).fetchall()
        edge_rows = conn.execute(
            """
            SELECT e.rel, s.slug AS src, d.slug AS dst, e.evidence_chapter
            FROM edges e
            JOIN entities s ON s.id = e.src_id
            JOIN entities d ON d.id = e.dst_id
            WHERE e.to_chapter IS NULL
            """
        ).fetchall()

    due_plants = []
    for plant in plants:
        if plant["paid_chapter"] is not None:
            continue
        if plant["planted_chapter"] + plant["due_after"] <= chapter:
            due_plants.append(plant)

    pov_ent = entities.get(pov_slug) if pov_slug else None
    loc_ent = entities.get(loc_slug) if loc_slug else None

    scored: list[ScoredEntity] = []
    for ent in entities.values():
        score = 0
        reasons: list[str] = []
        if ent.slug in present_slugs:
            score += 100
            reasons.append("on-stage")
        if pov_ent and ent.slug == pov_ent.slug:
            score += 120
            reasons.append("pov")
        if loc_ent and ent.slug == loc_ent.slug:
            score += 90
            reasons.append("scene-location")
        if (
            ent.last_seen_chapter is not None
            and chapter - ent.last_seen_chapter <= recent_window
        ):
            score += 40
            reasons.append("recent")
        if ent.type == "thread" and ent.status == "active":
            score += 50
            reasons.append("active-thread")
        if ent.type == "rule":
            score += 15
            reasons.append("world-rule")
        if any(p["slug"] == ent.slug for p in due_plants):
            score += 80
            reasons.append("due-plant")
        if pov_ent:
            for edge in edge_rows:
                if edge["src"] == pov_ent.slug and edge["dst"] == ent.slug:
                    score += 25
                    reasons.append(f"linked:{edge['rel']}")
                    break
                if edge["dst"] == pov_ent.slug and edge["src"] == ent.slug:
                    score += 20
                    reasons.append(f"linked:{edge['rel']}")
                    break
        if score > 0:
            scored.append(ScoredEntity(ent, score, reasons))

    scored.sort(key=lambda s: (-s.score, s.entity.type, s.entity.name))

    pov_secrets = [
        r
        for r in knowledge_rows
        if pov_slug and r["who"] == pov_slug
    ]

    locked: list[str] = []
    for ent in entities.values():
        if ent.type == "character" and ent.status in {"dead", "destroyed"}:
            locked.append(f"{ent.name} is {ent.status}")
        if ent.slug in present_slugs and ent.location():
            locked.append(f"{ent.name} is at {ent.location()}")
        if ent.type == "character" and ent.attrs.get("injury"):
            locked.append(f"{ent.name} is injured: {ent.attrs['injury']}")
        if ent.type == "character" and ent.location() and ent.slug not in present_slugs:
            if ent.last_seen_chapter is not None and chapter - ent.last_seen_chapter <= recent_window + 10:
                locked.append(f"{ent.name} was last at {ent.location()} (ch.{ent.last_seen_chapter})")
    if pov_ent:
        known = [r["secret_name"] for r in pov_secrets]
        if known:
            locked.append(f"{pov_ent.name} knows: " + ", ".join(known))
        else:
            locked.append(f"{pov_ent.name} currently knows no tracked secrets")

    recent = canon.recent_chapters(2)
    premise = canon.meta("premise") or str(canon.cfg.get("premise") or "")
    title = canon.meta("title") or str(canon.cfg.get("title") or "Untitled")

    md_parts: list[str] = [
        f"# Briefing — {title} chapter {chapter}",
        "",
        f"Last ingested chapter: {last_n or 0}. Do not reread the manuscript. Write only this chapter.",
        "",
        "## Premise",
        premise[:800] or "(none)",
        "",
    ]

    if pov_ent:
        md_parts += ["## POV", *pov_ent.sheet_lines(), ""]
        if pov_secrets:
            md_parts.append("knows:")
            for row in pov_secrets:
                md_parts.append(
                    f"- {row['secret_name']} (since ch.{row['known_since_chapter']})"
                )
            md_parts.append("")

    if loc_ent:
        md_parts += ["## Location", *loc_ent.sheet_lines(), ""]

    on_stage = [s for s in scored if s.entity.slug in present_slugs and s.entity.type == "character"]
    if on_stage:
        md_parts.append("## On stage")
        for item in on_stage:
            md_parts.extend(item.entity.sheet_lines())
            md_parts.append("")

    threads = [s for s in scored if s.entity.type == "thread" and s.entity.status == "active"]
    if threads:
        md_parts.append("## Active threads")
        for item in threads:
            md_parts.append(f"- **{item.entity.name}**: {item.entity.summary or '(no beat yet)'}")
        md_parts.append("")

    recent_beats = []
    with canon.connect() as conn:
        recent_beats = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM beats WHERE chapter >= ? ORDER BY chapter, sort",
                (max(1, (last_n or 1) - 2),),
            ).fetchall()
        ]
    if recent_beats:
        md_parts.append("## Recent beats")
        current = None
        for beat in recent_beats[-18:]:
            if beat["chapter"] != current:
                current = beat["chapter"]
                md_parts.append(f"### ch.{current}")
            md_parts.append(f"- [{beat['kind']}] {beat['text']}")
        md_parts.append("")

    if due_plants:
        md_parts.append("## Due plants (pay these off or keep them live on purpose)")
        for plant in due_plants:
            md_parts.append(
                f"- `{plant['slug']}` planted ch.{plant['planted_chapter']}, "
                f"due since ch.{plant['planted_chapter'] + plant['due_after']}"
                + (f" — {plant['note']}" if plant["note"] else "")
            )
        md_parts.append("")

    rules = [s for s in scored if s.entity.type == "rule"]
    if rules:
        md_parts.append("## World rules that apply")
        for item in rules[:8]:
            md_parts.append(f"- **{item.entity.name}**: {item.entity.summary or item.entity.attrs}")
        md_parts.append("")

    if recent:
        md_parts.append("## Last chapter summaries (not full text)")
        for ch in recent:
            md_parts.append(f"### ch.{ch['n']} — {ch.get('title') or ''}".rstrip(" —"))
            md_parts.append(ch.get("summary") or "(no summary)")
            md_parts.append("")

    if locked:
        md_parts.append("## Locked facts — do not contradict")
        for fact in locked[:40]:
            md_parts.append(f"- {fact}")
        md_parts.append("")

    if open_flags:
        md_parts.append("## Open continuity flags")
        for flag in open_flags[:15]:
            md_parts.append(
                f"- [{flag['severity']}/{flag['type']}] ch.{flag['chapter']}: {flag['body']}"
            )
        md_parts.append("")

    others = [
        s
        for s in scored
        if s.entity.type not in {"thread", "rule"}
        and s.entity.slug not in present_slugs
        and (not pov_ent or s.entity.slug != pov_ent.slug)
        and (not loc_ent or s.entity.slug != loc_ent.slug)
        and s.score >= 40
    ]
    if others:
        md_parts.append("## Nearby / recent (do not invent new spellings)")
        for item in others[:12]:
            extra = []
            if item.entity.location():
                extra.append(f"at {item.entity.location()}")
            if item.entity.attrs.get("injury"):
                extra.append(f"injury: {item.entity.attrs['injury']}")
            suffix = ("; " + "; ".join(extra)) if extra else ""
            md_parts.append(
                f"- {item.entity.name} (`{item.entity.slug}`, {item.entity.type}) "
                f"[{', '.join(item.reasons)}] {item.entity.summary}{suffix}".strip()
            )
        md_parts.append("")

    md_parts += [
        "## After you write",
        "1. Save markdown under `chapters/`.",
        "2. Call ingest_chapter with a structured delta (present, location, updates, threads, plants, learned).",
        "3. If ingest rejects, fix the prose or the delta. Do not treat the chapter as canon until ingest returns ok.",
        "",
    ]

    markdown, truncated = _cut_to_budget("\n".join(md_parts).strip() + "\n", budget)
    payload = {
        "chapter": chapter,
        "title": title,
        "pov": pov_slug,
        "location": loc_slug,
        "present": present_slugs,
        "token_budget": budget,
        "approx_tokens": _approx_tokens(markdown),
        "truncated": truncated,
        "due_plants": [p["slug"] for p in due_plants],
        "open_flag_count": len(open_flags),
        "markdown": markdown,
    }
    return payload
