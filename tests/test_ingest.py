from __future__ import annotations

from storycanon.ingest import ingest_chapter
from storycanon.query import get_entity_text, query_canon, shortest_path


def test_happy_path_updates_location_and_knowledge(project):
    r1 = ingest_chapter(
        project,
        {
            "chapter": 1,
            "pov": "elara",
            "title": "The Letter",
            "summary": "Elara finds a forged letter in the archives.",
            "present": ["elara"],
            "location": "archives",
            "new_entities": [
                {"name": "Elara", "type": "character", "aliases": ["the archivist"]},
                {"name": "Archives", "type": "location"},
                {"name": "Kael", "type": "character"},
                {"name": "Black Fort", "type": "location"},
                {"name": "Heir Pact", "type": "secret"},
                {
                    "name": "Forged Records",
                    "type": "thread",
                    "summary": "The founding records are fake.",
                },
            ],
            "threads": [{"slug": "forged-records", "status": "active", "beat": "letter found"}],
            "plants": [{"slug": "forged-letter", "due_after": 5, "note": "the letter's seal"}],
        },
    )
    assert r1.ok, r1.message

    r2 = ingest_chapter(
        project,
        {
            "chapter": 2,
            "pov": "elara",
            "summary": "Kael hides Elara at the Black Fort. She learns the heir pact.",
            "present": ["elara", "kael"],
            "location": "black-fort",
            "learned": [{"character": "elara", "secret": "heir-pact"}],
            "edges": [{"src": "elara", "rel": "allied_with", "dst": "kael"}],
            "threads": [{"slug": "forged-records", "beat": "fled to the fort"}],
        },
    )
    assert r2.ok, r2.message

    elara = project.get_by_slug("elara")
    assert elara is not None
    assert elara.location() == "black-fort"
    assert project.last_chapter_n() == 2
    desk = project.canon_dir / "graph.html"
    easy = project.root / "storycanon-desk.html"
    assert desk.exists()
    assert "Elara" in desk.read_text(encoding="utf-8")
    assert easy.exists()
    sheet = get_entity_text(project, "the archivist")
    assert "Elara" in sheet
    assert "Heir Pact" in query_canon(project, "who knows heir-pact")
    path = shortest_path(project, "Elara", "Kael")
    assert "allied_with" in path


def test_duplicate_chapter_rejected(project):
    delta = {
        "chapter": 1,
        "summary": "Once.",
        "present": ["elara"],
        "location": "archives",
        "new_entities": [
            {"name": "Elara", "type": "character"},
            {"name": "Archives", "type": "location"},
        ],
    }
    assert ingest_chapter(project, delta).ok
    again = ingest_chapter(project, delta)
    assert not again.ok
    forced = ingest_chapter(project, delta, force=True)
    assert forced.ok


def test_alias_resolve(project):
    ingest_chapter(
        project,
        {
            "chapter": 1,
            "summary": "Meet the captain.",
            "present": ["rin"],
            "location": "dock",
            "new_entities": [
                {
                    "name": "Rin Voss",
                    "slug": "rin",
                    "type": "character",
                    "aliases": ["the captain", "Lady Voss"],
                },
                {"name": "Dock", "type": "location"},
            ],
        },
    )
    assert project.resolve("Lady Voss").slug == "rin"
    assert project.resolve("the captain").slug == "rin"
