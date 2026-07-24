#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FACTO — MCP server (core, edizione Free e Pro)
==============================================
Espone la memoria del progetto come server MCP (Model Context Protocol): così
QUALSIASI agente che parla MCP — Claude Code, Claude Desktop, Cursor, ... —
può leggerla e scriverla via standard. È la "memoria universale per agenti".

Protocollo JSON-RPC 2.0 su stdio (un messaggio JSON per riga), stdlib pura.
Vive nel CORE: funziona nella Free da sola. I tool CRM compaiono solo se i
moduli Pro sono presenti (import difensivo): un agente della Free non vede
tool che non può usare.

Avvio (di norma è il CLIENT a lanciarlo come sottoprocesso):
  python core/mcp_server.py
Il config del progetto si trova via FACTO_CONFIG o risalendo dalla cwd.

REGOLA D'ORO di MCP su stdio: su stdout vanno SOLO messaggi JSON-RPC.
Ogni diagnostica va su stderr (vedi log()).
"""
import sys, os, json, sqlite3

try: sys.stdout.reconfigure(encoding="utf-8", newline="\n")
except Exception: pass
try: sys.stdin.reconfigure(encoding="utf-8")
except Exception: pass
try: sys.stderr.reconfigure(encoding="utf-8")
except Exception: pass

HERE = os.path.dirname(os.path.abspath(__file__))     # .../core (o site-packages/facto)
PKG  = os.path.dirname(HERE)
try:
    from . import mem                        # installato come package `facto` (pip)
    from . import dashboard_server as ds
except ImportError:
    sys.path.insert(0, HERE)                 # lanciato da cartella (repo/zip Pro)
    import mem                               # config/DB/etichette + add_fatto/upsert
    import dashboard_server as ds            # build_brief/build_query/build_crm

# CRM = modulo Pro: import difensivo. Senza, i tool CRM non vengono nemmeno esposti.
try:
    sys.path.insert(0, os.path.join(PKG, "pro", "crm"))
    import crm as _crm
except Exception:
    _crm = None

SERVER_NAME = "facto"
VERSION = "1.2.0"
PROTOCOL = "2024-11-05"


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def send(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def reply(rid, result):
    send({"jsonrpc": "2.0", "id": rid, "result": result})


def reply_error(rid, code, message):
    send({"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}})


# ============================  DEFINIZIONE DEI TOOL  ============================
# Nomi e descrizioni in INGLESE: sono l'API che vede l'agente del cliente.
# I VALORI dei tipi restano gli slug del motore (stato, decisione, ...): sono
# identificatori di storage; le etichette localizzate sono presentazione.
def _obj(props, required=()):
    return {"type": "object", "properties": props, "required": list(required), "additionalProperties": False}

TIPI_FATTO = "stato|obiettivo|rotta|nota|operativo|bloccante|bug|decisione|vincolo|preferenza"

CORE_TOOLS = [
    {"name": "facto_status",
     "description": "Overview of ALL project areas: current state, trust light (green/yellow/red vs git) and open blockers. Use it to orient yourself.",
     "inputSchema": _obj({})},
    {"name": "facto_brief",
     "description": "Briefing of one area: the compass sections (goal, where we are, last handoff, next steps, how-we-work, blockers, bugs, decisions). Without 'area' it lists the available areas.",
     "inputSchema": _obj({"area": {"type": "string", "description": "area slug (e.g. core)"}})},
    {"name": "facto_search",
     "description": "Full-text search across the project memory. Returns matching facts, marking whether each is true NOW or historical.",
     "inputSchema": _obj({"text": {"type": "string", "description": "words to search"}}, ["text"])},
    {"name": "facto_add_fact",
     "description": f"Record a new dated FACT in an area. type = {TIPI_FATTO}. The fact stays 'true now' until it gets closed.",
     "inputSchema": _obj({"area": {"type": "string"}, "type": {"type": "string"},
                          "text": {"type": "string"},
                          "date": {"type": "string", "description": "ISO date YYYY-MM-DD (default: today)"}},
                         ["area", "type", "text"])},
    {"name": "facto_close_fact",
     "description": "Close (NOT delete: history is kept) the open facts of a type in an area. 'contains' narrows by text.",
     "inputSchema": _obj({"area": {"type": "string"}, "type": {"type": "string"},
                          "contains": {"type": "string"}}, ["area", "type"])},
    {"name": "facto_handoff",
     "description": "Save the end-of-session HANDOFF for an area: what was done + where you were heading, so the next session resumes exactly. Replaces the previous one (kept in history).",
     "inputSchema": _obj({"area": {"type": "string"}, "text": {"type": "string"}}, ["area", "text"])},
    {"name": "facto_add_area",
     "description": "Define a project AREA (a logical module) — writes it into facto.config.json. Use during SETUP, one call per area, AFTER the human confirmed the structure. slug = short semantic name (e.g. 'factory', not '01_generatore-siti-astro'); path = the real folder (may be nested, e.g. 'code/01_thing'); label = readable name.",
     "inputSchema": _obj({"slug": {"type": "string"}, "path": {"type": "string"},
                          "label": {"type": "string"}}, ["slug", "path"])},
    {"name": "facto_remove_area",
     "description": "Remove an AREA from facto.config.json (e.g. a test area created by mistake). Its facts stay in history. Confirm with the human first.",
     "inputSchema": _obj({"slug": {"type": "string"}}, ["slug"])},
]

CRM_TOOLS = [
    {"name": "facto_crm",
     "description": "Project CRM: entities (people, clients, milestones), tasks with status and overdue deadlines.",
     "inputSchema": _obj({})},
    {"name": "facto_add_entity",
     "description": "Add a CRM entity: type = persona|cliente|milestone|risorsa|fonte, with a name and an optional note.",
     "inputSchema": _obj({"type": {"type": "string"}, "name": {"type": "string"},
                          "note": {"type": "string"}}, ["type", "name"])},
    {"name": "facto_add_task",
     "description": "Add a TASK in an area, with optional due date (YYYY-MM-DD) and status todo|doing|done.",
     "inputSchema": _obj({"area": {"type": "string"}, "title": {"type": "string"},
                          "due": {"type": "string"}, "status": {"type": "string"}},
                         ["area", "title"])},
]

TOOLS = CORE_TOOLS + (CRM_TOOLS if _crm else [])


# ============================  IMPLEMENTAZIONE  ============================
def _ro():
    # mem.db() garantisce lo schema (un progetto appena creato non ha ancora il DB).
    # row_factory=Row: t_status legge le colonne per NOME (r['contenuto']) — senza
    # questo, su un progetto con git+stato, esplode "tuple indices must be...".
    con = mem.db()
    con.row_factory = sqlite3.Row
    return con

def _sem_glyph(c):
    return {"VERDE": "🟢", "GIALLO": "🟡", "ROSSO": "🔴"}.get(c, "⚪")


def t_status(_):
    con = _ro()
    try:
        righe = [f"# {mem.BRAND} — all areas", ""]
        gr = con.execute("SELECT contenuto FROM fatti WHERE progetto='globale' AND tipo='git'"
                         " AND valido_fino_a IS NULL").fetchone()
        if gr:
            righe.append(f"git: {gr['contenuto']}")
        for slug, path in mem.PROGETTI.items():
            sem, det = mem.semaforo_progetto(con, slug, path)
            st = con.execute("SELECT contenuto FROM fatti WHERE progetto=? AND tipo='stato'"
                             " AND valido_fino_a IS NULL ORDER BY valido_da DESC LIMIT 1", (slug,)).fetchone()
            nb = con.execute("SELECT COUNT(*) FROM fatti WHERE progetto=? AND tipo='bloccante'"
                             " AND valido_fino_a IS NULL", (slug,)).fetchone()[0]
            extra = f"  ⚠ {nb} open blockers" if nb else ""
            righe.append(f"{_sem_glyph(sem)} {mem.LABELS.get(slug, slug)} [{slug}]: "
                         f"{st['contenuto'] if st else '(no status yet)'}{extra}")
        return "\n".join(righe)
    finally:
        con.close()


def t_brief(args):
    area = (args.get("area") or "").strip()
    if not area:
        elenco = "\n".join(f"- {slug}: {mem.LABELS.get(slug, slug)}" for slug in mem.PROGETTI)
        return "Specify an area. Available areas:\n" + elenco
    if area not in mem.PROGETTI:
        return f"Unknown area: {area}. Available: {', '.join(mem.PROGETTI)}"
    b = ds.build_brief(area)
    out = [f"# Brief — {mem.LABELS.get(area, area)} [{area}]"]
    if b.get("semaforo"):
        out.append(f"trust light: {_sem_glyph(b['semaforo'])} {b['semaforo']}"
                   + (f" ({', '.join(b['dettagli'])})" if b.get("dettagli") else ""))
    for s in b["sezioni"]:
        if not s["fatti"]:
            continue
        out.append(f"\n## {s['titolo']}")
        for f in s["fatti"]:
            out.append(f"- {f['testo']}  ({f['valido_da']} · {f['fonte']})")
    if len(out) <= 2:
        out.append("\n(no facts in this area yet)")
    return "\n".join(out)


def t_search(args):
    q = (args.get("text") or "").strip()
    if not q:
        return "Specify the text to search."
    r = ds.build_query(q, "", "", "")
    if not r["risultati"]:
        return f'No facts found for "{q}".'
    out = [f'Results for "{q}" ({r["tot"]}, mode {r["modo"]}):']
    for f in r["risultati"]:
        stato = "TRUE NOW" if f["vivo"] else f"historical, closed {f['valido_fino_a']}"
        out.append(f"- [{f['progetto']}/{f['tipo']}] <{stato}> {f['testo']}")
    return "\n".join(out)


def _fonte():
    """Attribuzione della scrittura: l'orchestratore setta FACTO_FONTE='agente:<slug>'
    quando spawna un agente; un uso normale (umano/editor) resta 'mcp'."""
    return (os.environ.get("FACTO_FONTE") or os.environ.get("REGISTRO_FONTE")) or "mcp"


def _scope_area(area):
    """Confinamento dell'agente: se FACTO_AREA e' settata (agente spawnato
    dall'orchestratore) puo' scrivere SOLO in quell'area, mai nella missione
    globale ('progetto'/'globale'). Senza FACTO_AREA non cambia nulla."""
    scope = (os.environ.get("FACTO_AREA") or os.environ.get("REGISTRO_AREA"))
    if scope:
        if area in ("progetto", "globale"):
            raise ValueError(f"protected area: an agent cannot write to [{area}] (global mission)")
        if area != scope:
            raise ValueError(f"this agent can only write to [{scope}], not [{area}]")
    return area


def t_add_fact(args):
    area, tipo, testo = args.get("area"), args.get("type"), args.get("text")
    if not (area and tipo and testo):
        raise ValueError("'area', 'type' and 'text' are required")
    da = (args.get("date") or mem.today()).strip()
    area = _scope_area(area)
    con = mem.db()
    try:
        mem.add_fatto(con, area, tipo, testo, da, _fonte())
    finally:
        con.close()
    k = mem.tab_di(tipo, testo)
    tab = next((t for kk, t, _ in mem.BUSSOLA if kk == k), "operativo")
    return f"✓ fact recorded in [{area}/{tipo}] (valid from {da}) → section «{tab}»"


def t_close_fact(args):
    area, tipo = args.get("area"), args.get("type")
    if not (area and tipo):
        raise ValueError("'area' and 'type' are required")
    contiene = args.get("contains")
    area = _scope_area(area)
    con = mem.db()
    try:
        q = "SELECT id FROM fatti WHERE progetto=? AND tipo=? AND valido_fino_a IS NULL"
        p = [area, tipo]
        if contiene:
            q += " AND contenuto LIKE ?"; p.append(f"%{contiene}%")
        ids = [r[0] for r in con.execute(q, p)]
        for fid in ids:
            con.execute("UPDATE fatti SET valido_fino_a=?, chiuso_il=? WHERE id=?",
                        (mem.today(), mem.now(), fid))
        con.commit()
    finally:
        con.close()
    return f"✓ closed {len(ids)} facts [{area}/{tipo}] (history is kept)"


def t_handoff(args):
    area, testo = args.get("area"), args.get("text")
    if not (area and testo):
        raise ValueError("'area' and 'text' are required")
    area = _scope_area(area)
    con = mem.db()
    try:
        esito = mem.upsert_singleton(con, area, "handoff", testo.strip(), mem.today(), _fonte())
    finally:
        con.close()
    return f"✓ handoff saved for [{area}] ({esito}, {len(testo)} chars)"


def t_add_area(args):
    """Stessa identica implementazione del CLI (`facto add-area`): una sola
    funzione, in mem — due copie divergerebbero al primo cambiamento."""
    slug, path, tot, nuovo, esiste = mem.add_area(
        args.get("slug"), args.get("path"), args.get("label"))
    warn = "" if esiste else "  (note: that folder doesn't exist yet)"
    verbo = "added" if nuovo else "updated"
    return f"✓ area '{slug}' {verbo} -> {path} [{tot} areas total]{warn}"


def t_remove_area(args):
    """Rimuove un'area dal config (CLI `facto remove-area`). I fatti restano
    nella storia. Serve all'agente per proporre «tolgo le aree di prova?»."""
    slug, tot = mem.remove_area(args.get("slug"))
    return f"✓ area '{slug}' removed [{tot} areas left] (its facts stay in history)"


def t_crm_view(_):
    d = ds.build_crm()
    out = ["# CRM"]
    if d["entita"]:
        out.append("\n## Entities")
        for e in d["entita"]:
            out.append(f"- {e['nome']} ({e['tipo']})" + (f" — {e['note']}" if e.get("note") else ""))
    if d["task"]:
        out.append("\n## Tasks")
        oggi = mem.today()
        for t in d["task"]:
            sc = ""
            if t.get("scadenza"):
                late = t["scadenza"] < oggi and t["stato"] != "done"
                sc = f"  due {t['scadenza']}" + (" (OVERDUE)" if late else "")
            who = f"  →{t['assegnatario_nome']}" if t.get("assegnatario_nome") else ""
            out.append(f"- [{t['stato']}] {t['titolo']} [{t['progetto']}]{sc}{who}")
    if not d["entita"] and not d["task"]:
        out.append("(CRM is empty)")
    return "\n".join(out)


def t_add_entity(args):
    tipo, nome = args.get("type"), args.get("name")
    if not (tipo and nome):
        raise ValueError("'type' and 'name' are required")
    c = _crm.con()
    try:
        cur = c.execute("INSERT INTO entita(tipo,nome,note,creato_il) VALUES(?,?,?,?)",
                        (tipo, nome, args.get("note"), mem.now()))
        c.commit(); rid = cur.lastrowid
    finally:
        c.close()
    return f"✓ entity #{rid} added: {nome} ({tipo})"


def t_add_task(args):
    area, titolo = args.get("area"), args.get("title")
    if not (area and titolo):
        raise ValueError("'area' and 'title' are required")
    stato = args.get("status") or "todo"
    area = _scope_area(area)
    c = _crm.con()
    try:
        chiuso = mem.now() if stato == "done" else None
        cur = c.execute("INSERT INTO task(progetto,titolo,stato,scadenza,priorita,creato_il,chiuso_il) "
                        "VALUES(?,?,?,?,?,?,?)",
                        (area, titolo, stato, args.get("due"), "media", mem.now(), chiuso))
        c.commit(); rid = cur.lastrowid
    finally:
        c.close()
    sc = f" · due {args['due']}" if args.get("due") else ""
    return f"✓ task #{rid} added in [{area}]: {titolo} [{stato}]{sc}"


DISPATCH = {
    "facto_status": t_status, "facto_brief": t_brief, "facto_search": t_search,
    "facto_add_fact": t_add_fact, "facto_close_fact": t_close_fact, "facto_handoff": t_handoff,
    "facto_add_area": t_add_area, "facto_remove_area": t_remove_area,
}
if _crm:
    DISPATCH.update({"facto_crm": t_crm_view, "facto_add_entity": t_add_entity,
                     "facto_add_task": t_add_task})


# ============================  ROUTING JSON-RPC / MCP  ============================
def call_tool(params):
    # Il config si carica all'IMPORT: questo processo e' partito quando il
    # progetto era ancora vuoto, quindi senza rilettura le aree create durante
    # la sessione non esisterebbero MAI per lui — facto_brief e facto_status
    # risponderebbero "Unknown area" mentre il CLI (processo nuovo ogni volta)
    # le vede benissimo. E' esattamente il flusso dell'onboarding: l'agente
    # crea le aree e subito dopo prova a leggerle.
    try:
        mem.ricarica_aree_se_cambiate()
    except Exception:
        pass                     # una rilettura fallita non deve mai bloccare un tool
    name = params.get("name")
    args = params.get("arguments") or {}
    fn = DISPATCH.get(name)
    if not fn:
        return {"content": [{"type": "text", "text": f"unknown tool: {name}"}], "isError": True}
    try:
        testo = fn(args)
        return {"content": [{"type": "text", "text": testo}]}
    except Exception as e:
        log(f"tool {name} failed: {e}")
        return {"content": [{"type": "text", "text": f"error: {e}"}], "isError": True}


def handle(method, params, rid):
    if method == "initialize":
        pv = params.get("protocolVersion") or PROTOCOL      # echo: massima compatibilità col client
        reply(rid, {"protocolVersion": pv, "capabilities": {"tools": {}},
                    "serverInfo": {"name": SERVER_NAME, "version": VERSION}})
    elif method == "tools/list":
        reply(rid, {"tools": TOOLS})
    elif method == "tools/call":
        reply(rid, call_tool(params))
    elif method == "ping":
        reply(rid, {})
    elif method == "resources/list":
        reply(rid, {"resources": []})
    elif method == "prompts/list":
        reply(rid, {"prompts": []})
    else:
        reply_error(rid, -32601, f"unhandled method: {method}")


def main():
    log(f"{SERVER_NAME} MCP server v{VERSION} — DB: {mem.DB} — tools: {len(TOOLS)}")
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            reply_error(None, -32700, "parse error")
            continue
        method = msg.get("method")
        rid = msg.get("id")
        params = msg.get("params") or {}
        if rid is None:           # notifica (es. notifications/initialized): nessuna risposta
            continue
        try:
            handle(method, params, rid)
        except Exception as e:
            log(f"internal error on {method}: {e}")
            reply_error(rid, -32603, f"internal error: {e}")


if __name__ == "__main__":
    main()
