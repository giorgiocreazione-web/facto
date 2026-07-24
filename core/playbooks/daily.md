# Facto — Daily playbook (keep the memory alive)

This project uses **Facto** as its living memory. At session start you already
received the briefing (goal, state, blockers, last handoff). Your job while you
work: **keep that memory true**, so the next session — you or someone else —
starts further ahead instead of re-learning everything.

## While you work — register as it happens
The moment one of these is real, record it in the **right area**, one idea per
fact, short and dated:
- made a **decision** (chose X over Y, and why) → `facto_add_fact(area, type="decisione", text=…)`
- hit or fixed a **bug** → `type="bug"` (or close it, see below)
- found a **constraint / rule of the codebase** → `type="vincolo"` / `"operativo"`
- the project **state** moved forward → `type="stato"`
- discovered a **reusable pattern** → `type="pattern"`

Don't batch it for "later" — later never comes, and the fact is lost.

## When something is no longer true
A new fact that supersedes an old one: `facto_close_fact` the old one (history is
**kept**, not deleted), then add the new. The memory must never assert something
that stopped being true.

## At session end
`facto_handoff(area, text=…)` — **what you did + where you were heading + what is
verified vs assumed.** This is the baton. It's the single most valuable thing you
leave behind.

## Before you trust the memory
`facto_status` — the trust light. **GREEN** = aligned with the code, trust it.
**YELLOW / RED** = the memory is behind the code, refresh before relying on it.

## The principle
The memory is only as good as your discipline in keeping it. **A fact not written
is a fact the next session re-learns the hard way** — in wasted time and tokens.
Writing it takes five seconds; not writing it costs the next session an hour.
