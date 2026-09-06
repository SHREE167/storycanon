#!/usr/bin/env node
"use strict";

const { spawn, spawnSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const pkgRoot = path.resolve(__dirname, "..");
const isWin = process.platform === "win32";

function exists(p) {
  try {
    return fs.existsSync(p);
  } catch {
    return false;
  }
}

function pythonCandidates() {
  const out = [];
  if (process.env.STORYCANON_PYTHON) out.push(process.env.STORYCANON_PYTHON);
  out.push(path.join(pkgRoot, ".venv", isWin ? "Scripts\\python.exe" : "bin/python"));
  out.push(isWin ? "python" : "python3");
  out.push("python");
  return out;
}

function findPython() {
  for (const cmd of pythonCandidates()) {
    const probe = spawnSync(cmd, ["-c", "import storycanon"], {
      encoding: "utf8",
      timeout: 15000,
      windowsHide: true,
    });
    if (probe.status === 0) return cmd;
  }
  for (const cmd of pythonCandidates()) {
    const probe = spawnSync(cmd, ["--version"], {
      encoding: "utf8",
      timeout: 8000,
      windowsHide: true,
    });
    if (probe.status === 0) return cmd;
  }
  return null;
}

const py = findPython();
if (!py) {
  console.error(
    "StoryCanon needs Python 3.11+ with the engine installed.\n" +
      "  pip install \"git+https://github.com/SHREE167/storycanon.git\"\n" +
      "  or:  python -m pip install \"" + pkgRoot + "\""
  );
  process.exit(1);
}

const child = spawn(py, ["-m", "storycanon", ...process.argv.slice(2)], {
  stdio: "inherit",
  cwd: process.env.INIT_CWD || process.cwd(),
  windowsHide: false,
});
child.on("exit", (code, signal) => {
  if (signal) process.kill(process.pid, signal);
  process.exit(code == null ? 1 : code);
});
