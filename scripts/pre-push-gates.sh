#!/usr/bin/env bash
# Council of AI agent plugin — repository safety suite (pre-push).
#
# WHY THIS EXISTS. A public plugin repo is a distribution channel: anyone can
# `npx -y csoai-agent-plugin install` it. The bytes that leave this repo are
# therefore public claims, and they get checked before they go, not twelve
# minutes into a deploy like the four failures this estate had on 2026-09-03.
#
# It runs the same five checks on every push:
#
#   secrets-gate    no credential material in tracked files
#   json-gate       every tracked JSON file parses, no duplicate keys
#   manifest-gate   the MiniMax plugin manifest satisfies the V1 contract
#   price-gate      no public price (CSOAI doctrine: no published prices)
#   doctrine-gate   no certification claim, no self-scoring, no retracted claim
#   packaging-gate  no junk, no lockfile secrets, licence and version present
#
# Install as a pre-push hook:
#     ln -sf ../../scripts/pre-push-gates.sh .git/hooks/pre-push
#
# Self-test (proves the gate can still go red):
#     bash scripts/pre-push-gates.sh --selftest
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 1

fail=0
note_fail() { echo "  ✖ $1"; fail=1; }

# ---------------------------------------------------------------- selftest --
# A gate that has never gone red proves nothing about the tree it just passed.
if [ "${1:-}" = "--selftest" ]; then
  selftest_fail=0
  sample='GITHUB_TOKEN=ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ012345'
  if printf '%s' "$sample" | grep -Eq '(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}'; then
    echo "  ✓ secrets-gate pattern still fires"
  else
    echo "  ✖ secrets-gate pattern is dead"; selftest_fail=1
  fi
  if printf '%s' '"$49.00"' | grep -Eq '[$€£][[:space:]]?[0-9]+(\.[0-9]{2})?'; then
    echo "  ✓ price-gate pattern still fires"
  else
    echo "  ✖ price-gate pattern is dead"; selftest_fail=1
  fi
  if printf '%s' 'CSOAI certified this model' | grep -Eqi 'csoai[- ]certified|certified by csoai'; then
    echo "  ✓ doctrine-gate pattern still fires"
  else
    echo "  ✖ doctrine-gate pattern is dead"; selftest_fail=1
  fi
  exit $selftest_fail
fi

echo "pre-push: Council of AI agent plugin safety suite …"

TRACKED=$(git ls-files)
if [ -z "$TRACKED" ]; then
  echo "  ✖ no tracked files — refusing push"; exit 1
fi

# ------------------------------------------------------------- secrets-gate --
# The gate's own pattern strings are excluded from its content scans: a gate
# that reads its own regex is a gate that can never pass. Everything else in
# the repo is scanned.
SCAN_EXCLUDE=':!scripts/pre-push-gates.sh'
secret_hits=$(git grep -I -n -E \
  '(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|npm_[A-Za-z0-9]{30,}|sk-[A-Za-z0-9]{24,}|AKIA[0-9A-Z]{16}|xox[baprs]-[A-Za-z0-9-]{10,}|-----BEGIN [A-Z ]*PRIVATE KEY-----' \
  -- . "$SCAN_EXCLUDE" 2>/dev/null | head -10)
if [ -n "$secret_hits" ]; then
  echo "  ✖ secrets-gate: credential material is in tracked files:"
  printf '%s\n' "$secret_hits" | sed 's/^/      /'
  fail=1
else
  echo "  ✓ secrets-gate clean"
fi

# ---------------------------------------------------------------- json-gate --
json_fail=0
for f in $TRACKED; do
  case "$f" in
    *.json)
      if ! python3 -c '
import json,sys
def hook(pairs):
    seen={}
    for k,v in pairs:
        if k in seen: raise SystemExit("duplicate key: "+k)
        seen[k]=v
    return seen
raw=open(sys.argv[1],"rb").read()
if raw.startswith(b"\xef\xbb\xbf"): raise SystemExit("BOM not allowed")
json.loads(raw.decode("utf-8"), object_pairs_hook=hook)
' "$f" 2>/tmp/csoai-json-gate.err; then
        echo "  ✖ json-gate: $f — $(head -1 /tmp/csoai-json-gate.err)"; json_fail=1; fail=1
      fi
      ;;
  esac
