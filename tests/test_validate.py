from __future__ import annotations

from storycanon.ingest import ingest_chapter
from storycanon.models import parse_delta


def _base_cast():
    return [
        {
            "name": "Elara",
            "type": "character",
            "attrs": {"voice": "dry, precise"},
        },
        {"name": "Archives", "type": "location"},
    ]


def test_dead_character_cannot_appear(project):
    ingest_chapter(
        project,
        {
            "chapter": 1,
            "summary": "Elara is introduced.",
            "present": ["elara"],
            "location": "archives",
            "new_entities": _base_cast(),
            "updates": [{"slug": "elara", "status": "dead"}],
        },
    )
    result = ingest_chapter(
        project,
        {
            "chapter": 2,
            "summary": "A corpse walks.",
            "present": ["elara"],
            "location": "archives",
        },
    )
    assert not result.ok
    assert any(f.type == "contradiction" for f in result.flags)


def test_unknown_slug_strict(project):
    result = ingest_chapter(
        project,
        {
            "chapter": 1,
            "summary": "Someone new.",
            "present": ["mystery-man"],
        },
        strict=True,
    )
    assert not result.ok
    assert any(f.type == "unknown_entity" for f in result.flags)


def test_secret_leak_rejected(project):
    ingest_chapter(
        project,
        {
            "chapter": 1,
            "summary": "The pact exists, Elara does not know it.",
            "present": ["elara"],
            "location": "archives",
            "new_entities": _base_cast()
            + [{"name": "Heir Pact", "type": "secret", "slug": "heir-pact"}],
        },
    )
    result = ingest_chapter(
        project,
        {
            "chapter": 2,
            "pov": "elara",
            "summary": "Elara recites the pact she has never learned.",
            "present": ["elara"],
            "location": "archives",
            "referenced_secrets": ["heir-pact"],
        },
    )
    assert not result.ok
    assert any("does not know" in f.body for f in result.flags)


def test_payoff_without_plant(project):
    result = ingest_chapter(
        project,
        {
            "chapter": 1,
            "summary": "A gun fires that was never shown.",
            "present": ["elara"],
            "location": "archives",
            "new_entities": _base_cast(),
            "payoffs": ["obsidian-key"],
        },
        strict=True,
    )
    assert not result.ok
    assert any(f.type == "unpaid_plant" for f in result.flags)


def test_parse_delta_requires_chapter():
    try:
        parse_delta({"summary": "no chapter"})
        assert False, "should have raised"
    except ValueError as exc:
        assert "chapter" in str(exc)
