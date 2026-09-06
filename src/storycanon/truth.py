from __future__ import annotations

import json
from typing import Any

from storycanon.db import Canon
from storycanon.models import ENTITY_TYPES, slugify


def set_truth(
    canon: Canon,
    slug: str,
    *,
    name: str | None = None,
    type: str | None = None,
    status: str | None = None,
    summary: str | None = None,
    attrs: dict[str, Any] | None = None,
    aliases: list[str] | None = None,
    create_type: str | None = None,
    chapter: int | None = None,
) -> str:
    slug = slugify(slug)
    chapter = chapter or max(canon.last_chapter_n(), 1)
    with canon.connect() as conn:
        ent = canon.get_by_slug(slug, conn)
        if ent is None:
            if not create_type:
                return f"No entity `{slug}`. Pass a type to create it."
            if create_type not in ENTITY_TYPES:
                return f"Unknown type `{create_type}`."
            ent = canon.insert_entity(
                conn,
                slug=slug,
                name=name or slug,
                type=create_type,
                status=status or ("alive" if create_type == "character" else "active"),
                aliases=list(aliases or []),
                attrs=dict(attrs or {}),
                summary=summary or "",
                chapter=chapter,
            )
            conn.commit()
            return f"Created {ent.type} `{ent.slug}` ({ent.name})."

        new_attrs = dict(ent.attrs)
        if attrs:
            new_attrs.update(attrs)
        new_aliases = list(ent.aliases)
        if aliases:
            for alias in aliases:
                canon.add_alias(conn, ent.id, alias, new_aliases)
        conn.execute(
            """
            UPDATE entities
            SET name = ?, type = ?, status = ?, summary = ?, attrs_json = ?,
                aliases_json = ?, updated_at = datetime('now')
            WHERE id = ?
            """,
            (
                name or ent.name,
                type or ent.type,
                status or ent.status,
                summary if summary is not None else ent.summary,
                json.dumps(new_attrs, ensure_ascii=False),
                json.dumps(new_aliases, ensure_ascii=False),
                ent.id,
            ),
        )
        conn.commit()
    return f"Updated `{slug}`."
