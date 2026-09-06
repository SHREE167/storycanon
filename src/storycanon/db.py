from __future__ import annotations

import json
import sqlite3
from importlib.resources import files
from pathlib import Path
from typing import Any, Iterator

from storycanon.models import Entity, slugify

DEFAULT_CONFIG = {
    "title": "Untitled Novel",
    "premise": "",
    "token_budget": 4000,
    "strict_ingest": True,
    "default_pov": "",
    "plant_due_after": 8,
    "recent_window": 5,
    "stale_after": 20,
}


def find_root(start: Path | None = None) -> Path:
    cur = (start or Path.cwd()).resolve()
    for candidate in [cur, *cur.parents]:
        if (candidate / "storycanon.toml").exists() or (candidate / ".storycanon").is_dir():
            return candidate
    return cur


def load_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    import tomllib

    return tomllib.loads(path.read_text(encoding="utf-8"))


def dump_toml(data: dict[str, Any]) -> str:
    lines: list[str] = []
    for key, value in data.items():
        if isinstance(value, bool):
            lines.append(f"{key} = {'true' if value else 'false'}")
        elif isinstance(value, (int, float)):
            lines.append(f"{key} = {value}")
        else:
            escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'{key} = "{escaped}"')
    return "\n".join(lines) + "\n"


def _schema_sql() -> str:
    return files("storycanon").joinpath("data/schema.sql").read_text(encoding="utf-8")


