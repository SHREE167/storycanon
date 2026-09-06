from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from storycanon.db import Canon
from storycanon.models import Delta, Flag, parse_delta, slugify
from storycanon.validate import blocking, validate_delta


@dataclass
class IngestResult:
    ok: bool
    chapter: int
    flags: list[Flag]
    applied: bool
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "chapter": self.chapter,
            "applied": self.applied,
            "message": self.message,
            "flags": [f.to_dict() for f in self.flags],
        }

    def render(self) -> str:
        lines = [
            f"{'OK' if self.ok else 'REJECTED'} — chapter {self.chapter}",
            self.message,
        ]
        if self.flags:
            lines.append("")
            lines.append("Flags:")
            for flag in self.flags:
                lines.append(f"- [{flag.severity}/{flag.type}] {flag.body}")
        return "\n".join(lines)


def _word_count(text: str) -> int:
    return len(text.split())


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def ingest_chapter(
    canon: Canon,
    delta: Delta | dict[str, Any],
    chapter_path: Path | None = None,
    *,
    strict: bool | None = None,
    force: bool = False,
    body: str | None = None,
) -> IngestResult:
    if not isinstance(delta, Delta):
        delta = parse_delta(delta)
    if strict is None:
        strict = bool(canon.cfg.get("strict_ingest", True))

    text = body or ""
    path_str = ""
    if chapter_path is not None:
        chapter_path = Path(chapter_path)
        if chapter_path.exists():
            text = chapter_path.read_text(encoding="utf-8")
            try:
                path_str = str(chapter_path.resolve().relative_to(canon.root.resolve()))
            except ValueError:
                path_str = str(chapter_path)

    with canon.connect() as conn:
        existing = conn.execute(
            "SELECT n FROM chapters WHERE n = ?", (delta.chapter,)
        ).fetchone()
        if existing and not force:
            return IngestResult(
                ok=False,
                chapter=delta.chapter,
                flags=[],
                applied=False,
                message=f"chapter {delta.chapter} already ingested (pass force=True to replace)",
            )

        flags = validate_delta(canon, conn, delta, strict=strict)
        blocked = blocking(flags, strict=strict)
        if blocked:
            for flag in flags:
                conn.execute(
                    "INSERT INTO flags(type, severity, chapter, body, status) VALUES(?,?,?,?,?)",
                    (flag.type, flag.severity, flag.chapter, flag.body, "open"),
                )
            conn.commit()
            canon.append_log(
                {
                    "event": "ingest_rejected",
                    "chapter": delta.chapter,
                    "flags": [f.to_dict() for f in flags],
                }
            )
            return IngestResult(
                ok=False,
                chapter=delta.chapter,
                flags=flags,
                applied=False,
                message="canon was not updated — fix the delta/prose and ingest again",
            )

        if existing and force:
            conn.execute("DELETE FROM chapters WHERE n = ?", (delta.chapter,))
            conn.execute("DELETE FROM mentions WHERE chapter = ?", (delta.chapter,))
            conn.execute("DELETE FROM beats WHERE chapter = ?", (delta.chapter,))

        due_default = int(canon.cfg.get("plant_due_after", 8))

        for spec in delta.new_entities:
            status = spec.status
            if spec.type == "character" and status == "active":
                status = "alive"
            if spec.type == "thread" and status in {"alive", "active"}:
                status = "active"
            existing = canon.get_by_slug(spec.slug, conn)
            if existing:
                aliases = list(existing.aliases)
                for alias in spec.aliases:
                    canon.add_alias(conn, existing.id, alias, aliases)
                attrs = dict(existing.attrs)
                attrs.update(spec.attrs)
                conn.execute(
                    """
                    UPDATE entities
                    SET name = ?, type = ?, status = ?, summary = ?,
                        attrs_json = ?, aliases_json = ?,
                        last_seen_chapter = ?, updated_at = datetime('now')
                    WHERE id = ?
                    """,
                    (
                        spec.name or existing.name,
                        spec.type or existing.type,
                        status or existing.status,
                        spec.summary or existing.summary,
                        json.dumps(attrs, ensure_ascii=False),
                        json.dumps(aliases, ensure_ascii=False),
                        delta.chapter,
                        existing.id,
                    ),
                )
            else:
                canon.insert_entity(
                    conn,
                    slug=spec.slug,
                    name=spec.name,
                    type=spec.type,
                    status=status,
                    aliases=list(spec.aliases),
                    attrs=dict(spec.attrs),
                    summary=spec.summary,
                    chapter=delta.chapter,
                )

        def require(slug: str):
            ent = canon.get_by_slug(slug, conn)
            if ent is None:
                raise RuntimeError(f"internal: missing `{slug}` after insert")
            return ent

        mentioned: set[int] = set()

        if delta.location:
            loc = require(delta.location)
            mentioned.add(loc.id)

        for slug in delta.present:
            ent = require(slug)
            mentioned.add(ent.id)
            if delta.location and ent.type == "character":
                _set_location(canon, conn, ent.id, delta.location, delta.chapter)

        for update in delta.updates:
            ent = require(update.slug)
            mentioned.add(ent.id)
            attrs = dict(ent.attrs)
            if update.set:
                attrs.update(update.set)
                if "location" in update.set and update.set["location"]:
                    _set_location(
                        canon,
                        conn,
                        ent.id,
                        slugify(str(update.set["location"])),
                        delta.chapter,
                    )
            aliases = list(ent.aliases)
            for alias in update.aliases:
                canon.add_alias(conn, ent.id, alias, aliases)
            status = update.status or ent.status
            summary = ent.summary if update.summary is None else update.summary
            conn.execute(
                """
                UPDATE entities
                SET attrs_json = ?, aliases_json = ?, status = ?, summary = ?,
                    last_seen_chapter = ?, updated_at = datetime('now')
                WHERE id = ?
                """,
                (
                    json.dumps(attrs, ensure_ascii=False),
                    json.dumps(aliases, ensure_ascii=False),
                    status,
                    summary,
                    delta.chapter,
                    ent.id,
                ),
            )

        for slug in delta.present:
            conn.execute(
                "UPDATE entities SET last_seen_chapter = ?, updated_at = datetime('now') WHERE slug = ?",
                (delta.chapter, slug),
            )

        for edge in delta.edges:
            src = require(edge.src)
            dst = require(edge.dst)
            mentioned.add(src.id)
            mentioned.add(dst.id)
            open_row = conn.execute(
                """
                SELECT id FROM edges
                WHERE src_id = ? AND dst_id = ? AND rel = ? AND to_chapter IS NULL
                """,
                (src.id, dst.id, edge.rel),
            ).fetchone()
            if open_row:
                conn.execute(
                    "UPDATE edges SET evidence_chapter = ?, note = ? WHERE id = ?",
                    (delta.chapter, edge.note, open_row["id"]),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO edges(src_id, dst_id, rel, from_chapter, to_chapter,
                                      evidence_chapter, note)
                    VALUES(?,?,?,?,NULL,?,?)
                    """,
                    (src.id, dst.id, edge.rel, delta.chapter, delta.chapter, edge.note),
                )

        for learned in delta.learned:
            character = require(learned.character)
            secret = require(learned.secret)
            mentioned.add(character.id)
            mentioned.add(secret.id)
            conn.execute(
                """
                INSERT OR IGNORE INTO knowledge(character_id, secret_id, known_since_chapter)
                VALUES(?,?,?)
                """,
                (character.id, secret.id, delta.chapter),
            )
            conn.execute(
                """
                INSERT INTO edges(src_id, dst_id, rel, from_chapter, to_chapter,
                                  evidence_chapter, note)
                SELECT ?, ?, 'knows', ?, NULL, ?, ''
                WHERE NOT EXISTS (
                    SELECT 1 FROM edges
                    WHERE src_id = ? AND dst_id = ? AND rel = 'knows' AND to_chapter IS NULL
                )
                """,
                (
                    character.id,
                    secret.id,
                    delta.chapter,
                    delta.chapter,
                    character.id,
                    secret.id,
                ),
            )

        for beat in delta.threads:
            ent = require(beat.slug)
            mentioned.add(ent.id)
            fields = ["last_seen_chapter = ?", "updated_at = datetime('now')"]
            values: list[Any] = [delta.chapter]
            if beat.status:
                fields.append("status = ?")
                values.append(beat.status)
            if beat.beat:
                fields.append("summary = ?")
                values.append(beat.beat)
            values.append(ent.id)
            conn.execute(
                f"UPDATE entities SET {', '.join(fields)} WHERE id = ?",
                values,
            )

        for plant in delta.plants:
            conn.execute(
                """
                INSERT INTO plants(slug, kind, planted_chapter, due_after, note)
                VALUES(?,?,?,?,?)
                ON CONFLICT(slug) DO UPDATE SET
                    kind = excluded.kind,
                    note = excluded.note
                """,
                (
                    plant.slug,
                    plant.kind,
                    delta.chapter,
                    plant.due_after if plant.due_after is not None else due_default,
                    plant.note,
                ),
            )

        for payoff in delta.payoffs:
            conn.execute(
                "UPDATE plants SET paid_chapter = ? WHERE slug = ? AND paid_chapter IS NULL",
                (delta.chapter, payoff),
            )

        if delta.time_advance:
            conn.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES('time', ?)",
                (delta.time_advance,),
            )
            prev = conn.execute(
                "SELECT value FROM meta WHERE key = 'time_log'"
            ).fetchone()
            log = json.loads(prev["value"]) if prev else []
            log.append({"chapter": delta.chapter, "advance": delta.time_advance})
            conn.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES('time_log', ?)",
                (json.dumps(log, ensure_ascii=False),),
            )

        if delta.pov:
            mentioned.add(require(delta.pov).id)

        for eid in mentioned:
            conn.execute(
                "INSERT OR IGNORE INTO mentions(chapter, entity_id) VALUES(?,?)",
                (delta.chapter, eid),
            )

        for flag in flags:
            conn.execute(
                "INSERT INTO flags(type, severity, chapter, body, status) VALUES(?,?,?,?,?)",
                (flag.type, flag.severity, flag.chapter, flag.body, "open"),
            )

        _record_beats(conn, delta)

        conn.execute(
            """
            INSERT INTO chapters(n, path, title, pov, location, present_json, summary,
                                 word_count, content_hash)
            VALUES(?,?,?,?,?,?,?,?,?)
            """,
            (
                delta.chapter,
                path_str,
                delta.title,
                delta.pov,
                delta.location,
                json.dumps(delta.present),
                delta.summary,
                _word_count(text),
                _hash_text(text) if text else "",
            ),
        )
        conn.commit()

    payload = asdict(delta) if hasattr(delta, "__dataclass_fields__") else delta
    canon.append_log(
        {
            "event": "ingest",
            "chapter": delta.chapter,
            "path": path_str,
            "delta": payload,
            "flags": [f.to_dict() for f in flags],
        }
    )
    extra = f" ({len(flags)} non-blocking flags)" if flags else ""
    return IngestResult(
        ok=True,
        chapter=delta.chapter,
        flags=flags,
        applied=True,
        message=f"chapter {delta.chapter} is now canon{extra}",
    )


def _record_beats(conn, delta: Delta) -> None:
    conn.execute("DELETE FROM beats WHERE chapter = ?", (delta.chapter,))
    sort = 0

    def add(kind: str, text: str, slug: str | None = None) -> None:
        nonlocal sort
        if not text:
            return
        conn.execute(
            "INSERT INTO beats(chapter, kind, entity_slug, text, sort) VALUES(?,?,?,?,?)",
            (delta.chapter, kind, slug, text, sort),
        )
        sort += 1

    if delta.summary:
        add("scene", delta.summary, delta.pov)
    if delta.location:
        add("arrival", f"at {delta.location}", delta.location)
    for beat in delta.threads:
        add("thread", beat.beat or beat.status or beat.slug, beat.slug)
    for plant in delta.plants:
        add("plant", plant.note or f"planted {plant.slug}", plant.slug)
    for payoff in delta.payoffs:
        add("payoff", f"paid off {payoff}", payoff)
    for learned in delta.learned:
        add("reveal", f"{learned.character} learns {learned.secret}", learned.secret)
    for update in delta.updates:
        if update.status in {"dead", "destroyed"}:
            add("death", f"{update.slug} is {update.status}", update.slug)
        if update.set.get("injury"):
            add("injury", f"{update.slug}: {update.set['injury']}", update.slug)
    for edge in delta.edges:
        if edge.rel in {"allied_with", "loves", "hates", "member_of"}:
            add("relation", f"{edge.src} {edge.rel.replace('_', ' ')} {edge.dst}", edge.src)


def _set_location(
    canon: Canon, conn, character_id: int, location_slug: str, chapter: int
) -> None:
    loc = canon.get_by_slug(location_slug, conn)
    if loc is None:
        return
    conn.execute(
        """
        UPDATE edges SET to_chapter = ?
        WHERE src_id = ? AND rel = 'at' AND to_chapter IS NULL
        """,
        (chapter, character_id),
    )
    conn.execute(
        """
        INSERT INTO edges(src_id, dst_id, rel, from_chapter, to_chapter, evidence_chapter, note)
        VALUES(?,?,?,?,NULL,?,?)
        """,
        (character_id, loc.id, "at", chapter, chapter, ""),
    )
    row = conn.execute(
        "SELECT attrs_json FROM entities WHERE id = ?", (character_id,)
    ).fetchone()
    attrs = json.loads(row["attrs_json"] or "{}")
    attrs["location"] = loc.slug
    conn.execute(
        "UPDATE entities SET attrs_json = ?, updated_at = datetime('now') WHERE id = ?",
        (json.dumps(attrs, ensure_ascii=False), character_id),
    )
