from __future__ import annotations

from storycanon.brief import assemble_brief
from storycanon.ingest import ingest_chapter


def test_200_chapters_brief_stays_under_budget(project):
    cast = [
        {"name": "Elara", "type": "character"},
        {"name": "Kael", "type": "character"},
        {"name": "Voss", "type": "character"},
        {"name": "Rin", "type": "character"},
        {"name": "Mira", "type": "character"},
        {"name": "Archives", "type": "location"},
        {"name": "Fort", "type": "location"},
        {"name": "City", "type": "location"},
        {"name": "Road", "type": "location"},
        {
            "name": "The Hunt",
            "type": "thread",
            "summary": "They are being hunted.",
        },
    ]
    people = ["elara", "kael", "voss", "rin", "mira"]
    places = ["archives", "fort", "city", "road"]

    first = ingest_chapter(
        project,
        {
            "chapter": 1,
            "pov": "elara",
            "summary": "The story begins.",
            "present": ["elara", "kael"],
            "location": "archives",
            "new_entities": cast,
            "threads": [{"slug": "the-hunt", "status": "active", "beat": "starts"}],
            "plants": [{"slug": "hidden-key", "due_after": 30}],
        },
        strict=True,
    )
    assert first.ok, first.render()

    for n in range(2, 201):
        pov = people[n % len(people)]
        loc = places[n % len(places)]
        partner = people[(n + 1) % len(people)]
        result = ingest_chapter(
            project,
            {
                "chapter": n,
                "pov": pov,
                "summary": f"Chapter {n}: {pov} travels to {loc} with {partner}.",
                "present": [pov, partner],
                "location": loc,
                "threads": [{"slug": "the-hunt", "beat": f"still hunted in ch.{n}"}],
            },
            strict=True,
        )
        assert result.ok, result.render()

    payload = assemble_brief(project, 201, token_budget=4000)
    assert payload["approx_tokens"] <= 4500  # small slack for the truncation notice path
    md = payload["markdown"]
    assert "Elara" in md or "elara" in md.lower()
    assert "The Hunt" in md
    # Must not concatenate 200 summaries.
    assert md.count("Chapter ") < 10
    assert project.last_chapter_n() == 200
