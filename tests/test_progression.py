from __future__ import annotations

from storycanon.ingest import ingest_chapter
from storycanon.progression import copy_bundled_plugin


def _seed(project):
    copy_bundled_plugin(project, "cultivation")
    r = ingest_chapter(
        project,
        {
            "chapter": 1,
            "summary": "Elara begins in Qi Refining.",
            "present": ["elara"],
            "location": "archives",
            "new_entities": [
                {
                    "name": "Elara",
                    "type": "character",
                    "attrs": {"stage": "qi-refining"},
                },
                {"name": "Archives", "type": "location"},
            ],
        },
    )
    assert r.ok, r.render()


def test_adjacent_rank_up_is_legal(project):
    _seed(project)
    r = ingest_chapter(
        project,
        {
            "chapter": 2,
            "summary": "Elara reaches Foundation.",
            "present": ["elara"],
            "location": "archives",
            "updates": [{"slug": "elara", "set": {"stage": "foundation"}}],
        },
    )
    assert r.ok, r.render()


def test_skip_to_nascent_soul_rejected_without_breakthrough(project):
    _seed(project)
    r = ingest_chapter(
        project,
        {
            "chapter": 2,
            "summary": "Elara skips three ranks.",
            "present": ["elara"],
            "location": "archives",
            "updates": [{"slug": "elara", "set": {"stage": "nascent-soul"}}],
        },
    )
    assert not r.ok
    assert any(f.type == "illegal_progression" for f in r.flags)


def test_skip_allowed_with_breakthrough_event(project):
    _seed(project)
    r = ingest_chapter(
        project,
        {
            "chapter": 2,
            "summary": "A tribulation shatters Elara's core.",
            "present": ["elara"],
            "location": "archives",
            "updates": [{"slug": "elara", "set": {"stage": "nascent-soul"}}],
            "events": [{"kind": "breakthrough", "slug": "elara", "note": "tribulation"}],
        },
    )
    assert r.ok, r.render()
