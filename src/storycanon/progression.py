from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from storycanon.db import Canon
from storycanon.models import Delta, Flag, slugify


def load_plugins(canon: Canon) -> list[dict[str, Any]]:
    plugins: list[dict[str, Any]] = []
    for folder in (canon.plugins_dir, canon.root / "systems"):
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.json")):
            if path.name.endswith(".example.json"):
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(data, dict) and data.get("attr") and data.get("ranks"):
                data["_path"] = str(path)
                plugins.append(data)
    return plugins


def copy_bundled_plugin(canon: Canon, name: str = "cultivation") -> Path:
    from importlib.resources import files

    src = files("storycanon").joinpath(f"data/plugins/{name}.json")
    canon.plugins_dir.mkdir(parents=True, exist_ok=True)
    dest = canon.plugins_dir / f"{name}.json"
    dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    return dest


def _rank_ids(plugin: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for raw in plugin.get("ranks") or []:
        if isinstance(raw, str):
            out.append(slugify(raw))
        elif isinstance(raw, dict):
            out.append(slugify(str(raw.get("id") or raw.get("name") or "")))
    return [r for r in out if r]


def rank_index(plugin: dict[str, Any], value: Any) -> int | None:
    if value is None or value == "":
        return None
    ranks = _rank_ids(plugin)
    token = slugify(str(value))
    if token in ranks:
        return ranks.index(token)
    # allow human names that slug the same
    return None


def _has_event(delta: Delta, kind: str, slug: str | None) -> bool:
    want = slugify(kind)
    for event in delta.events:
        if slugify(event.kind) != want:
            continue
        if slug is None or event.slug is None or event.slug == slug:
            return True
    return False


def check_progression(canon: Canon, delta: Delta) -> list[Flag]:
    flags: list[Flag] = []
    plugins = load_plugins(canon)
    if not plugins:
        return flags

    incoming = {e.slug: e for e in delta.new_entities}
    for plugin in plugins:
        attr = str(plugin.get("attr") or "stage")
        types = {str(t) for t in (plugin.get("entity_types") or ["character"])}
        ranks = _rank_ids(plugin)
        if not ranks:
            continue
        max_skip = int(plugin.get("max_skip_without_event", 0))
        skip_event = str(plugin.get("skip_event") or "breakthrough")
        allow_reg = bool(plugin.get("allow_regression", False))
        label = str(plugin.get("label") or plugin.get("id") or attr)

        for update in delta.updates:
            if attr not in update.set:
                continue
            new_val = update.set[attr]
            new_i = rank_index(plugin, new_val)
            if new_i is None:
                flags.append(
                    Flag(
                        type="illegal_progression",
                        severity="major",
                        chapter=delta.chapter,
                        body=(
                            f"`{update.slug}.{attr}` = `{new_val}` is not a rank in {label} "
                            f"({', '.join(ranks)})"
                        ),
                    )
                )
                continue

            ent = incoming.get(update.slug) or canon.get_by_slug(update.slug)
            if ent is None:
                continue
            if types and ent.type not in types and not incoming.get(update.slug):
                # new entity type from incoming NewEntity
                pass
            if hasattr(ent, "type") and types and ent.type not in types:
                continue

            old_val = None
            if incoming.get(update.slug):
                old_val = incoming[update.slug].attrs.get(attr)
            else:
                old_val = ent.attrs.get(attr) if hasattr(ent, "attrs") else None
            old_i = rank_index(plugin, old_val)
            if old_i is None:
                # first assignment: allow any listed rank
                continue
            step = new_i - old_i
            if step == 0:
                continue
            if step < 0 and not allow_reg:
                flags.append(
                    Flag(
                        type="illegal_progression",
                        severity="major",
                        chapter=delta.chapter,
                        body=(
                            f"`{update.slug}` {label} cannot regress "
                            f"{ranks[old_i]} → {ranks[new_i]}"
                        ),
                    )
                )
                continue
            if step > 1 + max_skip and not _has_event(delta, skip_event, update.slug):
                flags.append(
                    Flag(
                        type="illegal_progression",
                        severity="critical",
                        chapter=delta.chapter,
                        body=(
                            f"`{update.slug}` jumps {label} {ranks[old_i]} → {ranks[new_i]} "
                            f"(+{step}). Legal without event: +{1 + max_skip}. "
                            f"Add events:[{{kind:{skip_event!r}, slug:{update.slug!r}}}] "
                            f"or write the missing ranks."
                        ),
                    )
                )
                continue
            if step > 1 and not _has_event(delta, skip_event, update.slug):
                flags.append(
                    Flag(
                        type="illegal_progression",
                        severity="critical",
                        chapter=delta.chapter,
                        body=(
                            f"`{update.slug}` skips {label} ranks {ranks[old_i]} → {ranks[new_i]}. "
                            f"Requires a `{skip_event}` event on that character."
                        ),
                    )
                )
        for spec in delta.new_entities:
            if attr not in spec.attrs:
                continue
            if types and spec.type not in types:
                continue
            if rank_index(plugin, spec.attrs.get(attr)) is None:
                flags.append(
                    Flag(
                        type="illegal_progression",
                        severity="major",
                        chapter=delta.chapter,
                        body=(
                            f"new `{spec.slug}.{attr}` = `{spec.attrs.get(attr)}` "
                            f"is not a rank in {label}"
                        ),
                    )
                )
    return flags
