#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FACTO — console entry point (`facto ...`).

La porta d'ingresso GENTILE del prodotto:
- senza argomenti: orienta (config trovato? -> stato; assente -> come partire)
- `facto init`: bootstrap zero-config (aree auto-rilevate) con conferma se in TTY
- `facto connect claude-code|mcp|cursor|vscode|codex|gemini|agents|git|any|--all`:
  collega gli strumenti DA SOLO (fonde i config esistenti, mai distrugge;
  backup .bak prima di scrivere; --all rileva gli editor presenti; `any`
  stampa il kit universale per QUALSIASI client MCP, anche non elencato)
- `facto claude-hook`: il comando che Claude Code invoca a inizio sessione
  (stdin JSON -> brief nel contesto; se il motore muore l'agente LO VEDE)
- `facto handoff <area>`: guidato in 3 domande quando sei in terminale
- ogni altro verbo: delega al motore (mem.main)

NB: mem.py carica il config A IMPORT TIME (ed esce se manca): qui il config si
cerca PRIMA di importare mem — mai un traceback per una cartella senza progetto.
"""
import json
import os
import sys

# Windows: in una pipe stdout e' cp1252 e i caratteri del prodotto (⚠ · —)
# esploderebbero. UTF-8 esplicito, come negli altri moduli.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

LANG = ((os.environ.get("FACTO_LANG") or os.environ.get("REGISTRO_LANG") or "en").strip().lower()[:2])


def T(en, it):
    return it if LANG == "it" else en


# ----------------------------- config discovery -----------------------------
def _find_config(start=None):
    """Replica minima della ricerca di mem: $FACTO_CONFIG -> risali da CWD."""
    env = os.environ.get("FACTO_CONFIG") or os.environ.get("REGISTRO_CONFIG")
    if env and os.path.isfile(env):
        return os.path.abspath(env)
    d = os.path.abspath(start or os.getcwd())
    while True:
        cand = os.path.join(d, "facto.config.json")
        if os.path.isfile(cand):
            return cand
        nd = os.path.dirname(d)
        if nd == d:
            return None
        d = nd


def _import_mem():
    try:
        from . import mem                       # installato come package (pip)
        return mem
    except ImportError:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import mem                              # lanciato da cartella (repo/zip Pro)
        return mem


# ----------------------------- guida (a vuoto) -----------------------------
def _guide():
    print("facto — " + T("project memory for people who build with AI agents",
                         "memoria di progetto per chi costruisce con agenti AI"))
    print()
    cfg = _find_config()
    if cfg:
        print(T(f"  project config: {cfg}", f"  config del progetto: {cfg}"))
        print()
        print(T("  facto status         trust light for every area",
                "  facto status         semaforo di fiducia per ogni area"))
        print(T("  facto brief <area>   the compass for one area",
                "  facto brief <area>   la bussola di un'area"))
        print(T("  facto connect --all  hook Claude Code + MCP + git + AGENTS.md (+ editors it detects)",
                "  facto connect --all  aggancia Claude Code + MCP + git + AGENTS.md (+ editor rilevati)"))
        print(T("  facto --help         all commands", "  facto --help         tutti i comandi"))
    else:
        print(T("  No facto.config.json found from here upwards.",
                "  Nessun facto.config.json trovato da qui in su."))
        print()
        print(T("  To start in this folder:", "  Per partire in questa cartella:"))
        print(T("    facto connect --all  set up + wire your agent to the memory",
                "    facto connect --all  prepara + collega il tuo agente alla memoria"))
        print(T("  Then open Claude Code here: it designs the areas with you, guided.",
                "  Poi apri Claude Code qui: disegna le aree con te, guidato."))
    return 0


def _help():
    """L'aiuto completo, leggibile, che NON richiede un progetto configurato."""
    print("facto — " + T("project memory for people who build with AI agents",
                         "memoria di progetto per chi costruisce con agenti AI"))
    print()
    print(T("SETUP", "PREPARAZIONE"))
    print(T("  facto connect --all      wire this project: Claude Code hook + MCP + git +",
            "  facto connect --all      collega il progetto: hook Claude Code + MCP + git +"))
    print(T("                           AGENTS.md, plus the editors it detects",
            "                           AGENTS.md, più gli editor che rileva"))
    print(T("  facto connect <target>   claude-code · mcp · cursor · vscode · codex · gemini ·",
            "  facto connect <target>   claude-code · mcp · cursor · vscode · codex · gemini ·"))
    print("                           agents · git")
    print(T("  facto connect any        print the MCP block for ANY other tool",
            "  facto connect any        stampa il blocco MCP per QUALSIASI altro tool"))
    print(T("  facto doctor             check that everything is in place",
            "  facto doctor             controlla che sia tutto a posto"))
    print()
    print(T("DAILY USE", "USO QUOTIDIANO"))
    print(T("  facto status             the trust light: can you believe the memory?",
            "  facto status             il semaforo: ci si può fidare della memoria?"))
    print(T("  facto brief <area>       the compass of one area", "  facto brief <area>       la bussola di un'area"))
    print(T("  facto dashboard          Mission Control in your browser",
            "  facto dashboard          Mission Control nel browser"))
    print(T("  facto query <text>       full-text search across the facts",
            "  facto query <testo>      ricerca full-text nei fatti"))
    print()
    print(T("WRITING (your agent does this on its own via MCP)",
            "SCRITTURA (il tuo agente lo fa da solo via MCP)"))
    print(T('  facto add-area <slug> <path>        declare an area of the project',
            '  facto add-area <slug> <percorso>    dichiara un\'area del progetto'))
    print(T('  facto add <area> <type> "<text>"    record a dated fact',
            '  facto add <area> <tipo> "<testo>"   registra un fatto datato'))
    print(T('  facto close <area> <type> --like    close what is no longer true',
            '  facto close <area> <tipo> --like    chiude ciò che non è più vero'))
    print(T("  facto handoff <area>                leave the baton for next session",
            "  facto handoff <area>                lascia il testimone alla prossima sessione"))
    print()
    print(T("ALWAYS ON (optional)", "SEMPRE ACCESO (facoltativo)"))
    print(T("  facto tray on|off|status  start at login; on Windows, icon next to the clock",
            "  facto tray on|off|status  avvio al login; su Windows, icona vicino all'orologio"))
    print()
    cfg = _find_config()
    if cfg:
        print(T(f"project: {os.path.dirname(cfg)}", f"progetto: {os.path.dirname(cfg)}"))
    else:
        print(T("No project here yet — run `facto connect --all` in your project folder.",
                "Nessun progetto qui — lancia `facto connect --all` nella cartella del progetto."))
    return 0


# ------------------------- scaffold + playbooks (ex-init) -------------------------
# `facto init` non esiste piu': non si indovinano le aree con un'euristica cieca.
# `facto connect` prepara il terreno (config-scheletro VUOTO + .facto/) e al PRIMO
# avvio l'AGENTE costruisce la struttura seguendo il playbook di setup
# (onboarding agente-guidato: l'intelligenza e' l'agente, non un algoritmo).
def _scaffold_config(root):
    """facto.config.json SCHELETRO (projects={} — le aree le mette l'agente) + .facto/.
    Ritorna il path del config."""
    brand = os.path.basename(root.rstrip("\\/")) or "Project"
    ha_git = os.path.isdir(os.path.join(root, ".git"))
    git_cfg = {"enabled": ha_git}
    if ha_git:
        # il branch VERO del repo, non un "main" presunto: chi ha `master` (o
        # altro) non deve vedersi taggare ogni stato con "NOT on main".
        try:
            import subprocess
            r = subprocess.run(["git", "-C", root, "branch", "--show-current"],
                               capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=10)
            br = (r.stdout or "").strip()
            if br:
                git_cfg["main_branch"] = br
        except Exception:
            pass
    cfg = {"brand": brand, "root": ".", "db_path": ".facto/facto.db",
           "git": git_cfg,
           "projects": {}}
    path = os.path.join(root, "facto.config.json")
    # newline="\n": EOL identici su ogni OS — file condivisi via git in team misti
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(cfg, fh, ensure_ascii=False, indent=2)
    os.makedirs(os.path.join(root, ".facto"), exist_ok=True)
    return path


def _playbooks_dir():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "playbooks")

