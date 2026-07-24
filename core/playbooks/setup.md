# Facto — Setup playbook (you are the memory architect)

Facto is installed in this project, but its memory is still empty. **You are the
architect.** Your job: build a memory structure that mirrors how this project is
*really* organized, then seed it with the current state. Work **with** the human —
propose, never impose.

## Step 1 — Explore (read, don't guess)
- Map the folder structure, **including nested levels**: a real module often lives
  at `code/01_thing`, `packages/foo`, `apps/bar`, `services/x` — not at the top.
- Read the README(s), `docs/`, and any handoff / decisions / changelog / TODO
  files. Run `git log --oneline -20`.
- Goal: understand this project's real **modules** and its **current state**.

## Step 2 — Recognise WHAT this folder is (before designing anything)

People use Facto for very different things, so there is no single right layout.
Look at what you actually found and say out loud which of these it is:

- **A CONTAINER of projects** — an agency folder, a workspace, a monorepo of
  separate products (`clients/`, `apps/`, `01_thing/ 02_other/`). Each project
  is independent: different stack, different goal, own history.
  → **one area per project** (`astro`, `bridge`, `crm`), and the memory becomes
  the switchboard across all of them.
- **A SINGLE project** — one product, one goal, made of parts that only make
  sense together (`engine/ ui/ audio/`, `api/ web/ db/`).
  → **one area per module** (`engine`, `ui`, `audio`).
- **Neither, yet** — a nearly empty folder, or a project with no real structure.
  → don't invent areas. Ask the human what they are about to build, and start
  with one or two areas that match their answer (even a single `main` is fine —
  areas can be added later with `facto_add_area`, or removed with
  `facto_remove_area`).

Tell the human which case you think it is **and why**, in one line, before you
propose the areas: *"This looks like a container of separate projects — I'd make
one area per project. Agree?"* If they say it's the other case, they are right.

## Step 3 — Design the areas (this is the craft)
An **area** is a logical module of the project — the unit you'd brief a teammate
on: *what* the work is about (engine, ui, payments, strategy). What makes areas
*good* (this is exactly how an expert owner would do it):
- **Semantic short slug, NOT the folder name.** `01_generatore-siti-astro` →
  `factory`. `services/payment-gateway` → `payments`. A human, domain name.
- **Real modules, not noise.** Skip build/deps/tooling and archives:
  `node_modules`, `dist`, `.venv`, `vendor`, `build`, caches, `.obsidian`, `_archivio`.
- **Right depth.** If modules are nested (monorepo, numbered folders), point each
  area at the real subfolder, not the parent. One `code/` folder is not one area.
- **Few and meaningful.** 5 areas that mean something beat 30 folders.

### ⚠ The trap: folders organized by TYPE, not by module
Some projects keep folders like `decisions/`, `handoffs/`, `docs/`, `bugs/`,
`01_decisioni/`, `02_handoff/`, `03_doc-tecnici/`. **These are NOT areas.** They
group documents by **type of fact**, not by module — and area vs type are two
different axes you must never collapse into one:
- an **area** answers *"what module?"* (payments, engine, strategy)
- a **fact type** answers *"what kind of note?"* (`decisione`, `handoff`, `bug`,
  `stato`, `bloccante`…) — and every area already carries all of them.

So do **not** create an area called `handoff` or `decisions`. Instead, take what's
inside those type-folders and **distribute it into the real module-areas as facts
of the right type**: a payment decision is a `decisione` fact in `payments`, a
build bug is a `bug` fact in `engine`. Facts that are genuinely cross-cutting (a
global handoff, a project-wide decision) go into the **`globale`** area — never
into a per-type area. ⚠ **`globale` already exists in every project and is
reserved: do NOT call `facto_add_area` for it** (it will be refused). Just write
into it: `facto_add_fact(area="globale", …)`. If you catch yourself proposing an area whose name is a
*document type*, stop: that's a fact type, not a module.

