"""Seed a short serial so the desk has something to show."""

from __future__ import annotations

import shutil
from pathlib import Path

from storycanon.db import Canon
from storycanon.ingest import ingest_chapter
from storycanon.viz import open_graph, write_graph

STEPS = [
    {
        "chapter": 1,
        "pov": "elara",
        "title": "The Letter",
        "summary": "Elara finds a forged founding letter in the imperial archives.",
        "present": ["elara"],
        "location": "archives",
        "new_entities": [
            {"name": "Elara", "type": "character", "attrs": {"voice": "dry", "goal": "prove the forgery"}},
            {"name": "Archives", "type": "location"},
            {"name": "Kael", "type": "character"},
            {"name": "Black Fort", "type": "location"},
            {"name": "Vault City", "type": "location"},
            {"name": "Voss", "type": "character"},
            {"name": "Heir Pact", "type": "secret"},
            {"name": "Forged Records", "type": "thread", "summary": "The empire's founding records are fake."},
        ],
        "threads": [{"slug": "forged-records", "status": "active", "beat": "letter found"}],
        "plants": [{"slug": "forged-letter", "due_after": 5, "note": "the wax seal does not match the year"}],
    },
    {
        "chapter": 2,
        "pov": "elara",
        "title": "The Guard",
        "summary": "Kael hides Elara. They agree to run.",
        "present": ["elara", "kael"],
        "location": "archives",
        "edges": [{"src": "elara", "rel": "allied_with", "dst": "kael"}],
    },
    {
        "chapter": 3,
        "pov": "elara",
        "title": "Dusk at the Fort",
        "summary": "They reach the Black Fort at dusk.",
        "present": ["elara", "kael"],
        "location": "black-fort",
    },
    {
        "chapter": 4,
        "pov": "elara",
        "title": "The Folio",
        "summary": "Elara learns the heir pact from a hidden folio.",
        "present": ["elara"],
        "location": "black-fort",
        "learned": [{"character": "elara", "secret": "heir-pact"}],
    },
    {
        "chapter": 5,
        "pov": "kael",
        "title": "Covering Fire",
        "summary": "Kael is stabbed covering Elara's escape.",
        "present": ["elara", "kael"],
        "location": "black-fort",
        "updates": [{"slug": "kael", "set": {"injury": "stabbed side"}}],
    },
    {
        "chapter": 6,
        "pov": "elara",
        "title": "The Ride",
        "summary": "Elara leaves the wounded Kael and rides for Vault City.",
        "present": ["elara"],
        "location": "vault-city",
    },
    {
        "chapter": 7,
        "pov": "elara",
        "title": "The Smile",
        "summary": "Voss intercepts her in the market and smiles like a knife.",
        "present": ["elara", "voss"],
        "location": "vault-city",
    },
    {
        "chapter": 8,
        "pov": "elara",
        "title": "The Vault Door",
        "summary": "Elara reaches the vault door. The seal on the letter matches the lock.",
        "present": ["elara"],
        "location": "vault-city",
        "threads": [{"slug": "forged-records", "beat": "vault door, seal matches"}],
    },
]


def seed_demo(root: Path, *, reset: bool = True) -> Canon:
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    if reset:
        dbdir = root / ".storycanon"
        if dbdir.exists():
            shutil.rmtree(dbdir)
        toml = root / "storycanon.toml"
        if toml.exists():
            toml.unlink()
    canon = Canon(root)
    if not canon.exists():
        canon.init_project(
            "A disgraced archivist discovers the empire's founding records were forged.",
            "The Forged Archive",
        )
    for delta in STEPS:
        result = ingest_chapter(canon, delta, force=True)
        if not result.ok:
            raise RuntimeError(result.render())
    write_graph(canon)
    return canon


def run_demo(root: Path | None = None, *, open_browser: bool = True) -> Path:
    if root is None:
        root = Path.cwd() / "storycanon-demo"
    canon = seed_demo(root)
    path = canon.canon_dir / "graph.html"
    if open_browser:
        open_graph(path)
    return path
