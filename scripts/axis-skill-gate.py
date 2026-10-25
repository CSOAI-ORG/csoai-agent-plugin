#!/usr/bin/env python3
"""axis-skill-gate — one axis, one door, and no door without an axis.

WHAT THIS PROVES. The plugin ships a generated skill per GSPC board axis. This gate is what
stops that from rotting into sprawl:

  1. every axis in the index has exactly one skill directory, and it exists;
  2. every `gspc-axis-*` directory belongs to an axis in the index — no orphans;
  3. the counts agree: index rows == skill directories == axis_count;
  4. each skill names its axis (frontmatter name, description, body) and teaches how to READ
     the axis — including the rule that a remembered number is never a measurement;
  5. each skill points at the live fetch (the MCP tool and the board URL), so a skill can
     never become a static copy of a measurement;
  6. the index records the sha256 of the board snapshot the skills were generated from.

It reads the committed index, so it is offline and deterministic. Run
`python3 scripts/generate-axis-skills.py --live` and re-commit when the board moves.
"""
from __future__ import annotations

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ROOT = os.path.dirname(HERE)
SKILLS = os.path.join(PLUGIN_ROOT, "canonical", "skills")
INDEX = os.path.join(SKILLS, "axis-index.json")
PREFIX = "gspc-axis-"
NEVER_QUOTE = "Never quote a remembered number"


def fail(problems: list, message: str) -> None:
    problems.append(message)


def frontmatter_value(front: str, key: str) -> str:
    match = re.search(rf"^{key}:\s*(.+)$", front, re.M)
    return match.group(1).strip() if match else ""


def main() -> int:
    problems: list = []

    if not os.path.isfile(INDEX):
        print(f"  ✖ axis-skill-gate: {INDEX} is missing — run scripts/generate-axis-skills.py")
        return 1

    with open(INDEX, encoding="utf-8") as handle:
        index = json.load(handle)

    axes = index.get("axes") or []
    if not axes:
        fail(problems, "the index carries no axes")
    if index.get("axis_count") != len(axes):
        fail(problems, f"axis_count {index.get('axis_count')} != {len(axes)} index rows")
    sha = str(index.get("board_sha256") or "")
    if not re.fullmatch(r"[0-9a-f]{64}", sha):
        fail(problems, f"board_sha256 {sha!r} is not a sha256")

    # 1 + 4 + 5: each indexed axis has one skill that names it and teaches how to read it.
    seen_dirs = set()
    for entry in axes:
        axis = str(entry.get("axis") or "")
        skill = str(entry.get("skill") or "")
        if not axis or not skill:
            fail(problems, f"index row without axis/skill: {entry}")
            continue
        if skill != PREFIX + axis:
            fail(problems, f"axis {axis}: skill name {skill} does not follow gspc-axis-<axis>")
        directory = os.path.join(SKILLS, skill)
        seen_dirs.add(skill)
        path = os.path.join(directory, "SKILL.md")
        if not os.path.isfile(path):
            fail(problems, f"axis {axis}: {skill}/SKILL.md is missing")
            continue
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        match = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.S)
        if not match:
            fail(problems, f"axis {axis}: {skill} has no frontmatter")
            continue
        front, body = match.group(1), match.group(2)
        name = frontmatter_value(front, "name")
        if name != skill:
            fail(problems, f"axis {axis}: frontmatter name {name!r} != {skill!r}")
        description = frontmatter_value(front, "description")
        if not description:
            fail(problems, f"axis {axis}: frontmatter description is empty")
        elif axis not in description:
            fail(problems, f"axis {axis}: the description does not name the axis")
        if axis not in body:
            fail(problems, f"axis {axis}: the body never names the axis")
        if NEVER_QUOTE not in body:
            fail(problems, f"axis {axis}: the body does not forbid quoting a remembered number")
        if "get_axis" not in body:
            fail(problems, f"axis {axis}: the body does not point at the get_axis fetch")
        if "councilof.ai/api/gspc" not in body:
            fail(problems, f"axis {axis}: the body does not point at the live board")

    # 2: no orphan skill directory.
    on_disk = {d for d in os.listdir(SKILLS) if os.path.isdir(os.path.join(SKILLS, d)) and d.startswith(PREFIX)}
    for orphan in sorted(on_disk - seen_dirs):
        fail(problems, f"{orphan} is a skill with no axis in the index")
    for missing in sorted(seen_dirs - on_disk):
        fail(problems, f"{missing} is in the index but not on disk")

    # 3: the counts agree.
    if len(on_disk) != len(axes):
        fail(problems, f"{len(on_disk)} skill directories vs {len(axes)} index rows")

    if problems:
        print("  ✖ axis-skill-gate:")
        for problem in problems:
            print(f"      - {problem}")
        return 1

    print(f"  ✓ axis-skill-gate: {len(axes)} axes, one skill each, {sha[:12]}… — no orphans, no stale identity")
    return 0


if __name__ == "__main__":
    sys.exit(main())
