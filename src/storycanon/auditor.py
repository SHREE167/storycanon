from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from storycanon.db import Canon
from storycanon.models import Delta, Flag, parse_delta, slugify
from storycanon.progression import check_progression, load_plugins
from storycanon.validate import blocking, validate_delta

AUDITOR_INSTRUCTIONS = """You are the StoryCanon AUDITOR, not the novelist.
The drafter already wrote the chapter. You do not write prose. You do not invent facts.

Extract every canon change the TEXT actually states into one delta JSON object:
- character location / presence / injury / death / appearance
- item movement (who holds it, where it is)
- relationship shifts (allied_with, loves, hates, member_of, owns)
- secrets revealed (learned) and who now knows them
- thread beats, plants, payoffs
- power-system rank changes (attrs such as stage) and breakthrough events
- new named entities that did not exist in the glossary

Rules:
- Use glossary slugs. Never invent a second spelling of someone in the glossary.
- If the prose is silent, omit the field. Do not copy old canon into updates.
- If a rank jumps more than one step, add events: [{kind: "breakthrough", slug: "<character>"}] only if the prose describes a breakthrough. Otherwise leave the jump so ingest can reject it.
- Output ONLY valid JSON matching the delta schema. No markdown fences.
"""


def _glossary(canon: Canon, limit: int = 80) -> list[dict[str, Any]]:
    rows = []
    for ent in canon.list_entities():
        rows.append(
            {
                "slug": ent.slug,
                "name": ent.name,
                "type": ent.type,
                "status": ent.status,
                "aliases": ent.aliases,
                "location": ent.location(),
                "attrs": {
                    k: v
                    for k, v in ent.attrs.items()
                    if k in {"stage", "injury", "location", "realm", "rank", "level"}
                    or v not in (None, "", [], {})
                },
            }
        )
        if len(rows) >= limit:
            break
    return rows


def auditor_prompt(canon: Canon, chapter: int, prose: str) -> str:
    plugins = load_plugins(canon)
    plugin_note = ""
    if plugins:
        bits = []
        for p in plugins:
            ranks = p.get("ranks")
            bits.append(
                f"- {p.get('label') or p.get('id')}: attr `{p.get('attr')}` ranks {ranks}; "
                f"skip requires events.kind=`{p.get('skip_event', 'breakthrough')}`"
            )
        plugin_note = "Power systems in force:\n" + "\n".join(bits) + "\n\n"
    glossary = json.dumps(_glossary(canon), ensure_ascii=False, indent=2)
    from storycanon.models import DELTA_JSON_SCHEMA

    schema = json.dumps(DELTA_JSON_SCHEMA, ensure_ascii=False)
    return (
        f"{AUDITOR_INSTRUCTIONS}\n"
        f"Chapter number: {chapter}\n\n"
        f"{plugin_note}"
        f"## Glossary (canon slugs — reuse these)\n{glossary}\n\n"
        f"## Delta JSON schema\n{schema}\n\n"
        f"## Chapter prose\n{prose.strip()}\n"
    )


@dataclass
class AuditResult:
    ok: bool
    chapter: int
    flags: list[Flag]
    diff: list[str]
    message: str

    def render(self) -> str:
        lines = [
            f"{'OK' if self.ok else 'REJECT'} — auditor diff for chapter {self.chapter}",
            self.message,
            "",
            "## Diff vs canon",
        ]
        if self.diff:
            lines.extend(f"- {line}" for line in self.diff)
        else:
            lines.append("- (no tracked field changes)")
        if self.flags:
            lines += ["", "## Flags"]
            for flag in self.flags:
                lines.append(f"- [{flag.severity}/{flag.type}] {flag.body}")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "chapter": self.chapter,
            "message": self.message,
            "diff": self.diff,
            "flags": [f.to_dict() for f in self.flags],
        }


def diff_against_canon(canon: Canon, delta: Delta) -> list[str]:
    lines: list[str] = []
    incoming = {e.slug: e for e in delta.new_entities}
    for spec in delta.new_entities:
        lines.append(f"NEW {spec.type} `{spec.slug}` ({spec.name})")
    if delta.location:
        lines.append(f"scene location → `{delta.location}`")
    for update in delta.updates:
        ent = incoming.get(update.slug) or canon.get_by_slug(update.slug)
        old_attrs = dict(ent.attrs) if ent and hasattr(ent, "attrs") else {}
        if update.status:
            old_status = getattr(ent, "status", None)
            if old_status != update.status:
                lines.append(f"{update.slug}.status: {old_status} → {update.status}")
        for key, new in update.set.items():
            old = old_attrs.get(key)
            if old != new:
                lines.append(f"{update.slug}.{key}: {old} → {new}")
    for edge in delta.edges:
        lines.append(f"edge {edge.src} --{edge.rel}--> {edge.dst}")
    for learned in delta.learned:
        lines.append(f"secret `{learned.secret}` learned by `{learned.character}`")
    for beat in delta.threads:
        lines.append(f"thread `{beat.slug}`: {beat.beat or beat.status}")
    for plant in delta.plants:
        lines.append(f"plant `{plant.slug}`")
    for payoff in delta.payoffs:
        lines.append(f"payoff `{payoff}`")
    for event in delta.events:
        lines.append(f"event {event.kind}" + (f" `{event.slug}`" if event.slug else ""))
    return lines


def audit_delta(canon: Canon, delta: Delta | dict[str, Any], *, strict: bool | None = None) -> AuditResult:
    if not isinstance(delta, Delta):
        delta = parse_delta(delta)
    if strict is None:
        strict = bool(canon.cfg.get("strict_ingest", True))
    with canon.connect() as conn:
        flags = validate_delta(canon, conn, delta, strict=strict)
    flags.extend(check_progression(canon, delta))
    diff = diff_against_canon(canon, delta)
    blocked = blocking(flags, strict=strict)
    ok = not blocked
    message = (
        "Auditor extraction is legal against canon. Safe to ingest."
        if ok
        else "Auditor extraction is NOT legal. Fix the prose or the delta before ingest."
    )
    return AuditResult(
        ok=ok,
        chapter=delta.chapter,
        flags=flags,
        diff=diff,
        message=message,
    )


def load_prose(canon: Canon, chapter: int, chapter_path: Path | None = None) -> str:
    if chapter_path and Path(chapter_path).exists():
        return Path(chapter_path).read_text(encoding="utf-8")
    n = f"{chapter:04d}"
    for path in sorted(canon.chapters_dir.glob("*.md")):
        if path.name.startswith(n) or path.stem == str(chapter) or path.stem.endswith(f"-{chapter}"):
            return path.read_text(encoding="utf-8")
    row = canon.get_chapter(chapter)
    if row and row.get("path"):
        p = canon.root / row["path"]
        if p.exists():
            return p.read_text(encoding="utf-8")
    raise FileNotFoundError(f"No chapter prose found for {chapter} under {canon.chapters_dir}")
