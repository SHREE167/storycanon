from __future__ import annotations

from storycanon.ingest import ingest_chapter
from storycanon.viz import graph_payload, write_graph


def test_viz_html_contains_cast(project):
    result = ingest_chapter(
        project,
        {
            "chapter": 1,
            "summary": "Elara finds Kael in the archives.",
            "present": ["elara", "kael"],
            "location": "archives",
            "new_entities": [
                {"name": "Elara", "type": "character"},
                {"name": "Kael", "type": "character"},
                {"name": "Archives", "type": "location"},
                {"name": "Heir Pact", "type": "secret"},
            ],
            "learned": [{"character": "elara", "secret": "heir-pact"}],
            "edges": [{"src": "elara", "rel": "allied_with", "dst": "kael"}],
            "plants": [{"slug": "forged-letter", "due_after": 5}],
        },
    )
    assert result.ok, result.render()
    payload = graph_payload(project)
    ids = {n["id"] for n in payload["nodes"]}
    assert {"elara", "kael", "archives", "heir-pact", "forged-letter"} <= ids
    rels = {e["rel"] for e in payload["edges"]}
    assert "allied_with" in rels
    assert "knows" in rels
    path = write_graph(project)
    html = path.read_text(encoding="utf-8")
    assert "Elara" in html
    assert "StoryCanon" in html
    assert "Beats" in html
    assert "Timeline" in html
    assert path.exists()
