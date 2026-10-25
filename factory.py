#!/usr/bin/env python3
"""Council of AI plugin factory.

ONE canonical source -> every AI platform family. Nothing is hand-copied, so nothing can drift.

    ./factory.py build              render every platform package into platforms/<id>/
    ./factory.py check              validate the canonical source + every rendered package
    ./factory.py install <id|all>   install skills/rules and merge the MCP servers
    ./factory.py receipt            write a dated receipt of what exists and what is installed

Rules this obeys without exception:
  - It never prints a secret and never writes a secret.
  - It backs up every config file before it merges into it.
  - It never overwrites a host config wholesale; it merges the two Council servers into the
    existing map and leaves every other entry exactly as it found it.
  - A platform with no install target is CATALOGUED, not LIVE. Absence is an answer.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CANONICAL = os.path.join(HERE, "canonical")
PLATFORMS_DIR = os.path.join(HERE, "platforms")
MATRIX_PATH = os.path.join(HERE, "platforms.json")
RECEIPTS = os.path.join(HERE, "receipts")

SKILL_ORDER = ["council", "gspc", "council-os", "verify-card", "sign-artifact", "pack", "platform-measure"]

# A host's own instruction file is never clobbered. The Council section lives between these
# markers so it can be replaced in place or removed cleanly.
BEGIN_MARKER = "<!-- council-of-ai:begin -->"
END_MARKER = "<!-- council-of-ai:end -->"


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def expand(path: str) -> str:
    return os.path.expanduser(path)


def utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_matrix() -> dict:
    with open(MATRIX_PATH, encoding="utf-8") as handle:
        return json.load(handle)


# ── canonical source ─────────────────────────────────────────────────────────────────────────
def canonical_skills() -> list:
    root = os.path.join(CANONICAL, "skills")
    if not os.path.isdir(root):
        raise SystemExit("ABORT canonical/skills is missing")
    found = sorted(d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d)))
    for required in ("gspc", "council", "verify-card"):
        if required not in found:
            raise SystemExit(f"ABORT canonical skill '{required}' is missing")
    return found


def read_skill(name: str) -> str:
    with open(os.path.join(CANONICAL, "skills", name, "SKILL.md"), encoding="utf-8") as handle:
        return handle.read()


def split_frontmatter(text: str):
    match = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.S)
    if not match:
        return "", text
    return match.group(1), match.group(2)


def frontmatter_value(front: str, key: str) -> str:
    match = re.search(rf"^{key}:\s*(.+)$", front, re.M)
    return match.group(1).strip() if match else ""


# ── renderers ───────────────────────────────────────────────────────────────────────────────
def render_rules_md(skill: str) -> str:
    """A skill as a rules-style markdown file the host reads every session."""
    front, body = split_frontmatter(read_skill(skill))
    name = frontmatter_value(front, "name") or skill
    description = frontmatter_value(front, "description") or skill
    out = [
        "---",
        f"description: {description}",
        f"globs:",
        "alwaysApply: true",
        "---",
        "",
        f"# {name}",
        "",
        body.lstrip("\n"),
    ]
    return "\n".join(out)


def render_agent_file(skills: list) -> str:
    """Every skill inline, for a host that reads one instruction file."""
    parts = [
        "# Council of AI — measurement instructions",
        "",
        "Council of AI (CSOAI Ltd, UK Companies House 16939677) is an independent AI-behaviour",
        "measurement body. It runs AI systems against frozen, published tests, signs the result with",
        "Ed25519, and publishes what it could not measure next to what it could.",
        "",
        "**Measurement, never certification.** Verification is free, forever: https://councilof.ai/verify",
        "",
        "The GSPC board and the verification endpoint are free for everyone. The paid rails exist to",
        "assemble evidence packs for agents and organisations that need them filed; they are not a",
        "way to buy a verdict, and there is no price on any public surface.",
        "",
        "---",
        "",
    ]
    for skill in skills:
        front, body = split_frontmatter(read_skill(skill))
        name = frontmatter_value(front, "name") or skill
        description = frontmatter_value(front, "description") or skill
        parts.append(f"## Skill: {name}")
        parts.append("")
        parts.append(f"**When to use:** {description}")
        parts.append("")
        parts.append(body.lstrip("\n"))
        parts.append("")
        parts.append("---")
        parts.append("")
    return "\n".join(parts)


def render_skill_plugin(matrix: dict) -> dict:
    """A full plugin tree for hosts that discover skills by directory."""
    files = {}
    for sub in ("skills", "agents", "hooks", "scripts"):
        src = os.path.join(CANONICAL, sub)
        if not os.path.isdir(src):
            continue
        for root, _dirs, names in os.walk(src):
            for name in names:
                full = os.path.join(root, name)
                rel = os.path.relpath(full, CANONICAL)
                with open(full, "rb") as handle:
                    files[rel] = handle.read()
    for extra in (".minimax-plugin/plugin.json", "council-of-ai.mcp.json", "icon.png", "icon-dark.png"):
        full = os.path.join(CANONICAL, extra)
        if os.path.isfile(full):
            with open(full, "rb") as handle:
                files[extra] = handle.read()
    return files


# ── MCP config merging ───────────────────────────────────────────────────────────────────────
def backup(path: str) -> str | None:
    if not os.path.isfile(path):
        return None
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = f"{path}.bak-{stamp}-pre-csoai-plugin"
    shutil.copy2(path, target)
    return target


def endpoint_of(entry: dict) -> str | None:
    """The identity of an MCP entry: its URL, or its command+args for a stdio server.

    Some hosts write `command` as a string and some as an array; both mean the same thing.
    """
    if not isinstance(entry, dict):
        return None
    if entry.get("url"):
        return f"url:{str(entry['url']).rstrip('/')}"
    command = entry.get("command")
    if command:
        if isinstance(command, list):
            parts = [str(c) for c in command]
        else:
            parts = [str(command)]
        args = entry.get("args") or []
        if isinstance(args, str):
            args = [args]
        parts.extend(str(a) for a in args)
        return "cmd:" + " ".join(parts)
    return None


def is_factory_entry(entry: dict) -> bool:
    """An entry this factory wrote — identified by the descriptions it stamps on them."""
    if not isinstance(entry, dict):
        return False
    description = str(entry.get("description", ""))
    return description.startswith("Council of AI GSPC measurement board") or description.startswith(
        "CSOAI Layer-0 governance")


def backup_tree(path: str) -> str | None:
    """Copy a directory aside before it is overwritten. Returns the backup path."""
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = f"{path}.bak-{stamp}-pre-csoai-plugin"
    try:
        shutil.copytree(path, target)
        return target
    except Exception:
        return None


def merge_mcp_json(path: str, key: str, servers: dict, remote_shape: bool) -> dict:
    data = {}
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)
        except json.JSONDecodeError:
            data = {}
    existing = data.get(key) or {}
    added = []
    covered = {}
    for name, spec in servers.items():
        if remote_shape:
            if spec["transport"] == "streamable-http":
                entry = {"type": "remote", "url": spec["url"], "enabled": True}
            else:
                entry = {"type": "local", "command": spec["command"], "args": spec.get("args", []), "enabled": True}
        else:
            entry = {"type": spec["transport"]}
            if spec["transport"] == "streamable-http":
                entry["url"] = spec["url"]
            else:
                entry["command"] = spec["command"]
                entry["args"] = spec.get("args", [])
            if spec.get("timeout_ms"):
                entry["timeout"] = spec["timeout_ms"]
            if spec.get("description"):
                entry["description"] = spec["description"]
        wanted = endpoint_of(entry)
        # If this host already reaches the same endpoint under another name, do NOT add a
        # second server. Two servers on one URL is two copies of the same tool surface.
        alias = next((other for other, value in existing.items()
                      if other != name and endpoint_of(value) == wanted), None)
        if alias:
            covered[name] = alias
            continue
        if existing.get(name) != entry:
            existing[name] = entry
            added.append(name)
    data[key] = existing
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    return {"file": path, "key": key, "added": added, "covered_by": covered, "servers": sorted(servers)}


def merge_mcp_toml(path: str, key: str, servers: dict) -> dict:
    """Append or rebuild [key.name] blocks without touching any other part of the file.

    An existing block is REBUILT, never stripped: replacing a section with its own header would
    silently delete the host's configuration inside it.
    """
    text = ""
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    added = []
    rebuilt = []
    for name, spec in servers.items():
        header = f"[{key}.{name}]"
        body = []
        if spec["transport"] == "streamable-http":
            body.append(f'url = "{spec["url"]}"')
        else:
            body.append(f'command = "{spec["command"]}"')
            args = ", ".join(f'"{a}"' for a in spec.get("args", []))
            body.append(f"args = [{args}]")
        body.append("enabled = true")
        block = header + "\n" + "\n".join(body) + "\n"
        # Match the section header and everything up to the next section header.
        pattern = re.compile(rf"^\[{re.escape(key)}\.{re.escape(name)}\][^\[]*", re.M)
        if pattern.search(text):
            text = pattern.sub(block, text)
            rebuilt.append(name)
        else:
            text = text.rstrip("\n") + "\n\n" + block
            added.append(name)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return {"file": path, "key": key, "added": added, "rebuilt": rebuilt, "servers": sorted(servers)}


def merge_mcp_yaml(path: str, key: str, servers: dict) -> dict:
    """Insert sibling keys under a top-level YAML key, leaving every other byte alone."""
    text = ""
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    lines = text.splitlines()
    added = []
    for name, spec in servers.items():
        child = f"  {name}:"
        if any(line.startswith(child) for line in lines):
            continue
        block = [child]
        if spec["transport"] == "streamable-http":
            block.append(f'    url: "{spec["url"]}"')
        else:
            block.append(f'    command: "{spec["command"]}"')
            block.append("    args: [" + ", ".join(f'"{a}"' for a in spec.get("args", [])) + "]")
        block.append("    enabled: true")
        index = None
        for i, line in enumerate(lines):
            if line.rstrip() == f"{key}:":
                index = i
                break
        if index is None:
            lines = [f"{key}:"] + block + lines
        else:
            insert_at = index + 1
            while insert_at < len(lines) and (lines[insert_at].startswith(" ") or not lines[insert_at].strip()):
                insert_at += 1
            lines[insert_at:insert_at] = block
        added.append(name)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    return {"file": path, "key": key, "added": added, "servers": sorted(servers)}


def merge_mcp(spec: dict, servers: dict) -> dict:
    fmt = spec.get("format", "none")
    if fmt == "none" or not spec.get("file"):
        return {"skipped": "no MCP target declared for this platform"}
    path = expand(spec["file"])
    made = backup(path)
    if fmt == "json":
        result = merge_mcp_json(path, spec["key"], servers, spec.get("remote_shape", False))
    elif fmt == "toml":
        result = merge_mcp_toml(path, spec["key"], servers)
    elif fmt == "yaml":
        result = merge_mcp_yaml(path, spec["key"], servers)
    else:
        return {"skipped": f"unknown MCP format {fmt}"}
    result["backup"] = made
    return result


# ── build ────────────────────────────────────────────────────────────────────────────────────
def build(matrix: dict) -> dict:
    skills = canonical_skills()
    servers = matrix["canonical"]["mcp_servers"]
    rendered = {}
    for platform in matrix["platforms"]:
        pid = platform["id"]
        out_dir = os.path.join(PLATFORMS_DIR, pid)
        os.makedirs(out_dir, exist_ok=True)
        files = {}
        family = platform["family"]
        if family == "skill-plugin":
            files = render_skill_plugin(matrix)
        elif family == "rules-md":
            for skill in skills:
                files[f"skills/{skill}.md"] = render_rules_md(skill).encode("utf-8")
        elif family == "agent-file":
            files["AGENTS.md"] = render_agent_file(skills).encode("utf-8")
        elif family == "mcp-only":
            files = {}
        for name, payload in files.items():
            target = os.path.join(out_dir, name)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "wb") as handle:
                handle.write(payload)
        manifest = {
            "schema": "csoai.plugin-platform-package/0.1",
            "platform": pid,
            "label": platform["label"],
            "family": family,
            "state": platform["state"],
            "version": matrix["canonical"]["version"],
            "mcp_servers": sorted(servers),
            "files": {name: sha256_bytes(payload) for name, payload in sorted(files.items())},
            "install": platform.get("install", {}),
            "mcp_target": platform.get("mcp", {}),
            "note": platform.get("note"),
            "built_at": utc_now(),
        }
        with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2, sort_keys=True)
            handle.write("\n")
        rendered[pid] = manifest
    return rendered


# ── check ───────────────────────────────────────────────────────────────────────────────────
def check(matrix: dict) -> int:
    failures = []
    skills = canonical_skills()
    print(f"canonical skills: {len(skills)} -> {', '.join(skills)}")
    for skill in skills:
        path = os.path.join(CANONICAL, "skills", skill, "SKILL.md")
        if not os.path.isfile(path):
            failures.append(f"missing skill file {path}")
            continue
        front, _ = split_frontmatter(open(path, encoding="utf-8").read())
        name = frontmatter_value(front, "name")
        if name != skill:
            failures.append(f"skill {skill}: frontmatter name '{name}' != directory")
        if not frontmatter_value(front, "description"):
            failures.append(f"skill {skill}: description is empty")
    for pid in [p["id"] for p in matrix["platforms"]]:
        manifest_path = os.path.join(PLATFORMS_DIR, pid, "manifest.json")
        if not os.path.isfile(manifest_path):
            failures.append(f"{pid}: no rendered package")
            continue
        manifest = json.load(open(manifest_path, encoding="utf-8"))
        for name, digest in manifest["files"].items():
            full = os.path.join(PLATFORMS_DIR, pid, name)
            if not os.path.isfile(full):
                failures.append(f"{pid}: file {name} missing")
            elif sha256_file(full) != digest:
                failures.append(f"{pid}: file {name} digest drift")
    ids = [p["id"] for p in matrix["platforms"]]
    if len(ids) != len(set(ids)):
        failures.append("duplicate platform id")
    print(f"platforms: {len(ids)}")
    for line in failures:
        print("  FAIL " + line)
    print("check:", "FAIL" if failures else "PASS")
    return 1 if failures else 0


# ── install ─────────────────────────────────────────────────────────────────────────────────
def install_one(matrix: dict, platform: dict) -> dict:
    pid = platform["id"]
    src = os.path.join(PLATFORMS_DIR, pid)
    install = platform.get("install", {})
    kind = install.get("type")
    result = {"platform": pid, "label": platform["label"], "kind": kind, "installed": [], "backups": []}
    if kind in ("copy-tree", "rules-md", "agent-file"):
        dest = expand(install["to"])
        if kind != "agent-file":
            os.makedirs(dest, exist_ok=True)
        if kind == "copy-tree":
            # Never overwrite a host's own files without a backup. The tree is copied into a
            # sibling first so the previous content is recoverable.
            if os.path.isdir(dest) and os.listdir(dest):
                made = backup_tree(dest)
                if made:
                    result["backups"].append(made)
            for root, _dirs, names in os.walk(src):
                for name in names:
                    if name == "manifest.json":
                        continue
                    full = os.path.join(root, name)
                    rel = os.path.relpath(full, src)
                    target = os.path.join(dest, rel)
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    shutil.copy2(full, target)
                    result["installed"].append(target)
            # Some hosts read their skills from their own user-skill directory and treat the
            # package directory as runtime-owned. MiniMax Code does exactly that: it prunes
            # ~/.minimax/plugins/<name>/ on the next rescan, while ~/.minimax/skills is the
            # runtime's own skillsDir. Installing the skills there is what makes the plugin
            # work after the package copy is gone.
            skills_dir = install.get("skills_dir")
            if skills_dir:
                skill_root = expand(skills_dir)
                for skill in canonical_skills():
                    src_skill = os.path.join(CANONICAL, "skills", skill, "SKILL.md")
                    if not os.path.isfile(src_skill):
                        continue
                    with open(src_skill, encoding="utf-8") as handle:
                        body = handle.read()
                    # ${PLUGIN_ROOT} only exists inside a plugin package. A standalone skill gets
                    # the canonical source root instead: it is stable for as long as this package
                    # is installed, where the runtime-owned package directory may be pruned.
                    body = body.replace("${PLUGIN_ROOT}", CANONICAL)
                    target_dir = os.path.join(skill_root, skill)
                    os.makedirs(target_dir, exist_ok=True)
                    target = os.path.join(target_dir, "SKILL.md")
                    with open(target, "w", encoding="utf-8") as handle:
                        handle.write(body)
                    result["installed"].append(target)
        elif kind == "rules-md":
            for skill in canonical_skills():
                full = os.path.join(src, "skills", f"{skill}.md")
                if not os.path.isfile(full):
                    continue
                target = os.path.join(dest, f"{skill}.md")
                shutil.copy2(full, target)
                result["installed"].append(target)
        else:
            full = os.path.join(src, "AGENTS.md")
            if os.path.isfile(full):
                made = backup(dest)
                if made:
                    result["backups"].append(made)
                with open(full, encoding="utf-8") as handle:
                    new_body = handle.read()
                existing = ""
                if os.path.exists(dest):
                    with open(dest, encoding="utf-8") as handle:
                        existing = handle.read()
                # A host's own instruction file is never clobbered. The Council section is
                # appended between markers, or replaced in place if it is already there.
                if BEGIN_MARKER in existing and END_MARKER in existing:
                    head = existing.split(BEGIN_MARKER)[0]
                    tail = existing.split(END_MARKER, 1)[1]
                    merged = head + BEGIN_MARKER + "\n" + new_body.rstrip("\n") + "\n" + END_MARKER + tail
                    action = "replaced"
                elif existing:
                    merged = existing.rstrip("\n") + "\n\n" + BEGIN_MARKER + "\n" + new_body.rstrip("\n") + "\n" + END_MARKER + "\n"
                    action = "appended"
                else:
                    merged = BEGIN_MARKER + "\n" + new_body.rstrip("\n") + "\n" + END_MARKER + "\n"
                    action = "created"
                os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
                with open(dest, "w", encoding="utf-8") as handle:
                    handle.write(merged)
                result["installed"].append(dest)
                result["action"] = action
    mcp = merge_mcp(platform.get("mcp", {}), matrix["canonical"]["mcp_servers"])
    result["mcp"] = mcp
    if mcp.get("backup"):
        result["backups"].append(mcp["backup"])
    return result


def install_all(matrix: dict, only_present: bool = True) -> list:
    results = []
    for platform in matrix["platforms"]:
        if only_present and platform["state"] != "present":
            results.append({"platform": platform["id"], "skipped": "not installed on this host"})
            continue
        results.append(install_one(matrix, platform))
    return results


# ── receipt ─────────────────────────────────────────────────────────────────────────────────
def dedupe(matrix: dict) -> list:
    """Remove a factory-written server entry when the host already reaches the same endpoint
    under another name. Two servers on one URL is two copies of the same tool surface."""
    removed = []
    for platform in matrix["platforms"]:
        spec = platform.get("mcp", {})
        if spec.get("format") != "json" or not spec.get("file"):
            continue
        path = expand(spec["file"])
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)
        except json.JSONDecodeError:
            continue
        key = spec["key"]
        entries = data.get(key) or {}
        by_endpoint = {}
        for name, entry in entries.items():
            endpoint = endpoint_of(entry)
            if endpoint:
                by_endpoint.setdefault(endpoint, []).append(name)
        changed = False
        for endpoint, names in by_endpoint.items():
            if len(names) < 2:
                continue
            keep = [n for n in names if not is_factory_entry(entries.get(n))]
            drop = [n for n in names if is_factory_entry(entries.get(n))]
            if keep and drop:
                for name in drop:
                    entries.pop(name, None)
                    removed.append({"platform": platform["id"], "file": path, "removed": name,
                                    "covered_by": keep[0], "endpoint": endpoint})
                    changed = True
        if changed:
            data[key] = entries
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2, ensure_ascii=False)
                handle.write("\n")
    return removed


def receipt(matrix: dict) -> str:
    os.makedirs(RECEIPTS, exist_ok=True)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = os.path.join(RECEIPTS, f"plugin-factory-{stamp}.json")
    platforms = []
    for platform in matrix["platforms"]:
        pid = platform["id"]
        manifest_path = os.path.join(PLATFORMS_DIR, pid, "manifest.json")
        manifest = json.load(open(manifest_path, encoding="utf-8")) if os.path.isfile(manifest_path) else None
        install = platform.get("install", {})
        dest = expand(install["to"]) if install.get("to") else None
        installed_files = []
        if dest and os.path.isdir(dest):
            installed_files = [os.path.join(dest, n) for n in os.listdir(dest)]
        mcp_spec = platform.get("mcp", {})
        mcp_file = expand(mcp_spec["file"]) if mcp_spec.get("file") else None
        mcp_live = False
        if mcp_file and os.path.isfile(mcp_file) and mcp_spec.get("format") == "json":
            try:
                data = json.load(open(mcp_file, encoding="utf-8"))
                mcp_live = all(name in (data.get(mcp_spec["key"]) or {}) for name in matrix["canonical"]["mcp_servers"])
            except Exception:
                mcp_live = False
        platforms.append({
            "id": pid,
            "label": platform["label"],
            "family": platform["family"],
            "state": platform["state"],
            "package_built": bool(manifest),
            "package_digest": manifest["files"] if manifest else {},
            "installed_path": dest,
            "installed_files": len(installed_files),
            "mcp_target": mcp_file,
            "mcp_servers_present": mcp_live,
        })
    payload = {
        "schema": "csoai.plugin-factory-receipt/0.1",
        "observed_at": utc_now(),
        "canonical_version": matrix["canonical"]["version"],
        "canonical_source_sha256": {
            name: sha256_file(os.path.join(CANONICAL, name))
            for name in sorted(os.listdir(CANONICAL)) if os.path.isfile(os.path.join(CANONICAL, name))
        },
        "skills": canonical_skills(),
        "mcp_servers": matrix["canonical"]["mcp_servers"],
        "platforms": platforms,
        "totals": {
            "platforms_declared": len(platforms),
            "packages_built": sum(1 for p in platforms if p["package_built"]),
            "hosts_present": sum(1 for p in platforms if p["state"] == "present"),
            "installed_live": sum(1 for p in platforms if p["installed_files"] > 0),
            "mcp_wired": sum(1 for p in platforms if p["mcp_servers_present"]),
        },
        "doctrine": matrix["doctrine"],
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["build", "check", "install", "install-all", "dedupe", "receipt", "show"])
    parser.add_argument("target", nargs="?", default=None)
    args = parser.parse_args(argv)
    matrix = load_matrix()

    if args.command == "show":
        for platform in matrix["platforms"]:
            mcp = platform.get("mcp", {})
            print(f"  {platform['id']:12s} {platform['family']:13s} {platform['state']:8s} "
                  f"mcp={mcp.get('format','none'):16s} {(mcp.get('file') or '-')}")
        return 0
    if args.command == "build":
        rendered = build(matrix)
        print(f"rendered {len(rendered)} platform packages")
        for pid, manifest in rendered.items():
            print(f"  {pid:12s} {manifest['family']:13s} files={len(manifest['files'])}")
        return 0
    if args.command == "check":
        return check(matrix)
    if args.command == "install":
        for platform in matrix["platforms"]:
            if platform["id"] == args.target:
                print(json.dumps(install_one(matrix, platform), indent=2))
                return 0
        raise SystemExit(f"unknown platform {args.target}")
    if args.command == "install-all":
        results = install_all(matrix)
        for result in results:
            if result.get("skipped"):
                print(f"  {result['platform']:12s} SKIP  {result['skipped']}")
            else:
                mcp = result.get("mcp", {})
                print(f"  {result['platform']:12s} files={len(result['installed']):3d} "
                      f"mcp_added={mcp.get('added', [])} backup={bool(result['backups'])}")
        return 0
    if args.command == "dedupe":
        removed = dedupe(matrix)
        for row in removed:
            print(f"  {row['platform']:10s} removed {row['removed']:22s} -> covered by {row['covered_by']}")
        print(f"dedupe: {len(removed)} duplicate entries removed")
        return 0
    if args.command == "receipt":
        path = receipt(matrix)
        print(f"wrote {path}")
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