def _read_playbook(nome):
    try:
        with open(os.path.join(_playbooks_dir(), nome), encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return ""

def _setup_context():
    """Contesto iniettato al PRIMO avvio (progetto non ancora strutturato): il
    playbook che trasforma l'agente nell'architetto della memoria."""
    pb = _read_playbook("setup.md")
    head = ("[Facto — automatic first-run onboarding]\n"
            "Facto is installed here but this project's memory is EMPTY (no areas "
            "yet). Before normal work, run the setup below: explore the project, "
            "propose the areas to the human, get confirmation, then build the "
            "memory. Do this now.\n\n")
    return head + (pb or "Explore the project, propose areas, call facto_add_area "
                   "for each after the human confirms, then seed facts from the docs.")

def _daily_reminder():
    """Promemoria compatto a ogni sessione di lavoro (il playbook daily condensato;
    il file completo resta per approfondire)."""
    return ("[Facto] Keep the memory alive as you work: facto_add_fact for "
            "decisions/bugs/state, facto_close_fact when something changes, "
            "facto_handoff at session end. Trust light: facto_status.")


# ----------------------------- connect -----------------------------
def _rel(p, root):
    """Percorso RELATIVO al progetto per i messaggi: un muro di path assoluti
    lunghi tre righe non si legge, e l'utente sa dov'è casa sua."""
    try:
        r = os.path.relpath(p, root)
        return r if not r.startswith("..") else p
    except ValueError:                          # unità diverse su Windows
        return p


def _merge_json(path, mutate):
    """Carica un JSON (o {}), lo passa a mutate(dati)->dati, salva con backup .bak.
    Ritorna (changed, err)."""
    dati = {}
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8-sig") as fh:
                dati = json.load(fh)
        except Exception as e:
            return False, T(f"cannot parse {path}: {e}", f"non riesco a leggere {path}: {e}")
    prima = json.dumps(dati, sort_keys=True)
    dati = mutate(dati)
    if json.dumps(dati, sort_keys=True) == prima:
        return False, None
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    if os.path.isfile(path):
        try:
            import shutil
            shutil.copy2(path, path + ".bak")
        except OSError:
            pass
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(dati, fh, ensure_ascii=False, indent=2)
    return True, None


def _connect_claude(root):
    """Hook SessionStart di Claude Code -> `facto claude-hook` (comando nel PATH:
    niente path assoluti fragili, niente script da copiare)."""
    sp = os.path.join(root, ".claude", "settings.json")
    def mutate(d):
        hooks = d.setdefault("hooks", {})
        arr = hooks.setdefault("SessionStart", [])
        for entry in arr:
            for h in entry.get("hooks", []):
                if "facto claude-hook" in (h.get("command") or ""):
                    return d                                   # gia' collegato
        arr.append({"matcher": "*", "hooks": [{"type": "command", "command": "facto claude-hook"}]})
        return d
    ch, err = _merge_json(sp, mutate)
    tag = "claude-code"
    if err:
        print(f"  [FAIL] {tag}: {err}"); return False
    print(f"  [ OK ] {tag}: " + (T(f"hook added in {_rel(sp, root)}", f"hook aggiunto in {_rel(sp, root)}") if ch else
                                 T("already connected", "gia' collegato")))
    return True


def _mcp_block():
    return {"command": "facto", "args": ["mcp-serve"]}


def _connect_mcp(root):
    """Server MCP nel .mcp.json del progetto (Claude Code lo carica da li')."""
    sp = os.path.join(root, ".mcp.json")
    def mutate(d):
        d.setdefault("mcpServers", {})["facto"] = _mcp_block()
        return d
    ch, err = _merge_json(sp, mutate)
    if err:
        print(f"  [FAIL] mcp: {err}"); return False
    print("  [ OK ] mcp: " + (T(f"server 'facto' in {_rel(sp, root)}", f"server 'facto' in {_rel(sp, root)}") if ch else
                              T("already connected", "gia' collegato")))
    return True


def _connect_cursor(root):
    sp = os.path.join(root, ".cursor", "mcp.json")
    def mutate(d):
        d.setdefault("mcpServers", {})["facto"] = _mcp_block()
        return d
    ch, err = _merge_json(sp, mutate)
    if err:
        print(f"  [FAIL] cursor: {err}"); return False
    print("  [ OK ] cursor: " + (T(f"server 'facto' in {_rel(sp, root)}", f"server 'facto' in {_rel(sp, root)}") if ch else
                                 T("already connected", "gia' collegato")))
    return True


def _connect_vscode(root):
    """VS Code / GitHub Copilot: .vscode/mcp.json — root key 'servers' (NON
    'mcpServers': e' l'errore di setup n.1 copiando config di altri client)."""
    sp = os.path.join(root, ".vscode", "mcp.json")
    def mutate(d):
        d.setdefault("servers", {})["facto"] = _mcp_block()
        return d
    ch, err = _merge_json(sp, mutate)
    if err:
        print(f"  [FAIL] vscode: {err}"); return False
    print("  [ OK ] vscode: " + (T(f"server 'facto' in {_rel(sp, root)}", f"server 'facto' in {_rel(sp, root)}") if ch else
                                 T("already connected", "gia' collegato")))
    return True


def _connect_gemini(root):
    """Gemini CLI: .gemini/settings.json — stesso schema 'mcpServers' di Claude."""
    sp = os.path.join(root, ".gemini", "settings.json")
    def mutate(d):
        d.setdefault("mcpServers", {})["facto"] = _mcp_block()
        return d
    ch, err = _merge_json(sp, mutate)
    if err:
        print(f"  [FAIL] gemini: {err}"); return False
    print("  [ OK ] gemini: " + (T(f"server 'facto' in {_rel(sp, root)}", f"server 'facto' in {_rel(sp, root)}") if ch else
                                 T("already connected", "gia' collegato")))
    return True


def _connect_codex(root):
    """OpenAI Codex (CLI, VS Code, Desktop: stessa config): .codex/config.toml
    project-scoped. Niente writer TOML in stdlib -> append di un blocco, mai
    distruttivo; parse di verifica con tomllib dove c'e' (3.11+)."""
    sp = os.path.join(root, ".codex", "config.toml")
    cur = ""
    if os.path.isfile(sp):
        with open(sp, encoding="utf-8-sig", errors="replace") as fh:
            cur = fh.read()
    if "[mcp_servers.facto]" in cur:
        print("  [ OK ] codex: " + T("already connected", "gia' collegato")); return True
    blocco = ("\n# facto project memory (added by `facto connect codex`)\n"
              "[mcp_servers.facto]\n"
              'command = "facto"\n'
              'args = ["mcp-serve"]\n')
    os.makedirs(os.path.dirname(sp), exist_ok=True)
    if cur:
        try:
            import shutil
            shutil.copy2(sp, sp + ".bak")
        except OSError:
            pass
    with open(sp, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(blocco if cur.endswith("\n") or not cur else "\n" + blocco)
    try:                                   # verifica: il TOML deve restare valido
        import tomllib
        with open(sp, "rb") as fh:
            tomllib.load(fh)
    except ModuleNotFoundError:
        pass                               # Python < 3.11: niente parse, l'append resta sicuro
    except Exception as e:
        if cur:
            with open(sp, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(cur)              # ripristina: meglio non-connesso che config rotto
        print(f"  [FAIL] codex: " + T(f"config.toml would break ({e}) — restored",
                                      f"config.toml si romperebbe ({e}) — ripristinato"))
        return False
    print("  [ OK ] codex: " + T(f"server 'facto' in {_rel(sp, root)}", f"server 'facto' in {_rel(sp, root)}"))
    return True


_AGENTS_BEGIN = "<!-- facto:begin -->"
_AGENTS_END = "<!-- facto:end -->"


def _agents_block():
    """Il protocollo memoria per QUALSIASI agente che legge AGENTS.md (standard
    aperto: Codex, Cursor, Copilot, Gemini, Windsurf, Zed, Aider...)."""
    return (_AGENTS_BEGIN + "\n"
            "## Project memory (Facto)\n"
            "\n"
            "This project keeps a dated, bi-temporal memory of facts in `.facto/`\n"
            "(engine: `facto`, MCP server: `facto mcp-serve`). Work WITH it:\n"
            "\n"
            "1. **Session start — orient yourself**: MCP tools `facto_status` (trust\n"
            "   light per area) and `facto_brief` (the compass of one area); no MCP?\n"
            "   run `facto status` / `facto brief <area>` from the shell.\n"
            "2. **While working — record dated facts** as things happen, via\n"
            "   `facto_add_fact` (types: stato, decisione, bug, bloccante, vincolo,\n"
            "   operativo, nota); close superseded ones with `facto_close_fact`\n"
            "   (nothing is deleted: history stays).\n"
            "3. **Session end — leave the baton**: `facto_handoff` with what was\n"
            "   done, the next direction, and verified-vs-assumed.\n"
            "\n"
            "**No MCP support in your tool?** Every step also works from the shell —\n"
            "any agent that can run commands is fully covered:\n"
            "`facto status` · `facto brief <area>` · `facto add <area> <type> \"<text>\"` ·\n"
            "`facto close <area> <type>` · `facto handoff <area>`.\n"
            "\n"
            "Never edit `.facto/facto.db` by hand.\n"
            + _AGENTS_END + "\n")


def _connect_agents(root):
    """AGENTS.md alla root: UN file di istruzioni per tutti gli agenti non-Claude.
    Blocco marcato facto:begin/end — aggiornabile e idempotente; il resto del
    file resta del proprietario."""
    sp = os.path.join(root, "AGENTS.md")
    blocco = _agents_block()
    cur = None
    if os.path.isfile(sp):
        with open(sp, encoding="utf-8-sig", errors="replace") as fh:
            cur = fh.read()
    if cur is None:
        nuovo = "# Agent instructions\n\n" + blocco
    elif _AGENTS_BEGIN in cur and _AGENTS_END in cur:
        pre, resto = cur.split(_AGENTS_BEGIN, 1)
        _, post = resto.split(_AGENTS_END, 1)
        nuovo = pre + blocco.rstrip("\n") + post
        if nuovo == cur:
            print("  [ OK ] agents: " + T("already connected", "gia' collegato")); return True
    else:
        nuovo = cur.rstrip() + "\n\n" + blocco
    if cur is not None:
        try:
            import shutil
            shutil.copy2(sp, sp + ".bak")
        except OSError:
            pass
    with open(sp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(nuovo)
    print("  [ OK ] agents: " + T(f"memory protocol block in {_rel(sp, root)}",
                                  f"blocco protocollo memoria in {_rel(sp, root)}"))
    return True


def _connect_any(root):
    """IL KIT UNIVERSALE — per QUALSIASI client MCP, anche uno non elencato / non
    ancora esistente. Non scrive file: STAMPA le due righe che bastano ovunque +
    i blocchi pronti nei formati comuni. Facto parla lo standard: il server e' UNO
    (`facto mcp-serve`), cambia solo dove ogni tool tiene la sua config."""
    print(T("Facto speaks MCP — the universal standard. To connect ANY tool (even one",
            "Facto parla MCP — lo standard universale. Per collegare QUALSIASI tool (anche uno"))
    print(T("not listed, or that doesn't exist yet) point it at this ONE command:",
            "non elencato, o che non esiste ancora) puntalo a QUESTO unico comando:"))
    print()
    print("    command:  facto")
    print('    args:     ["mcp-serve"]')
    print()
    print(T("Ready-made blocks — paste into your tool's MCP config, wherever it keeps it:",
            "Blocchi pronti — incolla nella config MCP del tuo tool, dovunque la tenga:"))
    print()
    print('  # JSON, "mcpServers" key  (Claude Code, Cursor, Gemini, most tools)')
    print('  { "mcpServers": { "facto": { "command": "facto", "args": ["mcp-serve"] } } }')
    print()
    print('  # JSON, "servers" key  (VS Code / Copilot)')
    print('  { "servers": { "facto": { "command": "facto", "args": ["mcp-serve"] } } }')
    print()
    print("  # TOML, [mcp_servers.facto]  (Codex)")
    print('  [mcp_servers.facto]')
    print('  command = "facto"')
    print('  args = ["mcp-serve"]')
    print()
    print(T("No MCP at all? Any agent still uses Facto from the shell:",
            "Niente MCP? Qualsiasi agente usa Facto da riga di comando:"))
    print('    facto add-area <slug> <path> · facto status · facto brief <area>')
    print('    facto add <area> <type> "<text>" · facto handoff <area>')
    print(T("(AGENTS.md carries this protocol to every agent that reads it.)",
            "(AGENTS.md porta questo protocollo a ogni agente che lo legge.)"))
    return True


def _proteggi_gitignore(root):
    """`.facto/` fuori dal repo dell'utente. Il DB è binario e personale: senza
    questa riga finisce dritto nel suo primo `git add -A` — un regalo che non
    ha chiesto. Il CONFIG invece resta tracciato: è la struttura condivisa."""
    gi = os.path.join(root, ".gitignore")
    riga = ".facto/"
    cur = ""
    if os.path.isfile(gi):
        with open(gi, encoding="utf-8-sig", errors="replace") as fh:
            cur = fh.read()
        if any(l.strip() in (".facto", ".facto/") for l in cur.splitlines()):
            return False                       # già protetto: non tocco nulla
    blocco = ("" if not cur or cur.endswith("\n") else "\n") + \
             "\n# Facto: local memory database (personal, not shared)\n" + riga + "\n"
    with open(gi, "a" if cur else "w", encoding="utf-8", newline="\n") as fh:
        fh.write(blocco if cur else blocco.lstrip("\n"))
    return True


def _connect_git(root):
    """post-commit hook: la memoria si riallinea DA SOLA a ogni commit (semaforo auto-guarente)."""
    gitdir = os.path.join(root, ".git")
    if not os.path.isdir(gitdir):
        print("  [SKIP] git: " + T("not a git repo", "non e' un repo git")); return True
    if _proteggi_gitignore(root):
        print("  [ OK ] git: " + T(".facto/ added to .gitignore (the DB stays out of your repo)",
                                   ".facto/ aggiunto al .gitignore (il DB resta fuori dal tuo repo)"))
    hp = os.path.join(gitdir, "hooks", "post-commit")
    marker = "# facto auto-ingest"
    riga = "facto ingest-git >/dev/null 2>&1 || true"
    if os.path.isfile(hp):
        with open(hp, encoding="utf-8", errors="replace") as fh:
            cur = fh.read()
        if marker in cur:
            print("  [ OK ] git: " + T("already connected", "gia' collegato")); return True
        cur = cur.rstrip() + f"\n{marker}\n{riga}\n"
    else:
        cur = f"#!/bin/sh\n{marker}\n{riga}\n"
    os.makedirs(os.path.dirname(hp), exist_ok=True)
    with open(hp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(cur)
    try:
        os.chmod(hp, 0o755)
    except OSError:
        pass
    print("  [ OK ] git: " + T(f"post-commit hook in {_rel(hp, root)}", f"hook post-commit in {_rel(hp, root)}"))
    return True


def _cmd_connect(argv):
    # `facto connect any` = puro kit informativo: stampa e basta, NON tocca il
    # filesystem (niente scaffold, niente "connecting").
    if [a for a in argv if not a.startswith("-")] == ["any"]:
        return 0 if _connect_any(os.getcwd()) else 1
    cfg = _find_config()
    if not cfg:
        # niente config: `facto connect` prepara il terreno (era `facto init`).
        cfg = _scaffold_config(os.getcwd())
        print(T("prepared facto.config.json (empty — the agent designs the areas on first run)",
                "preparato facto.config.json (vuoto — le aree le disegna l'agente al primo avvio)"))
    root = os.path.dirname(cfg)
    targets = [a for a in argv if not a.startswith("-")]
    suggerisci = []
    if "--all" in argv or not targets:
        # Base sempre. Gli editor SOLO se questo PROGETTO li usa gia' (cartella
        # presente): avere Cursor installato sul PC non significa volerlo qui, e
        # creare .cursor/.vscode/.gemini in casa d'altri e' invadenza — finiscono
        # nel loro git. Se il binario c'e' ma la cartella no: si SUGGERISCE.
        targets = ["claude-code", "mcp", "git", "agents"]
        for t, cartella in (("cursor", ".cursor"), ("vscode", ".vscode"),
                            ("codex", ".codex"), ("gemini", ".gemini")):
            (targets if os.path.isdir(os.path.join(root, cartella)) else suggerisci).append(t)
    ok = True
    print(T(f"connecting ({', '.join(targets)}):", f"collego ({', '.join(targets)}):"))
    fns = {"claude-code": _connect_claude, "mcp": _connect_mcp, "cursor": _connect_cursor,
           "git": _connect_git, "vscode": _connect_vscode, "codex": _connect_codex,
           "gemini": _connect_gemini, "agents": _connect_agents, "any": _connect_any}
    for t in targets:
        fn = fns.get(t)
        if fn:
            ok &= fn(root)
        else:
            print(f"  [??  ] {t}: " + T("unknown target", "target sconosciuto")); ok = False
    if suggerisci:
        print("  " + T(f"(not detected here, available anytime: facto connect {' | '.join(suggerisci)})",
                       f"(non rilevati qui, disponibili quando vuoi: facto connect {' | '.join(suggerisci)})"))
    if "--all" in argv or not [a for a in argv if not a.startswith("-")]:
        print("  " + T("any other tool (even unknown)? `facto connect any` prints the universal block.",
                       "un altro tool (anche sconosciuto)? `facto connect any` stampa il blocco universale."))
    import shutil
    if not shutil.which("facto"):
        # gli hook (Claude e git) chiamano `facto` per nome: senza PATH non partirebbero
        print("  [WARN] " + T("`facto` is not on PATH from this shell: the Claude hook and the git hook "
                              "call it by name and would not fire. Open a NEW terminal, or run "
                              "`uv tool update-shell`; fallback: `python -m facto`.",
                              "`facto` non è nel PATH da questa shell: l'hook Claude e l'hook git lo "
                              "chiamano per nome e non partirebbero. Apri un terminale NUOVO, oppure "
                              "`uv tool update-shell`; ripiego: `python -m facto`."))
    # IL PASSO SUCCESSIVO, sempre: senza questa riga l'utente resta col cursore
    # che lampeggia e la domanda "e adesso?" — il momento in cui si perde.
    if ok:
        print()
        print(T("NEXT — open your AI agent in this folder (claude, cursor, …):",
                "ORA — apri il tuo agente AI in questa cartella (claude, cursor, …):"))
        print(T("  it gets the setup playbook, explores the project, proposes the areas,",
                "  riceve il playbook di setup, esplora il progetto, ti propone le aree,"))
        print(T("  and builds the memory once you confirm. Prefer by hand? "
                "`facto add-area <slug> <path>`",
                "  e costruisce la memoria appena confermi. A mano? "
                "`facto add-area <slug> <percorso>`"))
    return 0 if ok else 1


# ----------------------------- claude-hook -----------------------------
def _auto_snapshot(mem):
    """Copia di sicurezza silenziosa del DB (.facto/backups), max 1 ogni 12h, tiene 10.
    Best-effort: MAI deve far fallire l'apertura sessione."""
    try:
        import glob
        import sqlite3
        import time
        bdir = os.path.join(os.path.dirname(mem.DB), "backups")
        os.makedirs(bdir, exist_ok=True)
        snaps = sorted(glob.glob(os.path.join(bdir, "facto-*.db")))
        if snaps and (time.time() - os.path.getmtime(snaps[-1])) < 12 * 3600:
            return
        dest = os.path.join(bdir, time.strftime("facto-%Y%m%d-%H%M%S.db"))
        src = sqlite3.connect(mem.DB); dst = sqlite3.connect(dest)
        with dst:
            src.backup(dst)
        src.close(); dst.close()
        for old in snaps[:-9]:
            try:
                os.remove(old)
            except OSError:
                pass
    except Exception:
        pass


def _cmd_claude_hook():
    """SessionStart di Claude Code: stdin JSON -> contesto iniettato.
    REGOLA: il fallimento e' VISIBILE — se il motore non parte, l'agente riceve
    l'avviso invece di partire cieco in silenzio."""
    raw = ""
    try:
        raw = sys.stdin.read()
    except Exception:
        pass
    cwd = os.getcwd()
    try:
        p = json.loads(raw)
        if p.get("cwd"):
            cwd = p["cwd"]
    except Exception:
        pass
    testo = ""
    try:
        if os.path.isdir(cwd):
            os.chdir(cwd)                      # la ricerca del config parte da qui
        import argparse
        import contextlib
        import io
        buf = io.StringIO()
        # TUTTO dentro la redirezione, IMPORT COMPRESO: su stdout deve uscire SOLO
        # il JSON del protocollo hook — mai il testo d'aiuto del motore senza config.
        setup_mode = False
        with contextlib.redirect_stdout(buf):
            mem = _import_mem()
            con = mem.db()
            setup_mode = not mem.PROGETTI              # progetto NON ancora strutturato
            if not setup_mode:
                mem.cmd_session_start(con, argparse.Namespace(cwd=cwd))
            con.close()
        if setup_mode:
            testo = _setup_context()                   # onboarding: l'agente costruisce la memoria
        else:
            testo = (buf.getvalue().strip() + "\n\n" + _daily_reminder()).strip()
        _auto_snapshot(mem)
    except BaseException as e:                 # anche SystemExit del motore senza config
        testo = ("⚠ Facto: memory engine unavailable (%s). The session is starting BLIND: "
                 "no project memory was injected. Run `facto doctor` in the project folder." % e)
    if not testo or len(testo) < 20:
        testo = ("⚠ Facto: empty briefing. Run `facto doctor` in the project folder "
                 "(config or database problem).")
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                             "additionalContext": testo}}, ensure_ascii=False))
    return 0


# ----------------------------- handoff guidato -----------------------------
def _cmd_handoff_guided(area):
    mem = _import_mem()
    print(T(f"handoff for [{area}] — 3 questions, one line each (empty = skip):",
            f"handoff per [{area}] — 3 domande, una riga ciascuna (vuota = salta):"))
    try:
        fatto = input(T("  1. what did you do? ", "  1. cosa hai fatto? ")).strip()
        resta = input(T("  2. what remains / next direction? ", "  2. cosa resta / prossima direzione? ")).strip()
        verif = input(T("  3. verified vs assumed? ", "  3. verificato vs assunto? ")).strip()
    except (EOFError, KeyboardInterrupt):
        print(); return 1
    parti = []
    if fatto: parti.append(T("DONE: ", "FATTO: ") + fatto)
    if resta: parti.append(T("NEXT: ", "PROSSIMO: ") + resta)
    if verif: parti.append(T("VERIFIED vs ASSUMED: ", "VERIFICATO vs ASSUNTO: ") + verif)
    testo = "\n".join(parti)
    if len(testo) < 10:
        print(T("empty handoff, skipped", "handoff vuoto, skip")); return 1
    con = mem.db()
    esito = mem.upsert_singleton(con, area, "handoff", testo, mem.today(), T("session", "sessione"))
    con.close()
    print(T(f"handoff saved [{area}] ({esito}, {len(testo)} chars)",
            f"handoff salvato [{area}] ({esito}, {len(testo)} char)"))
    return 0


# ----------------------------- delega al motore -----------------------------
def _delegate(argv):
    mem = _import_mem()
    sys.argv = ["facto"] + argv
    try:
        mem.main()
        return 0
    except SystemExit as e:
        return int(e.code or 0)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        return _guide()
    cmd = argv[0]

    if cmd in ("--version", "version"):
        try:
            from . import __version__
        except ImportError:
            __version__ = "(dev)"
        print(f"facto {__version__}")
        return 0
    if cmd in ("--help", "-h", "help"):
        # SEMPRE disponibile: `facto --help` è la prima cosa che prova chi ha
        # appena installato, e finora rispondeva «no facto.config.json found»
        # (exit 2) — cioè l'aiuto era leggibile solo da chi non ne aveva bisogno.
        return _help()
    if cmd == "init":
        # `facto init` non esiste piu': niente auto-detect cieco delle aree.
        print(T("`facto init` is gone. Just run `facto connect --all`, then open your "
                "agent (Claude Code): it will design the areas with you, guided.",
                "`facto init` non esiste piu'. Lancia `facto connect --all`, poi apri il "
                "tuo agente (Claude Code): disegnera' le aree con te, guidato."))
        return 0
    if cmd == "connect":
        return _cmd_connect(argv[1:])
    if cmd == "claude-hook":
        return _cmd_claude_hook()
    if cmd == "mcp-serve":
        try:
            from . import mcp_server
        except ImportError:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            import mcp_server
        mcp_server.main()
        return 0
    if cmd == "tray-run":
        # il processo dell'icona/server (lanciato dall'autostart): --root esplicito
        try:
            from . import tray
        except ImportError:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            import tray
        return tray.tray_run(argv[1:])
    if cmd == "status":
        cmd, argv = "health", ["health"] + argv[1:]

    # config assente e serve il motore? messaggio gentile, mai traceback
    if not _find_config() and not (os.environ.get("FACTO_DB") or os.environ.get("REGISTRO_DB")):
        print(T("facto: no facto.config.json found from here upwards.",
                "facto: nessun facto.config.json trovato da qui in su."))
        print(T("  Run `facto connect --all` in your project folder to set it up.",
                "  Lancia `facto connect --all` nella cartella del progetto per prepararlo."))
        return 2

    # tray: «sempre acceso» OPT-IN (icona vicino all'orologio su Windows;
    # autostart del server su ogni OS). on|off|status.
    if cmd == "tray":
        try:
            from . import tray
        except ImportError:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            import tray
        cfg = _find_config()
        return tray.cmd_tray(argv[1:], os.path.dirname(cfg) if cfg else os.getcwd())

    # dashboard: la promessa del README — Mission Control nel BROWSER (ogni OS).
    # `facto dashboard --text` = la vista compatta in terminale, dal motore.
    if cmd == "dashboard":
        if "--text" in argv:
            return _delegate([a for a in argv if a != "--text"])
        try:
            from . import dashboard_server
        except ImportError:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            import dashboard_server
        sys.argv = ["facto-dashboard"] + argv[1:]
        dashboard_server.main()
        return 0

    # handoff guidato: in terminale, senza --file, si fanno 3 domande
    if cmd == "handoff" and len(argv) == 2 and sys.stdin.isatty():
        return _cmd_handoff_guided(argv[1])

    return _delegate(argv)


if __name__ == "__main__":
    sys.exit(main())
