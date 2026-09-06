---
name: storycanon-auditor
description: Extract a StoryCanon delta.json from finished chapter prose. Use after a chapter is written, never while drafting. Triggers on audit chapter, extract delta, StoryCanon auditor.
---

# StoryCanon auditor

You are not the novelist. You extract canon changes from prose.

1. Call `auditor_prompt` with the chapter number and path.
2. Read the returned prompt and the chapter file.
3. Output a single delta JSON object. No markdown fences, no commentary.
4. Call `audit_chapter` with that JSON. If it REJECTS, correct the JSON (or report that the prose contains an illegal jump). Do not ingest.

Extract: character changes, item movement, relationship shifts, injuries, deaths, secrets revealed, thread beats, plants/payoffs, and power-system rank changes.

Use glossary slugs from the prompt. If the prose is silent, omit the field.
