# Council of AI — agent plugin

**Independent AI-behaviour measurement, packaged for AI platforms.**

Council of AI (CSOAI Ltd, UK Companies House 16939667) runs AI systems against frozen, published
tests, signs the result with Ed25519, and publishes what it could **not** measure next to what it
could. Verification is free, forever, and needs no account.

> Measurement, never certification.

## Install

```bash
npx -y csoai-agent-plugin install
```

Or from a clone:

```bash
./install.sh                 # MiniMax Code (Mavis)
python3 factory.py install-all
```

## What it gives the host

| Capability | Names |
|---|---|
| Skills | `gspc`, `council`, `council-os`, `verify-card`, `sign-artifact`, `pack`, `platform-measure` |
| MCP | `gspc` — the live board, `https://councilof.ai/mcp` · `csoai-governance` — seal and verify bytes |
| Hooks (MiniMax Code) | `SessionStart` live board context · `UserPromptSubmit` outward-gate nudge · `PreToolUse` bash guard · `SessionEnd` receipt |

## Platform families

One canonical source; `platforms.json` is the only list. The factory renders the right package for
each family and wires the MCP servers.

| Adapter | Families |
|---|---|
| `skill-plugin` | MiniMax Code (Mavis), Claude Code, Grok |
| `rules-md` | Cursor, Windsurf, Continue, Cline, Roo Code, Zed, Kilo Code, Amazon Q, Warp, OpenHands, Trae |
| `agent-file` | Codex CLI, Gemini CLI, OpenCode, Qwen Code, OpenClaw, Goose, Aider |
| `mcp-only` | Hermes |

`GET https://councilof.ai/api/plugin/platforms` is the live projection of the same matrix, and
MEOK routes from it.

## What it will not do

- It will not certify anything, and it will not score CSOAI's own products.
- It will not fill an empty cell. `UNMEASURED` is an answer, never 0.
- It will not merge with `--admin`, and it will not reduce a check.
- It will not add a second MCP server for an endpoint the host already reaches under another name.
- It will not overwrite a host's own files without a backup.

## Licence

MIT — see [LICENSE](LICENSE). CSOAI Ltd, UK Companies House 16939677. This plugin is published for
public use. The board and verification stay free, forever, for everyone.

Measurement, not certification. Anyone can re-check at https://councilof.ai/verify
