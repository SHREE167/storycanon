from __future__ import annotations

from storycanon.arcs import arc_stage, briefing_block, current_arc, upsert_arc
from storycanon.brief import assemble_brief


def test_briefing_includes_distance_to_climax(project):
    upsert_arc(
        project,
        "The Forged Letter",
        start_chapter=1,
        target_end_chapter=40,
        climax_chapter=35,
        status="active",
        summary="Expose the empire's lie.",
    )
    payload = assemble_brief(project, 12)
    md = payload["markdown"]
    assert "Macro-arc" in md
    assert "The Forged Letter" in md
    assert "35" in md
    assert "climax" in md.lower()
    info = arc_stage(current_arc(project, 12), 12)
    assert info["chapters_to_climax"] == 23
    assert info["stage"] in {"setup", "rising", "approach-climax"}