done
[ "$json_fail" -eq 0 ] && echo "  ✓ json-gate clean"

# ----------------------------------------------------------- manifest-gate --
manifest_out=$(python3 - <<'PY' 2>&1
import json, os, sys, re

root = os.getcwd()
errors = []
manifest_path = os.path.join(root, "canonical", ".minimax-plugin", "plugin.json")
if not os.path.isfile(manifest_path):
    print("MISSING canonical/.minimax-plugin/plugin.json"); sys.exit(0)

raw = open(manifest_path, "rb").read()
if raw.startswith(b"\xef\xbb\xbf"):
    errors.append("manifest has a BOM")
m = json.loads(raw.decode("utf-8"))

required = ["schemaVersion","name","version","description","author","icon","category",
            "exampleQueries","apps","mcpServers","skills"]
for key in required:
    if key not in m:
        errors.append(f"missing required field: {key}")
if m.get("schemaVersion") != 1:
    errors.append("schemaVersion must be 1")
if not re.fullmatch(r"[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*", str(m.get("name",""))):
    errors.append("name does not match the required pattern")
if not re.fullmatch(r"\d+\.\d+\.\d+", str(m.get("version",""))):
    errors.append("version is not SemVer")
categories = ["Office","Studio","Design & Sites","Code","Business","Sales","Productivity",
              "Science & Healthcare","Education","Other"]
if m.get("category") not in categories:
    errors.append("category is not one of the allowed values")
if m.get("apps") != []:
    errors.append("apps must be an empty array")
queries = m.get("exampleQueries")
if not isinstance(queries, list) or not queries or not all(isinstance(q,str) and q.strip() for q in queries):
    errors.append("exampleQueries must be a non-empty list of non-empty strings")
if not isinstance(m.get("mcpServers"), list) and not isinstance(m.get("skills"), list):
    errors.append("mcpServers and skills must be arrays")
for cap in ("mcpServers","skills","agents","hooks"):
    val = m.get(cap, [])
    if not isinstance(val, list):
        errors.append(f"{cap} must be an array")
        continue
    for rel in val:
        if rel.startswith("/") or ".." in rel or "\\" in rel:
            errors.append(f"{cap} path is not package-relative: {rel}")
            continue
        if not os.path.isfile(os.path.join(root, "canonical", rel)):
            errors.append(f"{cap} references a missing file: {rel}")
for icon_key in ("icon","darkIcon"):
    rel = m.get(icon_key)
    if not rel: continue
    p = os.path.join(root, "canonical", rel)
    if not os.path.isfile(p):
        errors.append(f"{icon_key} file missing: {rel}"); continue
    if not open(p,"rb").read(8).startswith(b"\x89PNG\r\n\x1a\n"):
        errors.append(f"{icon_key} is not a PNG: {rel}")
# skill frontmatter name must equal the directory name
for rel in m.get("skills", []):
    p = os.path.join(root, "canonical", rel)
    if not os.path.isfile(p): continue
    text = open(p, encoding="utf-8").read()
    mm = re.match(r"^---\n(.*?)\n---", text, re.S)
    if not mm:
        errors.append(f"skill has no frontmatter: {rel}"); continue
    name = re.search(r"^name:\s*(.+)$", mm.group(1), re.M)
    desc = re.search(r"^description:\s*(.+)$", mm.group(1), re.M)
    expected = rel.split("/")[1]
    if not name or name.group(1).strip() != expected:
        errors.append(f"skill name does not match its directory: {rel}")
    if not desc or not desc.group(1).strip():
        errors.append(f"skill description is empty: {rel}")
# agents, if declared, must match the documented pattern
for rel in m.get("agents", []):
    if not re.fullmatch(r"agents/[a-z][a-z0-9_-]*\.md", rel):
        errors.append(f"agent path is invalid: {rel}")

for e in errors:
    print(e)
PY
)
if [ -n "$manifest_out" ]; then
  echo "  ✖ manifest-gate: the plugin manifest is not V1-valid:"
  printf '%s\n' "$manifest_out" | sed 's/^/      /'
  fail=1
