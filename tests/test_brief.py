from __future__ import annotations

from storycanon.brief import assemble_brief
from storycanon.ingest import ingest_chapter
from storycanon.query import status_text


def _ingest_serial(project) -> None:
    steps = [
        {
            "chapter": 1,
            "pov": "elara",
            "title": "The Letter",
            "summary": "Elara finds a forged founding letter in the imperial archives.",
            "present": ["elara"],
            "location": "archives",
            "new_entities": [
                {
                    "name": "Elara",
                    "type": "character",
                    "attrs": {"voice": "dry", "goal": "prove the forgery"},
                },
                {"name": "Archives", "type": "location"},
                {"name": "Kael", "type": "character"},
                {"name": "Black Fort", "type": "location"},
                {"name": "Vault City", "type": "location"},
                {"name": "Voss", "type": "character"},
                {"name": "Heir Pact", "type": "secret"},
                {
                    "name": "Forged Records",
                    "type": "thread",
                    "summary": "The empire's founding records are fake.",
                },
            ],
            "threads": [{"slug": "forged-records", "status": "active", "beat": "letter found"}],
            "plants": [
                {
                    "slug": "forged-letter",
                    "due_after": 5,
                    "note": "the wax seal does not match the year",
                }
            ],
        },
        {
            "chapter": 2,
            "pov": "elara",
            "summary": "Kael hides Elara. They agree to run.",
            "present": ["elara", "kael"],
            "location": "archives",
            "edges": [{"src": "elara", "rel": "allied_with", "dst": "kael"}],
        },
        {
            "chapter": 3,
            "pov": "elara",
            "summary": "They reach the Black Fort at dusk.",
            "present": ["elara", "kael"],
            "location": "black-fort",
        },
        {
            "chapter": 4,
            "pov": "elara",
            "summary": "Elara learns the heir pact from a hidden folio.",
            "present": ["elara"],
            "location": "black-fort",
            "learned": [{"character": "elara", "secret": "heir-pact"}],
        },
        {
            "chapter": 5,
            "pov": "kael",
            "summary": "Kael is stabbed covering Elara's escape.",
            "present": ["elara", "kael"],
            "location": "black-fort",
            "updates": [{"slug": "kael", "set": {"injury": "stabbed side"}}],
        },
        {
            "chapter": 6,
            "pov": "elara",
            "summary": "Elara leaves the wounded Kael and rides for Vault City.",
            "present": ["elara"],
            "location": "vault-city",
        },
        {
            "chapter": 7,
            "pov": "elara",
            "summary": "Voss intercepts her in the market and smiles like a knife.",
            "present": ["elara", "voss"],
            "location": "vault-city",
        },
        {
            "chapter": 8,
            "pov": "elara",
            "summary": "Elara reaches the vault door. The seal on the letter matches the lock.",
            "present": ["elara"],
            "location": "vault-city",
            "threads": [{"slug": "forged-records", "beat": "vault door, seal matches"}],
        },
    ]
    for delta in steps:
        result = ingest_chapter(project, delta)
        assert result.ok, result.render()


def test_chapter_9_brief_keeps_state_without_dumping_book(project):
    _ingest_serial(project)
    payload = assemble_brief(project, 9, token_budget=4000)
    md = payload["markdown"]

    assert "vault-city" in md.lower() or "Vault City" in md
    assert "Elara" in md
    assert "forged-letter" in payload["due_plants"]
    assert "forged-letter" in md
    assert "Forged Records" in md
    assert "stabbed" in md.lower()
    # Only the last two summaries, not chapter 1's text.
    assert "vault door" in md.lower()
    assert "Voss intercepts" in md
    assert "Elara finds a forged founding letter" not in md
    assert payload["truncated"] is False
    assert payload["approx_tokens"] <= 4000
    assert "CHAPTER TEXT" not in md

    status = status_text(project)
    assert "Forged Records" in status
    assert "forged-letter" in status
