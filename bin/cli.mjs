#!/usr/bin/env node
/**
 * csoai-agent-plugin — install the Council of AI plugin on this machine.
 *
 * It detects which AI platform families are present, renders the right package for each from the
 * one canonical source, and wires the two MCP servers. It never overwrites a host's own files
 * without a backup, and it never adds a second server for an endpoint the host already reaches
 * under another name.
 *
 *   csoai-agent-plugin install          install for every platform found
 *   csoai-agent-plugin install minimax  install for one platform
 *   csoai-agent-plugin list             show what is here and what would be installed
 *
 * Measurement, never certification. The board and verification are free, forever.
 */
import { existsSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const matrix = JSON.parse(readFileSync(join(root, "platforms.json"), "utf8"));
const expand = (p) => p.replace(/^~(?=$|\/)/, homedir());
const present = (p) => existsSync(expand(p));

function detect(platform) {
  const t = platform.install?.to;
  if (!t) return platform.mcp?.file ? present(platform.mcp.file) : false;
  if (platform.family === "agent-file") return existsSync(expand(t).replace(/\/[^/]+$/, ""));
  return existsSync(expand(t));
}

const command = process.argv[2] || "list";
const target = process.argv[3] || null;

if (command === "list") {
  console.log(`Council of AI agent plugin v${matrix.canonical.version} — ${matrix.platforms.length} platform families\n`);
  for (const p of matrix.platforms) {
    console.log(`  ${p.id.padEnd(12)} ${p.family.padEnd(13)} ${p.state.padEnd(9)} ${detect(p) ? "present here" : "not installed"}`);
  }
  console.log(`\n  board   ${matrix.surface.board_url}`);
  console.log(`  verify  ${matrix.surface.verify_url}`);
  console.log(`\n  ${matrix.doctrine[0]}`);
  process.exit(0);
}

if (command === "install") {
  const args = ["install"];
  if (target) args.push(target);
  process.exit(spawnSync(process.execPath, [join(root, "factory.py"), ...args], { stdio: "inherit" }).status ?? 0);
}

console.error(`unknown command: ${command}`);
console.error("usage: csoai-agent-plugin [install [platform]]");
process.exit(2);
