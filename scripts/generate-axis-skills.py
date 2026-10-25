#!/usr/bin/env python3
"""Generate one standalone skill per GSPC axis, from the live board.

WHY THIS EXISTS (2026-10-25). ArtCraft's org is 68 repos and ~245k stars because its unit
is ONE STANDALONE APP PER INCUMBENT PRODUCT — PhotoCraft for Photoshop, WordCraft for Word,
GridCraft for Excel — each clean-room, free, and driven by agents over MCP. Its shared
`craft-libs` and `artcraftx` carry what the apps share, so nothing is duplicated.

Council of AI had the opposite shape: ONE generic tool (`gspc.get_axis(axis)`) for 33 axes,
so an agent had to already know the axis vocabulary to ask a question. This generator
applies the ArtCraft unit: ONE AXIS, ONE DOOR. Each axis becomes its own skill that stands
alone, ships free, and an agent can drive it.

WHAT A SKILL MAY AND MAY NOT CONTAIN. A skill is a static file; a measurement is live. So a
skill carries the axis's IDENTITY (id, task, bench, family, kind) and the METHOD for reading
it — never a remembered number, a remembered leader or a remembered p. It says so in its own
body, and the gate proves it. The numbers are fetched live, every time.

The index this writes is the anti-staleness mechanism: `axis-index.json` records the board
snapshot the skills were generated from, and the gate proves the skills still match it.

Usage:
    python3 scripts/generate-axis-skills.py --board <board.json> [--out canonical/skills]
    python3 scripts/generate-axis-skills.py --live            # fetch GET /api/gspc first
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ROOT = os.path.dirname(HERE)
BOARD_URL = "https://councilof.ai/api/gspc"
DEFAULT_OUT = os.path.join(PLUGIN_ROOT, "canonical", "skills")

# The rule every generated skill must contain, in words. The gate greps for it.
NEVER_QUOTE = "Never quote a remembered number"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch_live() -> tuple[dict, bytes]:
    # A User-Agent is required: the origin answers the default urllib agent with 403.
    request = urllib.request.Request(
        BOARD_URL,
        headers={"accept": "application/json", "user-agent": "csoai-agent-plugin/0.1 (+https://councilof.ai)"},
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        raw = response.read()
    return json.loads(raw.decode("utf-8")), raw


def skill_name(axis_id: str) -> str:
    return "gspc-axis-" + axis_id


def describe(axis: dict) -> str:
    """One-line identity for the catalogue and the frontmatter."""
    task = str(axis.get("task") or "").strip()
    bench = str(axis.get("bench") or "").strip()
    bits = []
    if task:
        bits.append(task if len(task) <= 220 else task[:217].rstrip() + "…")
    if bench:
        bits.append(f"bench {bench}")
    kind = str(axis.get("kind") or "").strip()
    if kind:
        bits.append(kind)
    return "; ".join(bits) if bits else "GSPC axis"


def render(axis: dict, board_meta: dict) -> str:
    axis_id = str(axis.get("axis") or "")
    task = str(axis.get("task") or "").strip() or "The board's task description for this axis is empty."
    bench = str(axis.get("bench") or "").strip() or "—"
    family = str(axis.get("family") or "").strip() or "—"
    kind = str(axis.get("kind") or "").strip() or "—"
    dataset = str(axis.get("dataset") or "").strip()
    dataset_url = str(axis.get("dataset_url") or "").strip()
    schema = str(board_meta.get("schema") or "csoai.gspc-axes/0.5")
    measured_on = board_meta.get("measured_on") or {}
    measured_on_text = ""
    if isinstance(measured_on, dict):
        # Short scalar fields only. The board's own long prose note is not repeated into every
        # axis file — one axis, one identity, not the whole board's commentary 33 times.
        parts = [
            f"{k}={v}"
            for k, v in measured_on.items()
            if isinstance(v, (str, int, float)) and len(str(v)) <= 120
        ]
        if parts:
            measured_on_text = ", ".join(parts)
    elif isinstance(measured_on, str) and len(measured_on) <= 120:
        measured_on_text = measured_on

    front_description = (
        f"Council of AI GSPC axis '{axis_id}' — {describe(axis)}. "
        f"Use when the user asks about {axis_id} specifically, or about this axis's leader, n, "
        f"separation, or how far to trust its number. Free; measurement, never certification."
    )

    body = f"""# GSPC axis: {axis_id}

**What it measures.** {task}

