---
name: storycanon
description: Continuity engine for long novels. Use when writing or editing a webnovel/serial so the agent does not lose characters, threads, or canon. Triggers on chapter, webnovel, story bible, plot continuity, StoryCanon.
---

# StoryCanon

Write against local canon, not chat memory. Engine: `storycanon` CLI / MCP tools of the same name.

If missing:

```text
pip install "git+https://github.com/SHREE167/storycanon.git"
storycanon install
```

## Two-pass loop (mandatory)

The **drafter** writes prose only. The **auditor** writes `delta.json`. Never the same pass.

1. Drafter: `brief_chapter` for N (respect **Macro-arc** stage and chapters-to-climax).
2. Drafter: write `chapters/` from that briefing. **Do not invent a delta.**
3. Auditor (fresh context / subagent): `auditor_prompt` with N and the chapter path. Follow that prompt. Return only delta JSON.
4. `audit_chapter` with that delta (diffs vs canon, including illegal power-system jumps).
5. If audit is OK: `ingest_chapter`. If REJECT: fix prose or add a real `breakthrough` event. Not canon until ingest OK.

Use the `storycanon-auditor` skill for step 3 when available.

## Power systems

If `plugins/*.json` exists, attr changes on that ladder must be legal. Adjacent rank-ups are fine. Skipping ranks requires `events: [{kind:"breakthrough", slug:"<character>"}]` and the prose must show the breakthrough.

## Macro-arcs

`set_arc` / `storycanon arc-add`. Briefings include stage and distance to climax. Do not fire the climax early.

## delta_json (auditor output only)

```json
{
  "chapter": 12,
  "pov": "elara",
  "present": ["elara", "kael"],
  "location": "black-fort",
  "summary": "8-12 lines of what the prose states.",
  "updates": [{"slug": "elara", "set": {"injury": "burned left hand", "stage": "foundation"}}],
  "events": [{"kind": "breakthrough", "slug": "elara", "note": "core cracked in the vault"}],
  "edges": [{"src": "elara", "rel": "allied_with", "dst": "kael"}],
  "learned": [{"character": "elara", "secret": "heir-pact"}],
  "threads": [{"slug": "forged-records", "status": "active", "beat": "..."}],
  "plants": [],
  "payoffs": []
}
```

## Tools

- `brief_chapter` / `ingest_chapter` / `auditor_prompt` / `audit_chapter`
- `get_entity` / `query_canon` / `path` / `status` / `list_beats`
- `set_arc` / `list_arcs`
- `visualize` / `set_truth` (showrunner only)
