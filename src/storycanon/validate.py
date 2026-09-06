from __future__ import annotations

import sqlite3

from storycanon.db import Canon
from storycanon.models import DEAD_STATUSES, Delta, Flag, slugify


def validate_delta(
    canon: Canon, conn: sqlite3.Connection, delta: Delta, *, strict: bool
) -> list[Flag]:
    flags: list[Flag] = []
    chapter = delta.chapter
    incoming = {slugify(e.slug): e for e in delta.new_entities}

    def exists(slug: str) -> bool:
        slug = slugify(slug)
        if slug in incoming:
            return True
        return canon.get_by_slug(slug, conn) is not None

    def entity(slug: str):
        slug = slugify(slug)
        if slug in incoming:
            return None
        return canon.get_by_slug(slug, conn)

    for spec in delta.new_entities:
        same = canon.get_by_slug(spec.slug, conn)
        if same is None:
            collisions = [c for c in canon.resolve_all(spec.slug, conn) if c.slug != spec.slug]
            if collisions:
                flags.append(
                    Flag(
                        type="alias_collision",
                        severity="major",
                        chapter=chapter,
                        body=f"new entity `{spec.slug}` collides with existing `{collisions[0].slug}`",
                    )
                )
        for alias in spec.aliases + [spec.name]:
            hits = [h for h in canon.resolve_all(alias, conn) if h.slug != spec.slug]
            if hits:
                flags.append(
                    Flag(
                        type="alias_collision",
                        severity="major",
                        chapter=chapter,
                        body=f"alias `{alias}` for `{spec.slug}` already maps to `{hits[0].slug}`",
                    )
                )

    existing_plants = {r["slug"] for r in conn.execute("SELECT slug FROM plants")}
    plant_slugs = {p.slug for p in delta.plants} | existing_plants | set(delta.payoffs)
    for slug in sorted(delta.all_referenced_slugs()):
        if slug in incoming:
            continue
        if slug in plant_slugs:
            continue
        if not exists(slug):
            flags.append(
                Flag(
                    type="unknown_entity",
                    severity="major" if strict else "minor",
                    chapter=chapter,
                    body=f"unknown slug `{slug}` — add it under new_entities or fix the spelling",
                )
            )

    for slug in delta.present:
        ent = entity(slug)
        if ent and ent.status in DEAD_STATUSES:
            flags.append(
                Flag(
                    type="contradiction",
                    severity="critical",
                    chapter=chapter,
                    body=f"`{ent.name}` is {ent.status} but appears in present for ch.{chapter}",
                )
            )

    if delta.location and delta.present:
        for slug in delta.present:
            update = next((u for u in delta.updates if u.slug == slug), None)
            new_loc = None
            if update and update.set.get("location"):
                new_loc = slugify(str(update.set["location"]))
            if new_loc and new_loc != delta.location:
                flags.append(
                    Flag(
                        type="contradiction",
                        severity="major",
                        chapter=chapter,
                        body=(
                            f"`{slug}` is present at `{delta.location}` but update sets "
                            f"location `{new_loc}`"
                        ),
                    )
                )

    for learned in delta.learned:
        secret = entity(learned.secret)
        if secret and secret.type not in {"secret", "item", "rule", "event"}:
            flags.append(
                Flag(
                    type="contradiction",
                    severity="minor",
                    chapter=chapter,
                    body=f"`{learned.secret}` is type `{secret.type}`, not a secret",
                )
            )
        character = entity(learned.character)
        if character:
            row = conn.execute(
                "SELECT 1 FROM knowledge WHERE character_id = ? AND secret_id = ?",
                (character.id, secret.id if secret else -1),
            ).fetchone()
            if secret and row:
                flags.append(
                    Flag(
                        type="stale_arc",
                        severity="minor",
                        chapter=chapter,
                        body=f"`{character.name}` already knows `{secret.name}`",
                    )
                )

    if delta.pov:
        pov = entity(delta.pov)
        for secret_slug in delta.referenced_secrets:
            secret = entity(secret_slug)
            if not pov or not secret:
                continue
            known = conn.execute(
                "SELECT 1 FROM knowledge WHERE character_id = ? AND secret_id = ?",
                (pov.id, secret.id),
            ).fetchone()
            just_learned = any(
                l.character == delta.pov and l.secret == secret_slug for l in delta.learned
            )
            if not known and not just_learned:
                flags.append(
                    Flag(
                        type="contradiction",
                        severity="critical",
                        chapter=chapter,
                        body=(
                            f"POV `{pov.name}` references secret `{secret.name}` "
                            f"but does not know it yet"
                        ),
                    )
                )

    for beat in delta.threads:
        ent = entity(beat.slug)
        if ent and ent.status == "resolved" and (beat.status or "active") == "active":
            flags.append(
                Flag(
                    type="stale_arc",
                    severity="major",
                    chapter=chapter,
                    body=f"thread `{ent.name}` is already resolved but marked active",
                )
            )

    for payoff in delta.payoffs:
        row = conn.execute("SELECT * FROM plants WHERE slug = ?", (payoff,)).fetchone()
        if not row and payoff not in {p.slug for p in delta.plants}:
            flags.append(
                Flag(
                    type="unpaid_plant",
                    severity="major",
                    chapter=chapter,
                    body=f"payoff `{payoff}` was never planted",
                )
            )

    return flags


def blocking(flags: list[Flag], *, strict: bool) -> list[Flag]:
    if not strict:
        return [f for f in flags if f.severity == "critical"]
    return [f for f in flags if f.severity in {"critical", "major"}]
