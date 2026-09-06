from __future__ import annotations

from storycanon.ingest import ingest_chapter
from storycanon.query import beats_text
from storycanon.viz import desk_payload


def test_ingest_records_scene_plant_and_reveal(project):
    result = ingest_chapter(
        project,
        {
            "chapter": 1,
            "pov": "elara",
            "summary": "Elara finds the letter.",
            "present": ["elara"],
            "location": "archives",
            "new_entities": [
                {"name": "Elara", "type": "character"},
                {"name": "Archives", "type": "location"},
                {"name": "Heir Pact", "type": "secret"},
                {"name": "Forged Records", "type": "thread"},
            ],
            "threads": [{"slug": "forged-records", "status": "active", "beat": "letter found"}],
            "plants": [{"slug": "forged-letter", "note": "wax seal is wrong"}],
            "learned": [{"character": "elara", "secret": "heir-pact"}],
        },
    )
    assert result.ok, result.render()
    text = beats_text(project)
    assert "[scene]" in text
    assert "[plant]" in text
    assert "[reveal]" in text
    assert "[thread]" in text
    payload = desk_payload(project)
    kinds = {b["kind"] for b in payload["beats"]}
    assert {"scene", "plant", "reveal", "thread"} <= kinds
    assert payload["stats"]["beats"] >= 4
