PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS entities (
  id INTEGER PRIMARY KEY,
  slug TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  type TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active',
  aliases_json TEXT NOT NULL DEFAULT '[]',
  attrs_json TEXT NOT NULL DEFAULT '{}',
  summary TEXT NOT NULL DEFAULT '',
  first_chapter INTEGER,
  last_seen_chapter INTEGER,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS aliases (
  alias_norm TEXT NOT NULL,
  entity_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  alias_raw TEXT NOT NULL,
  PRIMARY KEY (alias_norm, entity_id)
);

CREATE INDEX IF NOT EXISTS idx_aliases_norm ON aliases(alias_norm);

CREATE TABLE IF NOT EXISTS edges (
  id INTEGER PRIMARY KEY,
  src_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  dst_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  rel TEXT NOT NULL,
  from_chapter INTEGER NOT NULL,
  to_chapter INTEGER,
  evidence_chapter INTEGER NOT NULL,
  note TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_edges_src ON edges(src_id, rel);
CREATE INDEX IF NOT EXISTS idx_edges_dst ON edges(dst_id);
CREATE INDEX IF NOT EXISTS idx_edges_open ON edges(src_id, rel, to_chapter);

CREATE TABLE IF NOT EXISTS knowledge (
  character_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  secret_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  known_since_chapter INTEGER NOT NULL,
  PRIMARY KEY (character_id, secret_id)
);

CREATE TABLE IF NOT EXISTS chapters (
  n INTEGER PRIMARY KEY,
  path TEXT NOT NULL,
  title TEXT NOT NULL DEFAULT '',
  pov TEXT,
  location TEXT,
  present_json TEXT NOT NULL DEFAULT '[]',
  summary TEXT NOT NULL DEFAULT '',
  word_count INTEGER NOT NULL DEFAULT 0,
  content_hash TEXT NOT NULL DEFAULT '',
  ingested_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS plants (
  slug TEXT PRIMARY KEY,
  kind TEXT NOT NULL DEFAULT 'chekhov',
  planted_chapter INTEGER NOT NULL,
  due_after INTEGER NOT NULL DEFAULT 8,
  paid_chapter INTEGER,
  note TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS flags (
  id INTEGER PRIMARY KEY,
  type TEXT NOT NULL,
  severity TEXT NOT NULL DEFAULT 'major',
  chapter INTEGER,
  body TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open',
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS mentions (
  chapter INTEGER NOT NULL,
  entity_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  PRIMARY KEY (chapter, entity_id)
);

CREATE TABLE IF NOT EXISTS beats (
  id INTEGER PRIMARY KEY,
  chapter INTEGER NOT NULL,
  kind TEXT NOT NULL,
  entity_slug TEXT,
  text TEXT NOT NULL,
  sort INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_beats_chapter ON beats(chapter, sort);

CREATE TABLE IF NOT EXISTS arcs (
  id INTEGER PRIMARY KEY,
  title TEXT NOT NULL,
  start_chapter INTEGER,
  target_end_chapter INTEGER,
  climax_chapter INTEGER,
  status TEXT NOT NULL DEFAULT 'active',
  summary TEXT NOT NULL DEFAULT ''
);
