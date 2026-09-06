from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Literal

ENTITY_TYPES = (
    "character",
    "location",
    "faction",
    "item",
    "thread",
    "rule",
    "secret",
    "event",
)

DEAD_STATUSES = frozenset({"dead", "destroyed"})


def slugify(name: str) -> str:
    text = unicodedata.normalize("NFKD", name or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text or "unnamed"


def norm_alias(name: str) -> str:
    return slugify(name)


@dataclass
class Entity:
    id: int
    slug: str
    name: str
    type: str
    status: str
    aliases: list[str]
    attrs: dict[str, Any]
    summary: str
    first_chapter: int | None
    last_seen_chapter: int | None

    def location(self) -> str | None:
        loc = self.attrs.get("location")
        return str(loc) if loc else None

    def sheet_lines(self) -> list[str]:
        lines = [f"**{self.name}** (`{self.slug}`, {self.type}, {self.status})"]
        if self.aliases:
            lines.append("aliases: " + ", ".join(self.aliases))
        for key in ("appearance", "voice", "goal", "injury", "location", "occupation"):
            if self.attrs.get(key):
                lines.append(f"{key}: {self.attrs[key]}")
        extra = {
            k: v
            for k, v in self.attrs.items()
            if k not in {"appearance", "voice", "goal", "injury", "location", "occupation"}
            and v not in (None, "", [], {})
        }
        if extra:
            lines.append("attrs: " + json.dumps(extra, ensure_ascii=False))
        if self.summary:
            lines.append(self.summary)
        if self.last_seen_chapter is not None:
            lines.append(f"last seen: ch.{self.last_seen_chapter}")
        return lines


@dataclass
class Flag:
    type: str
    severity: Literal["critical", "major", "minor"]
    body: str
    chapter: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "severity": self.severity,
            "chapter": self.chapter,
            "body": self.body,
        }


@dataclass
class NewEntity:
    slug: str
    name: str
    type: str
    status: str = "active"
    aliases: list[str] = field(default_factory=list)
    attrs: dict[str, Any] = field(default_factory=dict)
    summary: str = ""


@dataclass
class EntityUpdate:
    slug: str
    set: dict[str, Any] = field(default_factory=dict)
    status: str | None = None
    summary: str | None = None
    aliases: list[str] = field(default_factory=list)


@dataclass
class EdgeSpec:
    src: str
    rel: str
    dst: str
    note: str = ""


@dataclass
class LearnedSpec:
    character: str
    secret: str


@dataclass
class ThreadBeat:
    slug: str
    status: str | None = None
    beat: str | None = None


@dataclass
class PlantSpec:
    slug: str
    kind: str = "chekhov"
    due_after: int | None = None
    note: str = ""


@dataclass
class EventSpec:
    kind: str
    slug: str | None = None
    note: str = ""


@dataclass
class Delta:
    chapter: int
    pov: str | None = None
    present: list[str] = field(default_factory=list)
    location: str | None = None
    title: str = ""
    summary: str = ""
    time_advance: str | None = None
    new_entities: list[NewEntity] = field(default_factory=list)
    updates: list[EntityUpdate] = field(default_factory=list)
    edges: list[EdgeSpec] = field(default_factory=list)
    learned: list[LearnedSpec] = field(default_factory=list)
    threads: list[ThreadBeat] = field(default_factory=list)
    plants: list[PlantSpec] = field(default_factory=list)
    payoffs: list[str] = field(default_factory=list)
    referenced_secrets: list[str] = field(default_factory=list)
    events: list[EventSpec] = field(default_factory=list)

    def all_referenced_slugs(self) -> set[str]:
        slugs: set[str] = set()
        if self.pov:
            slugs.add(self.pov)
        slugs.update(self.present)
        if self.location:
            slugs.add(self.location)
        for item in self.updates:
            slugs.add(item.slug)
        for edge in self.edges:
            slugs.add(edge.src)
            slugs.add(edge.dst)
        for learned in self.learned:
            slugs.add(learned.character)
            slugs.add(learned.secret)
        for thread in self.threads:
            slugs.add(thread.slug)
        slugs.update(self.referenced_secrets)
        slugs.update(self.payoffs)
        for event in self.events:
            if event.slug:
                slugs.add(event.slug)
        return {slugify(s) for s in slugs if s}


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    raise ValueError(f"expected list, got {type(value).__name__}")


def _as_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    raise ValueError(f"expected object, got {type(value).__name__}")


