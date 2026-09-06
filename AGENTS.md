# StoryCanon

This repository is the StoryCanon engine (Python CLI + MCP) and the agent skill.

## For a novel project (Gemini, Antigravity, Cursor, Claude, OpenRouter)

Install the skill into that project:

```bash
npx skills add SHREE167/storycanon
```

or as an npm dependency:

```bash
npm install github:SHREE167/storycanon
```

Then install the engine (once per machine):

```bash
pip install "git+https://github.com/SHREE167/storycanon.git"
# or: uv tool install git+https://github.com/SHREE167/storycanon.git
storycanon install
```

Open the novel folder in your agent and say: use StoryCanon; brief, write, ingest. Do not skip ingest.

Skill source of truth: `skills/storycanon/SKILL.md`  
Auditor skill: `skills/storycanon-auditor/SKILL.md` (extracts delta; the drafter does not).

## For this repo (engine development)

- Python 3.11+, `uv sync` / `pip install -e ".[dev]"`
- Tests: `pytest -q`
- MCP: `storycanon mcp`
- Desk: `storycanon viz --open` (on a real novel project, not a bundled sample)

Do not commit `.venv`, `__pycache__`, `node_modules`, or generated `.storycanon/` databases.
