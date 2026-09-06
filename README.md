# StoryCanon

Local continuity engine so AI agents can write **1000+ chapter** novels without losing the plot.

LLMs already know how to write. They fail at *state*: names, who knows what, open threads, Chekhov guns, where everyone is. Gemini was honest — around chapter 40, chat memory collapses. StoryCanon is the memory.

Inspired by [Graphify](https://github.com/Graphify-Labs/graphify) (query a graph instead of grepping a repo), but built for fiction:

| Graphify | StoryCanon |
|---|---|
| AST-extracted code graph | SQLite **canon** of what is true *now* |
| `query` / `path` | same, plus **`brief`** and **`ingest`** |
| Token-budgeted subgraph | Token-budgeted **chapter briefing** |
| `graph.html` | **Story desk**: graph, timeline, beats, cast |

This does **not** write the novel and does **not** make the prose “million-dollar.” It makes long-horizon *continuity* possible. You (or Gemini in Antigravity, or an OpenRouter agent) still write the chapters.

## Write loop

```
brief(n)  →  write chapters/NNNN.md  →  ingest(n, delta)  →  OK or reject
```

Chapter N+1 is briefed from the updated canon. The model never rereads chapters 1…N.

## Install into a novel project

**Skill** (Gemini, Antigravity, Cursor, Claude, Codex):

```bash
npx skills add SHREE167/storycanon
```

**npm library** (copies the skill, wires MCP, tries to install the Python engine):

```bash
npm install github:SHREE167/storycanon
```

**Engine** (required once — Python 3.11+):

```bash
pip install "git+https://github.com/SHREE167/storycanon.git"
```

Then in the novel folder:

```bash
npx storycanon init "A disgraced archivist finds the empire's founding records were forged." --title "The Forged Archive"
npx storycanon install
```

That writes `.agents/mcp_config.json`, `.gemini/settings.json`, `.agents/skills/storycanon/SKILL.md`, and `AGENTS.md`.

Open that folder in Antigravity / Gemini CLI. Ask: *use StoryCanon; brief chapter 1, write it, ingest.*

PowerShell: `storycanon brief 2` — do not prefix `/`.

Dev install from a clone:

```bash
pip install -e ".[dev]"
pytest -q
```

## Commands

```powershell
storycanon brief 2
storycanon ingest 2 .\chapters\0002.md --delta delta.json
storycanon status
storycanon get Elara
storycanon query "who knows heir-pact"
storycanon path Elara "Black Fort"
storycanon set-truth kael --attrs "{\"injury\":\"broken rib\"}"
storycanon export-bible
storycanon beats
storycanon viz --open
storycanon demo --open
storycanon tools-json
```

## Delta

Every ingest needs a JSON object. Minimum: `chapter`, `summary`. Real chapters should also send `pov`, `present`, `location`, `updates`, `threads`.

See `skills/storycanon/SKILL.md` for the full shape.

## Story desk

After any ingest (or `storycanon viz --open`) you get a local HTML desk:

- **Graph** — force layout, chapter slider (“as of ch. N”), path trace, past edges dashed
- **Timeline** — every chapter with POV, place, and beat chips
- **Beats** — planted / due Chekhov / active threads / paid off, plus the full beat list
- **Cast** — characters and places as cards
- **Threads** — each plotline with the beats that moved it

```powershell
storycanon demo --open
```

## OpenRouter / custom agents

If your agent talks OpenAI-style tools (OpenRouter, etc.) and not MCP, load `.storycanon/tools.json` and implement each function as a subprocess:

```powershell
storycanon brief 12 --json
storycanon ingest 12 .\chapters\0012.md --delta-json "{...}"
```

## Tests

```powershell
python -m pytest -q
```