class Canon:
    def __init__(self, root: Path | None = None):
        # Explicit path is the project root. Discovery from cwd is find_root().
        self.root = Path(root).resolve() if root is not None else find_root()
        self.canon_dir = self.root / ".storycanon"
        self.db_path = self.canon_dir / "canon.sqlite"
        self.log_path = self.canon_dir / "ingest-log.jsonl"
        self.cfg_path = self.root / "storycanon.toml"
        self.chapters_dir = self.root / "chapters"
        self.drafts_dir = self.root / "drafts"
        self.bible_dir = self.root / "bible"
        file_cfg = load_toml(self.cfg_path)
        self.cfg = {**DEFAULT_CONFIG, **file_cfg}

    def exists(self) -> bool:
        return self.db_path.exists()

    def connect(self) -> sqlite3.Connection:
        if not self.db_path.exists():
            raise FileNotFoundError(
                f"No StoryCanon project at {self.root}. Run `storycanon init` first."
            )
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(_schema_sql())
        return conn

    def init_project(self, premise: str, title: str = "Untitled Novel") -> None:
        self.canon_dir.mkdir(parents=True, exist_ok=True)
        self.chapters_dir.mkdir(exist_ok=True)
        self.drafts_dir.mkdir(exist_ok=True)
        self.bible_dir.mkdir(exist_ok=True)
        (self.bible_dir / "characters").mkdir(exist_ok=True)
        (self.bible_dir / "threads").mkdir(exist_ok=True)
        (self.bible_dir / "world").mkdir(exist_ok=True)
        cfg = {
            **DEFAULT_CONFIG,
            "title": title,
            "premise": premise.strip(),
        }
        if not self.cfg_path.exists():
            self.cfg_path.write_text(dump_toml(cfg), encoding="utf-8")
        self.cfg = {**DEFAULT_CONFIG, **load_toml(self.cfg_path)}
        conn = sqlite3.connect(self.db_path)
        conn.executescript(_schema_sql())
        conn.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES(?, ?)",
            ("title", title),
        )
        conn.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES(?, ?)",
            ("premise", premise.strip()),
        )
        conn.commit()
        conn.close()
        gitignore = self.root / ".gitignore"
        extra = "\n".join(
            [
                ".storycanon/ingest-log.jsonl",
                "storycanon-desk.html",
                "",
            ]
        )
        if gitignore.exists():
            text = gitignore.read_text(encoding="utf-8")
            if ".storycanon/ingest-log.jsonl" not in text:
                gitignore.write_text(text.rstrip() + "\n" + extra, encoding="utf-8")
        else:
            gitignore.write_text(extra, encoding="utf-8")

    def meta(self, key: str, default: str = "") -> str:
        with self.connect() as conn:
            row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
            return row["value"] if row else default

    def set_meta(self, key: str, value: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES(?, ?)",
                (key, value),
            )
            conn.commit()

    def _row_to_entity(self, row: sqlite3.Row) -> Entity:
        return Entity(
            id=row["id"],
            slug=row["slug"],
            name=row["name"],
            type=row["type"],
            status=row["status"],
            aliases=json.loads(row["aliases_json"] or "[]"),
            attrs=json.loads(row["attrs_json"] or "{}"),
            summary=row["summary"] or "",
            first_chapter=row["first_chapter"],
            last_seen_chapter=row["last_seen_chapter"],
        )

    def get_by_slug(self, slug: str, conn: sqlite3.Connection | None = None) -> Entity | None:
        slug = slugify(slug)
        own = conn is None
        conn = conn or self.connect()
        try:
            row = conn.execute("SELECT * FROM entities WHERE slug = ?", (slug,)).fetchone()
            return self._row_to_entity(row) if row else None
        finally:
            if own:
                conn.close()

    def resolve(self, name_or_slug: str, conn: sqlite3.Connection | None = None) -> Entity | None:
        token = slugify(name_or_slug)
        own = conn is None
        conn = conn or self.connect()
        try:
            row = conn.execute("SELECT * FROM entities WHERE slug = ?", (token,)).fetchone()
            if row:
                return self._row_to_entity(row)
            rows = conn.execute(
                """
                SELECT e.* FROM aliases a
                JOIN entities e ON e.id = a.entity_id
                WHERE a.alias_norm = ?
                """,
                (token,),
            ).fetchall()
            if len(rows) == 1:
                return self._row_to_entity(rows[0])
            if len(rows) > 1:
                return None
            rows = conn.execute(
                "SELECT * FROM entities WHERE lower(name) = lower(?)",
                (name_or_slug.strip(),),
            ).fetchall()
            if len(rows) == 1:
                return self._row_to_entity(rows[0])
            return None
        finally:
            if own:
                conn.close()

    def resolve_all(self, name_or_slug: str, conn: sqlite3.Connection | None = None) -> list[Entity]:
        token = slugify(name_or_slug)
        own = conn is None
        conn = conn or self.connect()
        try:
            seen: dict[int, Entity] = {}
            row = conn.execute("SELECT * FROM entities WHERE slug = ?", (token,)).fetchone()
            if row:
                seen[row["id"]] = self._row_to_entity(row)
            for r in conn.execute(
                """
                SELECT e.* FROM aliases a
                JOIN entities e ON e.id = a.entity_id
                WHERE a.alias_norm = ?
                """,
                (token,),
            ):
                seen[r["id"]] = self._row_to_entity(r)
            return list(seen.values())
        finally:
            if own:
                conn.close()

    def add_alias(
        self, conn: sqlite3.Connection, entity_id: int, alias: str, aliases_json: list[str]
    ) -> None:
        raw = alias.strip()
        if not raw:
            return
        norm = slugify(raw)
        conn.execute(
            "INSERT OR IGNORE INTO aliases(alias_norm, entity_id, alias_raw) VALUES(?,?,?)",
            (norm, entity_id, raw),
        )
        if raw not in aliases_json:
            aliases_json.append(raw)

    def insert_entity(
        self,
        conn: sqlite3.Connection,
        *,
        slug: str,
        name: str,
        type: str,
        status: str,
        aliases: list[str],
        attrs: dict[str, Any],
        summary: str,
        chapter: int,
    ) -> Entity:
        slug = slugify(slug)
        cur = conn.execute(
            """
            INSERT INTO entities(slug, name, type, status, aliases_json, attrs_json, summary,
                                 first_chapter, last_seen_chapter)
            VALUES(?,?,?,?,?,?,?,?,?)
            """,
            (
                slug,
                name,
                type,
                status,
                json.dumps(aliases, ensure_ascii=False),
                json.dumps(attrs, ensure_ascii=False),
                summary,
                chapter,
                chapter,
            ),
        )
        eid = int(cur.lastrowid)
        self.add_alias(conn, eid, name, aliases)
        self.add_alias(conn, eid, slug, aliases)
        for alias in list(aliases):
            self.add_alias(conn, eid, alias, aliases)
        conn.execute(
            "UPDATE entities SET aliases_json = ? WHERE id = ?",
            (json.dumps(aliases, ensure_ascii=False), eid),
        )
        return Entity(
            id=eid,
            slug=slug,
            name=name,
            type=type,
            status=status,
            aliases=aliases,
            attrs=attrs,
            summary=summary,
            first_chapter=chapter,
            last_seen_chapter=chapter,
        )

    def list_entities(self, type: str | None = None) -> list[Entity]:
        with self.connect() as conn:
            if type:
                rows = conn.execute(
                    "SELECT * FROM entities WHERE type = ? ORDER BY name", (type,)
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM entities ORDER BY type, name").fetchall()
            return [self._row_to_entity(r) for r in rows]

    def last_chapter_n(self) -> int:
        with self.connect() as conn:
            row = conn.execute("SELECT MAX(n) AS n FROM chapters").fetchone()
            return int(row["n"] or 0)

    def get_chapter(self, n: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM chapters WHERE n = ?", (n,)).fetchone()
            if not row:
                return None
            return dict(row)

    def recent_chapters(self, limit: int = 2) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM chapters ORDER BY n DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in reversed(rows)]

    def open_edges(self, src_id: int | None = None) -> list[sqlite3.Row]:
        with self.connect() as conn:
            if src_id is None:
                return conn.execute(
                    "SELECT * FROM edges WHERE to_chapter IS NULL"
                ).fetchall()
            return conn.execute(
                "SELECT * FROM edges WHERE src_id = ? AND to_chapter IS NULL",
                (src_id,),
            ).fetchall()

    def iter_open_graph(self) -> tuple[dict[int, Entity], list[tuple[int, str, int, int]]]:
        """Return entities and (src_id, rel, dst_id, evidence_chapter) for open edges."""
        with self.connect() as conn:
            entities = {
                r["id"]: self._row_to_entity(r)
                for r in conn.execute("SELECT * FROM entities")
            }
            edges = [
                (r["src_id"], r["rel"], r["dst_id"], r["evidence_chapter"])
                for r in conn.execute("SELECT * FROM edges WHERE to_chapter IS NULL")
            ]
            return entities, edges

    def append_log(self, record: dict[str, Any]) -> None:
        self.canon_dir.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