def parse_delta(data: dict[str, Any]) -> Delta:
    if not isinstance(data, dict):
        raise ValueError("delta must be a JSON object")
    if "chapter" not in data:
        raise ValueError("delta.chapter is required")
    try:
        chapter = int(data["chapter"])
    except (TypeError, ValueError) as exc:
        raise ValueError("delta.chapter must be an integer") from exc
    if chapter < 1:
        raise ValueError("delta.chapter must be >= 1")

    new_entities: list[NewEntity] = []
    for raw in _as_list(data.get("new_entities")):
        item = _as_dict(raw)
        name = str(item.get("name") or "").strip()
        if not name:
            raise ValueError("new_entities[].name is required")
        etype = str(item.get("type") or "character").strip().lower()
        if etype not in ENTITY_TYPES:
            raise ValueError(f"unknown entity type: {etype}")
        slug = slugify(str(item.get("slug") or name))
        aliases = [str(a) for a in _as_list(item.get("aliases"))]
        new_entities.append(
            NewEntity(
                slug=slug,
                name=name,
                type=etype,
                status=str(item.get("status") or ("active" if etype != "character" else "alive")),
                aliases=aliases,
                attrs=_as_dict(item.get("attrs")),
                summary=str(item.get("summary") or ""),
            )
        )

    updates: list[EntityUpdate] = []
    for raw in _as_list(data.get("updates")):
        item = _as_dict(raw)
        slug = slugify(str(item.get("slug") or ""))
        if not slug:
            raise ValueError("updates[].slug is required")
        updates.append(
            EntityUpdate(
                slug=slug,
                set=_as_dict(item.get("set")),
                status=str(item["status"]) if item.get("status") else None,
                summary=str(item["summary"]) if item.get("summary") is not None else None,
                aliases=[str(a) for a in _as_list(item.get("aliases"))],
            )
        )

    edges: list[EdgeSpec] = []
    for raw in _as_list(data.get("edges")):
        item = _as_dict(raw)
        src = slugify(str(item.get("src") or ""))
        dst = slugify(str(item.get("dst") or ""))
        rel = str(item.get("rel") or "").strip()
        if not src or not dst or not rel:
            raise ValueError("edges[] need src, rel, dst")
        edges.append(EdgeSpec(src=src, rel=rel, dst=dst, note=str(item.get("note") or "")))

    learned: list[LearnedSpec] = []
    for raw in _as_list(data.get("learned")):
        item = _as_dict(raw)
        character = slugify(str(item.get("character") or ""))
        secret = slugify(str(item.get("secret") or ""))
        if not character or not secret:
            raise ValueError("learned[] need character and secret")
        learned.append(LearnedSpec(character=character, secret=secret))

    threads: list[ThreadBeat] = []
    for raw in _as_list(data.get("threads")):
        item = _as_dict(raw)
        slug = slugify(str(item.get("slug") or ""))
        if not slug:
            raise ValueError("threads[].slug is required")
        threads.append(
            ThreadBeat(
                slug=slug,
                status=str(item["status"]) if item.get("status") else None,
                beat=str(item["beat"]) if item.get("beat") is not None else None,
            )
        )

    plants: list[PlantSpec] = []
    for raw in _as_list(data.get("plants")):
        item = _as_dict(raw)
        slug = slugify(str(item.get("slug") or ""))
        if not slug:
            raise ValueError("plants[].slug is required")
        due = item.get("due_after")
        plants.append(
            PlantSpec(
                slug=slug,
                kind=str(item.get("kind") or "chekhov"),
                due_after=int(due) if due is not None else None,
                note=str(item.get("note") or ""),
            )
        )

    present = [slugify(str(s)) for s in _as_list(data.get("present")) if str(s).strip()]
    payoffs = [slugify(str(s)) for s in _as_list(data.get("payoffs")) if str(s).strip()]
    referenced = [
        slugify(str(s)) for s in _as_list(data.get("referenced_secrets")) if str(s).strip()
    ]

    events: list[EventSpec] = []
    for raw in _as_list(data.get("events")):
        item = _as_dict(raw)
        kind = str(item.get("kind") or "").strip().lower()
        if not kind:
            raise ValueError("events[].kind is required")
        slug_raw = item.get("slug")
        events.append(
            EventSpec(
                kind=kind,
                slug=slugify(str(slug_raw)) if slug_raw else None,
                note=str(item.get("note") or ""),
            )
        )

    pov = data.get("pov")
    location = data.get("location")
    return Delta(
        chapter=chapter,
        pov=slugify(str(pov)) if pov else None,
        present=present,
        location=slugify(str(location)) if location else None,
        title=str(data.get("title") or ""),
        summary=str(data.get("summary") or "").strip(),
        time_advance=str(data["time_advance"]) if data.get("time_advance") else None,
        new_entities=new_entities,
        updates=updates,
        edges=edges,
        learned=learned,
        threads=threads,
        plants=plants,
        payoffs=payoffs,
        referenced_secrets=referenced,
        events=events,
    )


DELTA_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["chapter", "summary"],
    "properties": {
        "chapter": {"type": "integer", "minimum": 1},
        "pov": {"type": "string"},
        "present": {"type": "array", "items": {"type": "string"}},
        "location": {"type": "string"},
        "title": {"type": "string"},
        "summary": {"type": "string"},
        "time_advance": {"type": "string"},
        "new_entities": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name", "type"],
                "properties": {
                    "slug": {"type": "string"},
                    "name": {"type": "string"},
                    "type": {"enum": list(ENTITY_TYPES)},
                    "status": {"type": "string"},
                    "aliases": {"type": "array", "items": {"type": "string"}},
                    "attrs": {"type": "object"},
                    "summary": {"type": "string"},
                },
            },
        },
        "updates": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["slug"],
                "properties": {
                    "slug": {"type": "string"},
                    "set": {"type": "object"},
                    "status": {"type": "string"},
                    "summary": {"type": "string"},
                    "aliases": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "edges": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["src", "rel", "dst"],
                "properties": {
                    "src": {"type": "string"},
                    "rel": {"type": "string"},
                    "dst": {"type": "string"},
                    "note": {"type": "string"},
                },
            },
        },
        "learned": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["character", "secret"],
                "properties": {
                    "character": {"type": "string"},
                    "secret": {"type": "string"},
                },
            },
        },
        "threads": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["slug"],
                "properties": {
                    "slug": {"type": "string"},
                    "status": {"type": "string"},
                    "beat": {"type": "string"},
                },
            },
        },
        "plants": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["slug"],
                "properties": {
                    "slug": {"type": "string"},
                    "kind": {"type": "string"},
                    "due_after": {"type": "integer"},
                    "note": {"type": "string"},
                },
            },
        },
        "payoffs": {"type": "array", "items": {"type": "string"}},
        "referenced_secrets": {"type": "array", "items": {"type": "string"}},
        "events": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["kind"],
                "properties": {
                    "kind": {"type": "string", "description": "e.g. breakthrough, death, travel"},
                    "slug": {"type": "string"},
                    "note": {"type": "string"},
                },
            },
        },
    },
}
