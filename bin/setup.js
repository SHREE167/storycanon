#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const pkgRoot = path.resolve(__dirname, "..");
const projectRoot = process.env.INIT_CWD || process.cwd();

if (path.resolve(projectRoot) === pkgRoot) {
  console.log("storycanon: skipped project wiring (installing the engine repo itself).");
  process.exit(0);
}

function copyDir(src, dest) {
  fs.mkdirSync(dest, { recursive: true });
  for (const name of fs.readdirSync(src)) {
    const from = path.join(src, name);
    const to = path.join(dest, name);
    const st = fs.statSync(from);
    if (st.isDirectory()) copyDir(from, to);
    else fs.copyFileSync(from, to);
  }
}

function writeJson(file, data) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, JSON.stringify(data, null, 2) + "\n", "utf8");
}

function mergeMcp(file, command, args) {
  let cfg = {};
  if (fs.existsSync(file)) {
    try {
      cfg = JSON.parse(fs.readFileSync(file, "utf8"));
    } catch {
      cfg = {};
    }
  }
  cfg.mcpServers = cfg.mcpServers || {};
  cfg.mcpServers.storycanon = { command, args };
  writeJson(file, cfg);
}

const skillSrc = path.join(pkgRoot, "skills", "storycanon");
const skillDest = path.join(projectRoot, ".agents", "skills", "storycanon");
if (fs.existsSync(skillSrc)) {
  copyDir(skillSrc, skillDest);
  console.log("storycanon: skill -> " + skillDest);
}

const npxCmd = process.platform === "win32" ? "npx.cmd" : "npx";
mergeMcp(path.join(projectRoot, ".agents", "mcp_config.json"), npxCmd, ["storycanon", "mcp"]);
mergeMcp(path.join(projectRoot, ".gemini", "settings.json"), npxCmd, ["storycanon", "mcp"]);

const agents = path.join(projectRoot, "AGENTS.md");
const block =
  "\n## StoryCanon\n\n" +
  "Use the StoryCanon skill and MCP tools. Brief before writing a chapter; ingest after. " +
  "A chapter is not canon until ingest returns OK.\n";
if (fs.existsSync(agents)) {
  const text = fs.readFileSync(agents, "utf8");
  if (!text.includes("StoryCanon")) fs.appendFileSync(agents, block);
} else {
  fs.writeFileSync(agents, "# Agents\n" + block, "utf8");
}

const py = process.platform === "win32" ? "python" : "python3";
const pip = spawnSync(py, ["-m", "pip", "install", pkgRoot], {
  encoding: "utf8",
  timeout: 120000,
  windowsHide: true,
});
if (pip.status === 0) {
  console.log("storycanon: Python engine installed.");
} else {
  console.log(
    "storycanon: skill and MCP config are in place.\n" +
      "Install the engine with:\n" +
      "  pip install \"" + pkgRoot + "\"\n" +
      "  or: pip install \"git+https://github.com/SHREE167/storycanon.git\""
  );
}

console.log("storycanon: ready. In this folder run `npx storycanon init \"your premise\"` then open your agent.");
