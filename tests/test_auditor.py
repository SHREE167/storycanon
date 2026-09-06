from __future__ import annotations

from storycanon.auditor import audit_delta, auditor_prompt
from storycanon.ingest import ingest_chapter
from storycanon.progression import copy_bundled_plugin


def test_auditor_prompt_asks_for_delta_not_prose(project):
    ingest_chapter(
        project,
        {
            "chapter": 1,
            "summary": "Meet Elara.",
            "present": ["elara"],
            "location": "archives",
            "new_entities": [
                {"name": "Elara", "type": "character"},
                {"name": "Archives", "type": "location"},
            ],
        },
    )
    text = auditor_prompt(project, 2, "Elara fled the archives with a burned hand.")
    assert "AUDITOR" in text
    assert "elara" in text.lower()
    assert "Do not write prose" in text or "not the novelist" in text.lower()


def test_audit_diffs_injury_and_rejects_illegal_jump(project):
    copy_bundled_plugin(project, "cultivation")
    ingest_chapter(
        project,
        {
            "chapter": 1,
            "summary": "Begin.",
            "present": ["elara"],
            "location": "archives",
            "new_entities": [
                {"name": "Elara", "type": "character", "attrs": {"stage": "qi-refining"}},
                {"name": "Archives", "type": "location"},
                {"name": "Black Fort", "type": "location"},
            ],
        },
    )
    ok = audit_delta(
        project,
        {
            "chapter": 2,
            "summary": "Elara is hurt at the fort.",
            "present": ["elara"],
            "location": "black-fort",
            "updates": [{"slug": "elara", "set": {"injury": "burned hand", "location": "black-fort"}}],
        },
    )
    assert ok.ok
    assert any("injury" in line for line in ok.diff)

    bad = audit_delta(
        project,
        {
            "chapter": 2,
            "summary": "Elara becomes a Nascent Soul on the stairs.",
            "present": ["elara"],
            "location": "archives",
            "updates": [{"slug": "elara", "set": {"stage": "nascent-soul"}}],
        },
    )
    assert not bad.ok
    assert any(f.type == "illegal_progression" for f in bad.flags)
