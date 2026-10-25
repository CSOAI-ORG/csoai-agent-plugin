#!/usr/bin/env bash
# Install and verify the Council of AI MiniMax Code plugin.
#
# The source of truth lives HERE, in the CSOAI estate — not in the runtime-managed
# ~/.minimax/plugins/ directory. The runtime's local-plugin rescan has been observed to prune a
# package it does not recognise, and a prune must never be able to destroy the work. Install copies
# the source in; --verify re-reads what is actually installed.
#
# Usage:  ./install.sh          install (idempotent)
#         ./install.sh --verify verify the installed package without changing it
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="${MINIMAX_PLUGIN_HOME:-$HOME/.minimax/plugins}/council-of-ai"

verify() {
  local fail=0
  echo "verifying $DEST"

  for f in .minimax-plugin/plugin.json council-of-ai.mcp.json hooks/hooks.json icon.png icon-dark.png; do
    if [ -f "$DEST/$f" ]; then echo "  ok   $f"; else echo "  MISS $f"; fail=1; fi
  done

  APP_VERSION=$(/usr/bin/defaults read "/Applications/MiniMax Code.app/Contents/Info.plist" CFBundleShortVersionString 2>/dev/null || echo "unknown")
  if grep -q '"agents"' "$DEST/.minimax-plugin/plugin.json"; then
    case "$APP_VERSION" in
      3.1.*)
        echo "  WARN manifest declares 'agents' but MiniMax Code ${APP_VERSION} rejects that field"
        echo "       (MANIFEST_SCHEMA_INVALID -> the runtime DELETES this package). Remove the"
        echo "       'agents' field unless this runtime is known to tolerate it."
        ;;
    esac
  fi

  python3 - "$DEST" <<'PY'
import json, os, re, sys
dest = sys.argv[1]
fail = 0
try:
    manifest = json.load(open(os.path.join(dest, ".minimax-plugin/plugin.json"), encoding="utf-8"))
except Exception as error:
    print(f"  MISS manifest unreadable: {error}")
    sys.exit(1)

required = ["schemaVersion", "name", "version", "description", "author", "icon",
            "category", "exampleQueries", "apps", "mcpServers", "skills"]
for key in required:
    if key not in manifest:
        print(f"  MISS manifest field '{key}'")
        fail = 1
if manifest.get("schemaVersion") != 1:
    print("  MISS schemaVersion must be 1"); fail = 1
if not re.match(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$", manifest.get("name", "")):
    print("  MISS plugin name pattern"); fail = 1
if not re.match(r"^\d+\.\d+\.\d+", manifest.get("version", "")):
    print("  MISS version is not SemVer"); fail = 1
if manifest.get("apps") != []:
    print("  MISS apps must be []"); fail = 1
if not manifest.get("skills") and not manifest.get("mcpServers") \
        and not manifest.get("agents") and not manifest.get("hooks"):
    print("  MISS no effective capability"); fail = 1

for ref in manifest.get("skills", []) + manifest.get("agents", []) + manifest.get("hooks", []) + manifest.get("mcpServers", []):
    if not os.path.isfile(os.path.join(dest, ref)):
        print(f"  MISS referenced file {ref}")
        fail = 1

for ref in manifest.get("skills", []):
    path = os.path.join(dest, ref)
    text = open(path, encoding="utf-8").read()
    match = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not match:
        print(f"  MISS frontmatter in {ref}"); fail = 1; continue
    name = re.search(r"^name:\s*(.+)$", match.group(1), re.M)
    desc = re.search(r"^description:\s*(.+)$", match.group(1), re.M)
    stem = os.path.basename(os.path.dirname(ref))
    if not name or name.group(1).strip() != stem:
        print(f"  MISS skill name != dir in {ref}"); fail = 1
    if not desc or not desc.group(1).strip():
        print(f"  MISS skill description empty in {ref}"); fail = 1

for ref in manifest.get("agents", []):
    if not re.match(r"^agents/[a-z][a-z0-9_-]*\.md$", ref):
        print(f"  MISS agent path pattern {ref}"); fail = 1
    path = os.path.join(dest, ref)
    text = open(path, encoding="utf-8").read()
    match = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not match:
        print(f"  MISS frontmatter in {ref}"); fail = 1; continue
    name = re.search(r"^name:\s*(.+)$", match.group(1), re.M)
    stem = os.path.basename(ref)[:-3]
    if not name or name.group(1).strip() != stem:
        print(f"  MISS agent name != file in {ref}"); fail = 1
    if "task" in (re.search(r"^tools:\s*\[(.*?)\]", match.group(1), re.M) or type("", (), {"group": lambda self, i: ""})()).group(1):
        print(f"  MISS agent must not list 'task' in {ref}"); fail = 1

for ref in manifest.get("mcpServers", []):
    path = os.path.join(dest, ref)
    payload = json.load(open(path, encoding="utf-8"))
    if payload.get("schemaVersion") != 1:
        print(f"  MISS mcp schemaVersion in {ref}"); fail = 1
    servers = payload.get("mcpServers") or {}
    if not servers:
        print(f"  MISS empty mcpServers in {ref}"); fail = 1
    for name, server in servers.items():
        if not re.match(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$", name):
            print(f"  MISS mcp server name pattern: {name}"); fail = 1
        if server.get("type") not in ("stdio", "streamable-http", "sse"):
            print(f"  MISS mcp transport for {name}"); fail = 1
        if server.get("type") == "stdio" and "/" in server.get("command", ""):
            print(f"  MISS stdio command must be PATH-resolved: {name}"); fail = 1
        if server.get("type") in ("streamable-http", "sse") and not server.get("url", "").startswith("https://"):
            print(f"  MISS remote mcp url must be https: {name}"); fail = 1
        for banned in ("auth", "oauth", "headers"):
            if banned in server:
                print(f"  MISS unsupported mcp field '{banned}' on {name}"); fail = 1

print("  manifest checks:", "FAIL" if fail else "PASS")
sys.exit(1 if fail else 0)
PY
  return $fail
}

if [ "${1:-}" = "--verify" ]; then
  verify
  exit $?
fi

echo "installing $SRC -> $DEST"
mkdir -p "$DEST"
rsync -a --delete "$SRC/" "$DEST/"
verify
echo
echo "installed. The runtime rescans local plugins automatically."
echo "source of truth: $SRC"