else
  echo "  ✓ manifest-gate clean"
fi

# --------------------------------------------------------------- price-gate --
# Doctrine: no published prices. The board is free, forever; a price in a public
# JSON file is the machine surface nobody reads before it becomes a claim.
price_hits=$(git grep -I -n -E '[$€£][[:space:]]?[0-9]+(\.[0-9]{2})?( |$|,|\.|"|;)' -- \
  '*.json' '*.md' '*.mjs' '*.py' "$SCAN_EXCLUDE" 2>/dev/null | grep -v -E '(price|amount|cost)[^ ]* *[=:][^ ]* *["'"'"']?0(\.0+)?["'"'"']?$' | head -10)
if [ -n "$price_hits" ]; then
  echo "  ✖ price-gate: a published price is in a tracked file:"
  printf '%s\n' "$price_hits" | sed 's/^/      /'
  fail=1
else
  echo "  ✓ price-gate clean"
fi

# ------------------------------------------------------------ doctrine-gate --
# We measure; we never certify. We never score our own products. DR-0007 was
# self-retracted and must not come back.
doctrine_hits=$(git grep -I -n -i -E \
  'csoai[- ]certified|certified by csoai|guaranteed accuracy|100% accurate|byzantine consensus|33-agent' \
  -- . "$SCAN_EXCLUDE" 2>/dev/null | head -10)
if [ -n "$doctrine_hits" ]; then
  echo "  ✖ doctrine-gate: a forbidden claim is in a tracked file:"
  printf '%s\n' "$doctrine_hits" | sed 's/^/      /'
  fail=1
else
  echo "  ✓ doctrine-gate clean"
fi

# ---------------------------------------------------------- packaging-gate --
packaging_fail=0
for junk in $(git ls-files | grep -E '(^|/)\.DS_Store$|(^|/)node_modules/|\.pyc$|(^|/)\.env$|\.pem$|(^|/)id_(rsa|ed25519)$' | head -10); do
  echo "  ✖ packaging-gate: junk or secret-shaped file is tracked: $junk"; packaging_fail=1; fail=1
done
[ -f LICENSE ] || { echo "  ✖ packaging-gate: LICENSE is missing"; packaging_fail=1; fail=1; }
[ -f README.md ] || { echo "  ✖ packaging-gate: README.md is missing"; packaging_fail=1; fail=1; }
# The installer must install the PACKAGE (canonical/), not the repository root, and it must
# never delete a user's plugin directory to do it.
if [ -f install.sh ]; then
  grep -q 'canonical' install.sh || { echo "  ✖ packaging-gate: install.sh does not install the canonical/ package"; packaging_fail=1; fail=1; }
  if grep -v '^[[:space:]]*#' install.sh | grep -q -- '--delete'; then
    echo "  ✖ packaging-gate: install.sh uses a destructive delete against a user's plugin directory"
    packaging_fail=1; fail=1
  fi
  [ -x install.sh ] || { echo "  ✖ packaging-gate: install.sh is not executable"; packaging_fail=1; fail=1; }
fi
pkg_version=$(python3 -c 'import json;print(json.load(open("package.json")).get("version",""))' 2>/dev/null)
man_version=$(python3 -c 'import json;print(json.load(open("canonical/.minimax-plugin/plugin.json")).get("version",""))' 2>/dev/null)
if [ "$pkg_version" != "$man_version" ]; then
  echo "  ✖ packaging-gate: package.json version ($pkg_version) and the plugin manifest version ($man_version) disagree"
  packaging_fail=1; fail=1
fi
[ "$packaging_fail" -eq 0 ] && echo "  ✓ packaging-gate clean"

if [ "$fail" -ne 0 ]; then
  echo
  echo "  Push blocked. These are the checks that make a public package safe to run."
  exit 1
fi
echo "  ✓ secrets-gate + json-gate + manifest-gate + price-gate + doctrine-gate + packaging-gate clean"
exit 0
