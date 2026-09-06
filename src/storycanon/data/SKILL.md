---
name: storycanon
description: Continuity engine for long novels. Use when writing or editing a webnovel/serial so the agent does not lose characters, threads, or canon. Triggers on chapter, webnovel, story bible, plot continuity, StoryCanon.
---

# StoryCanon

Write against local canon, not chat memory. The engine is the `storycanon` CLI (MCP tools with the same names).

If `storycanon` is missing, install it first:

```text
pip install "git+https://github.com/SHREE167/storycanon.git"
storycanon install
```

or from npm (copies this skill + tries to install the Python engine):

```text
npm install github:SHREE167/storycanon
```

## Loop (every chapter N)

1. `brief_chapter` with N (and pov / present / location if known).
2. Write `chapters/` from that briefing only. Do not reread the whole manuscript.
3. `ingest_chapter` with N, the chapter path, and `delta_json`.
4. Not canon until ingest returns OK. On REJECTED, fix prose or delta and ingest again.

## delta_json

```json
{
  "chapter": 12,
  "pov": "elara",
  "present": ["elara", "kael"],
  "location": "black-fort",
  "title": "The Vault Door",
  "summary": "8-12 lines of what happened.",
  "time_advance": "one night",
  "new_entities": [],
  "updates": [{"slug": "elara", "set": {"injury": "burned left hand"}}],
  "edges": [{"src": "elara", "rel": "allied_with", "dst": "kael"}],
  "learned": [{"character": "elara", "secret": "heir-pact"}],
  "threads": [{"slug": "forged-records", "status": "active", "beat": "..."}],
  "plants": [],
  "payoffs": [],
  "referenced_secrets": []
}
```

`new_entities[].type`: character, location, faction, item, thread, rule, secret, event.

## Tools

- `brief_chapter` — token-capped packet for chapter N
- `ingest_chapter` — commit chapter + delta
- `get_entity` / `query_canon` / `path` / `status` / `list_beats`
- `visualize` — story desk HTML
- `set_truth` — showrunner override only

## Rules

- New names go in `new_entities`. Do not invent a second spelling of an existing person (`get_entity` first).
- POV cannot use a secret they do not know (`learned` or `referenced_secrets`).
- Dead characters are not in `present`.
- Prefer tools over reading `bible/` or old chapters.