**Bench.** {bench} · family {family} · kind {kind}
"""

    if dataset or dataset_url:
        body += f"\n**Dataset.** {dataset}"
        if dataset_url:
            body += f" — {dataset_url}"
        body += "\n"

    if measured_on_text:
        body += f"\n**Board snapshot.** schema {schema} · measured_on {measured_on_text}\n"

    body += f"""
## This file carries identity, never a value

{NEVER_QUOTE}: this file records what the axis IS and HOW to read it. The number, the leader,
the p and the interval are live and must be fetched at the moment you answer. A remembered
accuracy is not a measurement.

## Fetch this axis

MCP `gspc` (declared by this plugin, `https://councilof.ai/mcp`):

```
get_axis  {{ "axis": "{axis_id}" }}
```

Plain HTTP:

```bash
node "${{PLUGIN_ROOT}}/scripts/gspc-board.mjs" --axis={axis_id}
curl -sS https://councilof.ai/api/gspc      # then read the "{axis_id}" row
```

## Print, in this order

1. **`status`** — MEASURED means a real run stands behind this slot. UNMEASURED is a declared
   slot with no run: it is an answer, never 0 and never a failure.
2. **`n`, `accuracy`, `interval`** — the interval is annotation only; it is not a second vote.
3. **`separation`** — SEPARATED, TIE or UNTESTED. A TIE is not a win. UNTESTED is not a tie.
4. **`mde`** — the axis's own resolution: what difference this axis could have detected at its
   own alpha and power. A reader shown only an accuracy is being asked to trust more than the
   number can bear. Where the board publishes no MDE, say so — never 0.
5. **`separation_sentence`** — quote it verbatim; it carries the test, the threshold and the p.
6. **`measurement_time`** — the observed day AND the precision the source published. No
   midnight timestamp is invented.
7. **`leader_card_state`** — whether the signed card backs the number shown. A card that
   records a DIFFERENT measurement does not back it; say so next to the number.
8. **`fleet_mean`, `mean_harm`, `cvar05_harm`** — the fleet the leader is read against.
9. **`peritem_file_sha256`, `dataset`** — the rows the number was computed from.

## Never

- Never certify, grade or rank anything from this axis. We measure; we do not certify.
- Never score CSOAI's own products on it.
- Never present a point-estimate lead as a measured advantage.
- Never turn an absent field into 0, and never fold a state into another state.
- Never publish a price for anything here. The board and its verification are free, forever.
"""
    return (
        "---\n"
        f"name: {skill_name(axis_id)}\n"
        f"description: {front_description}\n"
        "---\n\n"
        + body
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--board", help="path to a board JSON payload")
    parser.add_argument("--live", action="store_true", help=f"fetch {BOARD_URL}")
    parser.add_argument("--out", default=DEFAULT_OUT)
    args = parser.parse_args()

    if args.live and not args.board:
        board, raw = fetch_live()
        board_sha = sha256_bytes(raw)
    elif args.board:
        with open(args.board, "rb") as handle:
            raw = handle.read()
        board = json.loads(raw.decode("utf-8"))
        board_sha = sha256_bytes(raw)
    else:
        parser.error("one of --board or --live is required")

    axes = board.get("axes") or []
    if not axes:
        raise SystemExit("ABORT the board payload carries no axes")

    out = args.out
    os.makedirs(out, exist_ok=True)
    written = []
    for axis in axes:
        axis_id = str(axis.get("axis") or "").strip()
        if not axis_id:
            continue
        directory = os.path.join(out, skill_name(axis_id))
        os.makedirs(directory, exist_ok=True)
        with open(os.path.join(directory, "SKILL.md"), "w", encoding="utf-8") as handle:
            handle.write(render(axis, board))
        written.append(axis_id)

    index = {
        "schema": "csoai.axis-skills/0.1",
        "source": BOARD_URL,
        "board_schema": board.get("schema"),
        "board_sha256": board_sha,
        "axis_count": len(written),
        "axes": [
            {
                "axis": axis_id,
                "skill": skill_name(axis_id),
                "description": describe(next(a for a in axes if a.get("axis") == axis_id)),
            }
            for axis_id in written
        ],
    }
    with open(os.path.join(out, "axis-index.json"), "w", encoding="utf-8") as handle:
        json.dump(index, handle, indent=2, ensure_ascii=False)
        handle.write("\n")

    print(f"wrote {len(written)} axis skills + axis-index.json under {out}")
    print(f"board sha256 {board_sha}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
