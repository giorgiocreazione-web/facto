# Changelog

All notable changes to **Facto** (Free edition, MIT).
Format follows [Keep a Changelog](https://keepachangelog.com);
versioning follows [SemVer](https://semver.org).

While Facto is in `0.x`, the public surface — CLI flags, MCP tool names, config
keys — can still change between minor versions. Every breaking change is listed
here, at the top of its release.

---

## [0.1.0] — 2026-07-24

First public release. The engine has been in daily use on a real multi-project
codebase since June 2026; this is the first cut packaged, tested and published
for everyone else.

### The engine

- **Dated facts, bi-temporal.** A new fact *closes* the previous one instead of
  overwriting it: the current picture stays clean, the history stays queryable.
- **Trust light.** The memory is compared against the real state of your git
  repo and says out loud when it should not be believed — `GREEN` (trust it),
  `YELLOW` (verify), `RED` (refresh). On an empty memory it says *no memory yet*
  rather than green.
- **Areas.** Memory split per area of the project, so each agent gets the
  compass of *its* corner instead of one big blob.
- **Local by design.** One SQLite file inside your project, pure Python standard
  library: zero dependencies, no account, no telemetry, zero network calls.
- **Several agents at once.** WAL mode — concurrent readers while someone
  writes. Optional hard boundary per agent with `FACTO_AREA=<slug>`, which
  refuses writes to any other area.
- **Snapshots.** A silent database snapshot at session start (`.facto/backups`),
  at most one every 12 hours, last ten kept.

### Getting it wired

- One-line installer for macOS/Linux (`install.sh`) and Windows (`install.ps1`):
  it uses the best installer already on the machine (`uv`, `pipx` or `pip`) and
  fetches `uv` when there is none — no Python toolchain required beforehand.
- `facto connect` for **Claude Code** (session hook + `.mcp.json`), **Cursor**,
  **VS Code / Copilot**, **OpenAI Codex**, **Gemini CLI**, plus `connect any`
  for a universal MCP block. Configs are **merged, never overwritten**, and a
  `.bak` is written first.
- An **AGENTS.md** protocol block, so an agent with no MCP support can still
  drive Facto from the shell.
- `connect` adds `.facto/` to your `.gitignore`, keeping the database out of
  your repo while the config stays tracked.

### Interfaces

- **CLI**: `connect` · `doctor` · `status` · `brief` · `dashboard` · `query` ·
  `add-area` · `remove-area` · `add` · `close` · `handoff` · `tray` ·
  `mcp-serve`.
- **MCP tools, read *and* write in Free**: `facto_status`, `facto_brief`,
  `facto_search`, `facto_add_fact`, `facto_close_fact`, `facto_handoff`,
  `facto_add_area`, `facto_remove_area`.
- **Mission Control** dashboard: the graph of every fact, the trust light,
  full-text search, the per-area compass, statistics, and **Compose** — writing
  facts, handoffs and closures straight from the browser. English and Italian.
- Optional **tray / start-at-login** (`facto tray on`), opt-in and reversible;
  on Windows a real icon next to the clock.

### Verified, not assumed

- Cross-platform smoke suite green in CI on four runners: Linux (Python 3.9 and
  3.12), Windows and macOS.
- A deterministic MCP config check proves that every config Facto writes
  actually launches a working server — including the unknown-tool case.
- Installation exercised on a clean machine with no Python tooling present, and
  from a clean virtual environment.

[0.1.0]: https://github.com/giorgiocreazione-web/facto/releases/tag/v0.1.0