## Step 4 — Propose and get confirmation (MANDATORY)
Show the human a short table: **slug · path · one line of what it is**. Ask:
*"Do these areas match how you think of the project? Rename / merge / drop
anything?"* **Wait for an explicit yes. Do not proceed without it.** They own the
project — the names must be theirs.

## Step 5 — Write the structure
For each confirmed area call the MCP tool **`facto_add_area(slug, path, label)`**.
It writes the area into `facto.config.json` (validated). Do them one by one.

## Step 6 — Seed the memory (from the docs, not just from git)
For each area, register the facts that are **true now**, reading the project's own
documents — this is what stops the memory from being "blind" on day one:
- the **goal** of the area → `facto_add_fact(area, type="obiettivo", text=…)`
- key **decisions / constraints** → `type="decisione"` / `"vincolo"`
- open **blockers / bugs** → `type="bloccante"` / `"bug"`
- the current **state** → `type="stato"`
Keep each fact short, one idea, dated. Then, for each active area, leave a
`facto_handoff(area, text=…)` with where things stand right now.

## Step 7 — Verify

Call `facto_status` and `facto_brief` on one area. Confirm the memory reflects
reality. **If `facto_status` disagrees with what you just wrote**, say so to the
human instead of hiding it — a memory that lies about itself is worse than none.

## Step 8 — TEACH them how to use it (never skip this)

They just watched you build something they don't yet know how to run. Close the
setup by teaching it, in **six short lines, plain language, no lecture**:

1. **What just happened** — "your project now has a memory: N areas, M facts."
2. **What happens by itself** — every session of any AI agent here opens with
   this briefing; you don't have to paste context ever again.
3. **What you do** — nothing special. Work as always: I record decisions, bugs
   and state as they happen, and leave a handoff at the end.
4. **How to look at it** — `facto dashboard` (browser: the graph, the search,
   and Compose to write without a terminal) · `facto status` (the trust light)
   · `facto brief <area>` (one area's compass).
5. **How to fix it when it's wrong** — tell me ("that's no longer true"), or do
   it yourself: `facto add-area` / `facto remove-area` / `facto add`.
6. **What the light means** — green = trust it, yellow = check, red = refresh
   first, new = nothing recorded here yet. It compares the memory with git, so
   it can tell you when it has gone stale.

Then ask: *"anything here you'd like to change before we start working?"*

The rule: **they must be able to use it without you.** If they'd have to ask
"and now what?", you have not finished.

### The three questions everyone asks next — answer them without being asked

**"When is my stuff actually saved?"** — Immediately. Every fact is written to
`.facto/facto.db` (SQLite, inside the project) the moment it is recorded: there
is no save button and nothing is buffered. If a session dies mid-work, whatever
was already recorded is there. A silent snapshot of the database is taken at
session start into `.facto/backups` (at most one every 12 hours, last 10 kept).
Nothing leaves the machine — no account, no cloud, no telemetry.

**"How does a session start and end?"** — It *starts* by itself: opening any AI
agent in this folder injects the briefing, you do nothing. It does **not** end
by itself: there is no closing hook, so the handoff — the baton for next time —
has to be written **before** you close. Say *"leave the handoff"*, or count on
me doing it when we're wrapping up. A session closed without a handoff loses
nothing that was recorded, but the next one restarts a step behind: it knows
*what* is true, not *where we were heading*.

**"Can I run several agents at once?"** — Yes. The database takes concurrent
readers even while someone writes (SQLite in WAL mode), and a write that finds
it busy waits its turn for up to five seconds. Two agents in two terminals on
the same project is a normal, supported setup. Two things to know:
- **Give them different areas.** Facts add up without conflict, but *state* and
  *handoff* are one-per-area: if two agents write the handoff of the SAME area,
  the last one wins and the earlier is closed into history.
- To make the boundary hard, launch an agent with `FACTO_AREA=<slug>`: it will
  be **refused** if it tries to write outside that area (or into `globale`).
  Useful when you fan out work and want no crossing.

## The principle
You are not filling a database — you are **writing the project's memory the way the
expert who owns it would**: semantic, honest, current. If the human's mental model
and your areas don't match, the human is right. Adjust.
