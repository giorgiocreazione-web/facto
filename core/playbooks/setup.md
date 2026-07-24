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
into a per-type area. If you catch yourself proposing an area whose name is a
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

## Step 7 — Verify and hand over
Call `facto_status` and `facto_brief` on one area. Confirm the memory reflects
reality. Tell the human it's ready, and that from now on every session opens with
this briefing. Point them to the day-to-day rules (the daily playbook).

## The principle
You are not filling a database — you are **writing the project's memory the way the
expert who owns it would**: semantic, honest, current. If the human's mental model
and your areas don't match, the human is right. Adjust.
