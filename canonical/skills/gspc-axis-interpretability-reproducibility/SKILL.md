---
name: gspc-axis-interpretability-reproducibility
description: Council of AI GSPC axis 'interpretability-reproducibility' — what an interpretability group publishes and whether it can be reproduced; bench pending frozen bank; declared-slot. Use when the user asks about interpretability-reproducibility specifically, or about this axis's leader, n, separation, or how far to trust its number. Free; measurement, never certification.
---

# GSPC axis: interpretability-reproducibility

**What it measures.** what an interpretability group publishes and whether it can be reproduced

**Bench.** pending frozen bank · family subject · kind declared-slot

**Board snapshot.** schema csoai.gspc-axes/0.5 · measured_on endpoint=A100 · local Ollama (board v2) · 3090 pod (jail), date=behavioural axes 2026-08-12 · jail 2026-08-18 · financial-fact axes: see each axis facts_as_of / measurement_time, peritem_sha256=0d8dacfbe7384a5d2f6a83e7455482ab75f935366bbb6e18da61cfdac8890dec

## This file carries identity, never a value

Never quote a remembered number: this file records what the axis IS and HOW to read it. The number, the leader,
the p and the interval are live and must be fetched at the moment you answer. A remembered
accuracy is not a measurement.

## Fetch this axis

MCP `gspc` (declared by this plugin, `https://councilof.ai/mcp`):

```
get_axis  { "axis": "interpretability-reproducibility" }
```

Plain HTTP:

```bash
node "${PLUGIN_ROOT}/scripts/gspc-board.mjs" --axis=interpretability-reproducibility
curl -sS https://councilof.ai/api/gspc      # then read the "interpretability-reproducibility" row
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
