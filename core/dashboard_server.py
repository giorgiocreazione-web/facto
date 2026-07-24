#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FACTO — server dashboard LIVE  (stdlib pura, zero dipendenze)
====================================================================
Legge il DB DAL VIVO e serve una dashboard a piu' viste:
  - Grafo dati (relazioni, stile Obsidian)
  - Progetti (log per progetto)
  - Struttura (anatomia di un fatto + ciclo bi-temporale)
  - Ripesca (ricerca FTS5 live = come l'agente trova un fatto tra tanti)
  - Bussola (le 8 sezioni che l'agente legge per un progetto)
  - Attivita' (scritture degli agenti in tempo reale)

Uso:
  python core/dashboard_server.py            # porta 8780, solo locale
  python core/dashboard_server.py --port 8790
  python core/dashboard_server.py --host 0.0.0.0   # esposta in rete (usa il controllo accessi!)

CONTROLLO ACCESSI (Pro, opzionale): se esiste pro/access ED almeno un utente
(`python pro/access/access.py add <utente>`), la dashboard richiede login e applica
lo SCOPING per progetto (ogni utente vede solo i suoi). In locale, senza utenti,
resta aperta come sempre. Import difensivo: il core non dipende dal Pro.

NON modifica mem.py (engine condiviso dalle sessioni): lo importa in sola lettura.
Tutto cio' che e' specifico del progetto arriva da facto.config.json via mem.py.
"""
import os, sys, json, time, sqlite3, argparse, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from . import mem            # installato come package `facto` (pip)
except ImportError:
    import mem                   # lanciato da cartella (repo/zip Pro)
# CRM (Pro): serve solo alla SCRITTURA di entita/task/relazioni dalla dashboard.
# Import difensivo: l'edizione core (senza pro/) resta perfettamente funzionante in lettura.
try:
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pro", "crm"))
    import crm as _crm
except Exception:
    _crm = None

# Backup & Notify (Pro): import DIFENSIVO e DOPO 'import mem' (cosi' mem.DB/CFG sono gia'
# corretti). L'edizione core senza pro/ resta funzionante (gli endpoint rispondono "non disponibile").
_PRO = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pro")
try:
    sys.path.insert(0, os.path.join(_PRO, "backup"))
    import backup as _backup
except Exception:
    _backup = None
try:
    sys.path.insert(0, os.path.join(_PRO, "notify"))
    import notify as _notify
except Exception:
    _notify = None

HERE = os.path.dirname(os.path.abspath(__file__))
# Edizione Pro: serve la dashboard premium "Mission Control" (Panoramica + Grafo)
HTML = os.path.join(HERE, "mission.html")   # UNA dashboard per tutti (Free e Pro)
_cache = {"t": 0.0, "git": "", "sem": None}
_cache_lock = threading.Lock()           # ThreadingHTTPServer: niente stampede sul ricalcolo git
_restore_lock = threading.Lock()         # single-flight del restore (operazione distruttiva)
_notify_cache = {"t": 0.0, "data": None}  # le allerte sono costose (git per area): cache TTL lunga

# Controllo accessi (Pro, OPZIONALE). Import difensivo: il core non dipende dal Pro.
# Si attiva DA SOLO se pro/access è presente E c'è almeno un utente; altrimenti la
# dashboard resta aperta (uso locale su 127.0.0.1, comportamento storico invariato).
try:
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), "pro", "access"))
    import access as _access
    _SESS = _access.Sessions()
except Exception:
    _access = None
    _SESS = None

def auth_on():
    return bool(_access and _access.auth_attiva())

def _visibile(prog, allowed):
    """allowed=None -> tutti. 'globale' (stato git) sempre visibile a chi è dentro."""
    return allowed is None or prog == "globale" or prog in allowed


def ro_con():
    con = sqlite3.connect(mem.DB, timeout=5.0)
    con.row_factory = sqlite3.Row
    return con


def git_parts(con):
    # double-check sotto lock: su ThreadingHTTPServer due richieste insieme non rispawnano git per area
    if time.time() - _cache["t"] < 5 and _cache["sem"] is not None:
        return _cache["git"], _cache["sem"]
    with _cache_lock:
        if time.time() - _cache["t"] < 5 and _cache["sem"] is not None:
            return _cache["git"], _cache["sem"]
        row = con.execute("SELECT contenuto FROM fatti WHERE progetto='globale' AND tipo='git'"
                          " AND valido_fino_a IS NULL").fetchone()
        gitline = row["contenuto"] if row else ""
        sem = {}
        rank = {"VERDE": 0, "GIALLO": 1, "ROSSO": 2}
        peggiore = "VERDE"
        for slug, path in mem.PROGETTI.items():
            try:
                c, det = mem.semaforo_progetto(con, slug, path)
            except Exception:
                c, det = "-", []
            sem[slug] = {"colore": c, "dettagli": det}
            if c in rank and rank[c] > rank[peggiore]:
                peggiore = c
        sem["_globale"] = peggiore
        _cache.update(t=time.time(), git=gitline, sem=sem)
        return gitline, sem


def build_notify():
    """Allerte di notify per il badge del cruscotto. Endpoint SEPARATO da /api/state
    (poll lento lato UI) + cache TTL: raccogli() RIUSA il semaforo gia' calcolato da
    git_parts, quindi NON ri-esegue git per area ad ogni richiesta."""
    if _notify is None:
        return {"disponibile": False, "count": 0, "allerte": []}
    with _cache_lock:                     # riusa il lock del semaforo per il double-check del TTL
        if _notify_cache["data"] is not None and time.time() - _notify_cache["t"] < 45:
            return _notify_cache["data"]
    con = ro_con()
    try:
        _, sem = git_parts(con)
        al = _notify.raccogli(con, sem)
        data = {"disponibile": True, "count": len(al),
                "allerte": [{"icona": a.get("icona", ""), "testo": a.get("testo", "")} for a in al]}
    except Exception as e:
        data = {"disponibile": False, "count": 0, "allerte": [], "errore": str(e)[:160]}
    finally:
        con.close()
    with _cache_lock:
        _notify_cache.update(t=time.time(), data=data)
    return data


def _fact(r):
    return {
        "id": r["id"], "progetto": r["progetto"], "tipo": r["tipo"],
        "testo": r["contenuto"], "vivo": r["valido_fino_a"] is None,
        "valido_da": r["valido_da"], "valido_fino_a": r["valido_fino_a"],
        "fonte": r["fonte"], "creato_il": r["creato_il"], "chiuso_il": r["chiuso_il"],
    }


def build_state(allowed=None):
    # L'agente puo' creare le aree MENTRE questa pagina e' aperta (e' proprio il
    # flusso dell'onboarding): rileggi il config se e' cambiato, altrimenti la
    # dashboard resta vuota per sempre.
    mem.ricarica_aree_se_cambiate()
    con = ro_con()
    try:
        gitline, sem = git_parts(con)
        fatti = [_fact(r) for r in con.execute(
            "SELECT id,progetto,tipo,contenuto,valido_da,valido_fino_a,fonte,creato_il,chiuso_il"
            " FROM fatti ORDER BY id")]
        if allowed is not None:                         # scoping per progetto (viewer ristretto)
            fatti = [f for f in fatti if _visibile(f["progetto"], allowed)]
        progetti_tutti = sorted({f["progetto"] for f in fatti})
        tipi_tutti = sorted({f["tipo"] for f in fatti})
        prog = []
        for slug in list(mem.PROGETTI.keys()) + ["globale"]:
            if not _visibile(slug, allowed):
                continue
            vivi = sum(1 for f in fatti if f["progetto"] == slug and f["vivo"])
            chiusi = sum(1 for f in fatti if f["progetto"] == slug and not f["vivo"])
            s = sem.get(slug, {"colore": "-", "dettagli": []})
            prog.append({"slug": slug, "semaforo": s["colore"], "dettagli": s["dettagli"],
                         "vivi": vivi, "chiusi": chiusi})
        tabelle = []
        for (nome,) in con.execute("SELECT name FROM sqlite_master WHERE type='table'"
                                   " AND name NOT LIKE 'sqlite_%'"
                                   " AND name NOT LIKE '%\\_fts\\_%' ESCAPE '\\' ORDER BY name"):
            cols = [{"nome": c["name"], "tipo": c["type"] or "?"}
                    for c in con.execute("PRAGMA table_info(%s)" % nome)]
            try:
                n = con.execute("SELECT COUNT(*) FROM %s" % nome).fetchone()[0]
            except Exception:
                n = None
            tabelle.append({"nome": nome, "colonne": cols, "righe": n})
        indici = [r["name"] for r in con.execute("SELECT name FROM sqlite_master WHERE type='index'"
                                                 " AND name NOT LIKE 'sqlite_%'")]
        trigger = [r["name"] for r in con.execute("SELECT name FROM sqlite_master WHERE type='trigger'")]
        vivi_tot = sum(1 for f in fatti if f["vivo"])
        eventi = []
        for f in fatti:
            azione = "handoff" if f["tipo"] == "handoff" else "nuovo"
            eventi.append({"ts": f["creato_il"], "azione": azione, "progetto": f["progetto"],
                           "tipo": f["tipo"], "testo": (f["testo"] or "")[:120], "id": f["id"]})
            if f["chiuso_il"]:
                eventi.append({"ts": f["chiuso_il"], "azione": "chiuso", "progetto": f["progetto"],
                               "tipo": f["tipo"], "testo": (f["testo"] or "")[:120], "id": f["id"]})
        eventi.sort(key=lambda e: (e["ts"] or ""), reverse=True)
        eventi = eventi[:60]
        return {
            "brand": mem.BRAND, "git_on": mem.GIT_ON,
            "ts": mem.now(), "git": gitline, "semaforo_globale": sem.get("_globale", "-"),
            "progetti": prog, "progetti_tutti": progetti_tutti, "tipi": tipi_tutti,
            "fatti": fatti, "tot_fatti": len(fatti), "vivi_tot": vivi_tot,
            "schema": {"tabelle": tabelle, "indici": indici, "trigger": trigger},
            "attivita": eventi,
        }
    finally:
        con.close()


def build_query(q, fprog, ftipo, fstato, allowed=None):
    """Replica esatta di cio' che fa l'agente con `mem.py query`: FTS5 MATCH + fallback LIKE."""
    con = ro_con()
    try:
        rows, modo = [], "tutti"
        if q:
            modo = "FTS5"
            try:
                rows = con.execute(
                    "SELECT f.id,f.progetto,f.tipo,f.contenuto,f.valido_da,f.valido_fino_a,f.fonte,"
                    "f.creato_il,f.chiuso_il, rank AS r FROM fatti_fts JOIN fatti f ON f.id=fatti_fts.rowid"
                    " WHERE fatti_fts MATCH ? ORDER BY rank", (q,)).fetchall()
            except sqlite3.OperationalError:
                modo = "LIKE (fallback)"
                rows = con.execute(
                    "SELECT id,progetto,tipo,contenuto,valido_da,valido_fino_a,fonte,creato_il,chiuso_il,"
                    "0 AS r FROM fatti WHERE contenuto LIKE ?", ("%" + q + "%",)).fetchall()
        else:
            rows = con.execute(
                "SELECT id,progetto,tipo,contenuto,valido_da,valido_fino_a,fonte,creato_il,chiuso_il,"
                "0 AS r FROM fatti ORDER BY id DESC").fetchall()
        out = []
        for i, r in enumerate(rows):
            f = _fact(r)
            if not _visibile(f["progetto"], allowed):    # scoping per progetto
                continue
            if fprog and f["progetto"] != fprog:
                continue
            if ftipo and f["tipo"] != ftipo:
                continue
            if fstato == "vivo" and not f["vivo"]:
                continue
            if fstato == "storia" and f["vivo"]:
                continue
            f["pos"] = i + 1
            out.append(f)
        return {"modo": modo, "q": q, "risultati": out[:80], "tot": len(out)}
    finally:
        con.close()


def build_brief(slug, allowed=None):
    """Assembla le 8 sezioni della BUSSOLA per un progetto: cio' che l'agente LEGGE all'apertura."""
    if not _visibile(slug, allowed):                     # progetto fuori dallo scope dell'utente
        return {"slug": slug, "negato": True, "git": "", "semaforo": None,
                "dettagli": [], "sezioni": [], "storia": []}
    con = ro_con()
    try:
        gitline, sem = git_parts(con)
        sezioni = []
        for chiave, titolo, perche, rows in mem.assembla_sezioni(con, slug):
            sezioni.append({"chiave": chiave, "titolo": titolo, "perche": perche,
                            "tipi": mem.tipi_di_tab(chiave), "fatti": [_fact(r) for r in rows]})
        storia = [_fact(r) for r in con.execute(
            "SELECT id,progetto,tipo,contenuto,valido_da,valido_fino_a,fonte,creato_il,chiuso_il"
            " FROM fatti WHERE progetto=? AND valido_fino_a IS NOT NULL ORDER BY chiuso_il DESC LIMIT 8",
            (slug,))]
        s = sem.get(slug)
        return {"slug": slug, "git": gitline,
                "semaforo": (s["colore"] if s else None),
                "dettagli": (s["dettagli"] if s else []),
                "sezioni": sezioni, "storia": storia}
    finally:
        con.close()


def build_crm():
    """Entità, task e scadenze dal CRM (tabelle aggiuntive). Tollera l'assenza delle tabelle."""
    con = ro_con()
    try:
        def q(sql):
            try: return con.execute(sql).fetchall()
            except sqlite3.OperationalError: return []
        ent = [dict(r) for r in q("SELECT id,tipo,nome,note FROM entita WHERE chiuso_il IS NULL ORDER BY tipo,nome")]
        tsk = [dict(r) for r in q("SELECT id,progetto,titolo,stato,scadenza,assegnatario FROM task"
                                  " ORDER BY stato='done', scadenza IS NULL, scadenza")]
        nomi = {e["id"]: e["nome"] for e in ent}
        for t in tsk:
            t["assegnatario_nome"] = nomi.get(t.get("assegnatario"))
        scad = [t for t in tsk if t.get("scadenza") and t.get("stato") != "done"]
        return {"entita": ent, "task": tsk, "scadenze": scad}
    finally:
        con.close()


def build_stats():
    """Serie temporali per la vista Statistiche, calcolate in SQL sul DB reale."""
    from datetime import date, timedelta
    con = ro_con()
    try:
        oggi = date.today()
        giorni = [(oggi - timedelta(days=i)).isoformat() for i in range(20, -1, -1)]
        fpd = {g: 0 for g in giorni}
        for d, n in con.execute("SELECT substr(valido_da,1,10) d, COUNT(*) n FROM fatti GROUP BY d"):
            if d in fpd: fpd[d] = n
        fatti_per_giorno = [{"g": g, "n": fpd[g]} for g in giorni]
        blocc = []
        for g in giorni:
            n = con.execute("SELECT COUNT(*) FROM fatti WHERE tipo='bloccante'"
                            " AND substr(valido_da,1,10)<=? AND (valido_fino_a IS NULL OR substr(valido_fino_a,1,10)>?)",
                            (g, g)).fetchone()[0]
            blocc.append({"g": g, "n": n})
        tps = {"todo": 0, "doing": 0, "done": 0}
        try:
            for st, n in con.execute("SELECT stato, COUNT(*) FROM task GROUP BY stato"):
                if st in tps: tps[st] = n
        except sqlite3.OperationalError:
            pass
        d7 = (oggi - timedelta(days=7)).isoformat(); d14 = (oggi - timedelta(days=14)).isoformat()
        rec = con.execute("SELECT COUNT(*) FROM fatti WHERE substr(creato_il,1,10)>?", (d7,)).fetchone()[0]
        prev = con.execute("SELECT COUNT(*) FROM fatti WHERE substr(creato_il,1,10)>? AND substr(creato_il,1,10)<=?",
                           (d14, d7)).fetchone()[0]
        pct = 0 if prev == 0 else round((rec - prev) / prev * 100)
        return {"fatti_per_giorno": fatti_per_giorno, "bloccanti": blocc,
                "task_per_stato": tps, "momentum": {"recenti": rec, "precedenti": prev, "pct": pct}}
    finally:
        con.close()


# ============================================================ SCRITTURA (dashboard interattiva)
# Gli endpoint POST /api/write/* costruiscono il Registro da browser. Riusano mem (fatti) e
# crm (entita/task/relazioni): nessuna logica duplicata. Protetti dal controllo accessi (solo admin).
def _rw():
    """Connessione in SCRITTURA con lo schema completo (fatti+FTS dal core, CRM additivo)."""
    con = mem.db()                       # makedirs + WAL + schema fatti + trigger FTS
    if _crm:
        con.executescript(_crm.SCHEMA)   # tabelle entita/task/relazioni (IF NOT EXISTS)
    return con

def _need(d, *campi):
    for c in campi:
        v = d.get(c)
        if v is None or (isinstance(v, str) and not v.strip()):
            raise ValueError(f"campo obbligatorio mancante: {c}")

def _crm_serve():
    if not _crm:
        raise ValueError("il layer CRM (pro/crm) non è disponibile in questa installazione")

def w_fatto(d):
    _need(d, "progetto", "tipo", "contenuto")
    con = _rw()
    mem.add_fatto(con, d["progetto"].strip(), d["tipo"].strip(), d["contenuto"].strip(),
                  (d.get("valido_da") or mem.today()), "dashboard")
    con.close()
    return {"msg": mem.T(f"fact «{d['tipo'].strip()}» added to {d['progetto'].strip()}",
                        f"fatto «{d['tipo'].strip()}» aggiunto a {d['progetto'].strip()}")}

def w_fatto_close(d):
    _need(d, "progetto", "tipo")
    con = _rw()
    q = "SELECT id FROM fatti WHERE progetto=? AND tipo=? AND valido_fino_a IS NULL"; pa = [d["progetto"].strip(), d["tipo"].strip()]
    like = (d.get("like") or "").strip()
    if like:
        q += " AND contenuto LIKE ?"; pa.append("%" + like + "%")
    ids = [r[0] for r in con.execute(q, pa)]
    for i in ids:
        con.execute("UPDATE fatti SET valido_fino_a=?, chiuso_il=? WHERE id=?", (mem.today(), mem.now(), i))
    con.commit(); con.close()
    return {"msg": mem.T(f"{len(ids)} fact(s) closed (kept in history)",
                        f"{len(ids)} fatto/i chiuso/i (restano nella storia)")}

def w_handoff(d):
    _need(d, "progetto", "testo")
    con = _rw()
    mem.upsert_singleton(con, d["progetto"].strip(), "handoff", d["testo"].strip(), mem.today(), "dashboard")
    con.close()
    return {"msg": mem.T(f"handoff updated for {d['progetto'].strip()}",
                        f"handoff aggiornato per {d['progetto'].strip()}")}

def w_entita(d):
    _crm_serve(); _need(d, "tipo", "nome")
    note = (d.get("note") or "").strip() or None
    con = _rw()
    cur = con.execute("INSERT INTO entita(tipo,nome,note,creato_il) VALUES(?,?,?,?)",
                      (d["tipo"].strip(), d["nome"].strip(), note, mem.now()))
    con.commit(); rid = cur.lastrowid; con.close()
    return {"msg": mem.T(f"entity «{d['nome'].strip()}» created",
                        f"entità «{d['nome'].strip()}» creata"), "id": rid}

def w_entita_close(d):
    _crm_serve(); _need(d, "id")
    con = _rw()
    con.execute("UPDATE entita SET chiuso_il=? WHERE id=?", (mem.now(), int(d["id"])))
    con.commit(); con.close()
    return {"msg": mem.T(f"entity #{int(d['id'])} archived", f"entità #{int(d['id'])} archiviata")}

def w_task(d):
    _crm_serve(); _need(d, "progetto", "titolo")
    per = d.get("per"); per = int(per) if per not in (None, "", "0", 0) else None
    scad = (d.get("scadenza") or "").strip() or None
    pri = (d.get("priorita") or "media").strip()
    con = _rw()
    cur = con.execute("INSERT INTO task(progetto,titolo,stato,assegnatario,scadenza,priorita,creato_il) VALUES(?,?,?,?,?,?,?)",
                      (d["progetto"].strip(), d["titolo"].strip(), "todo", per, scad, pri, mem.now()))
    con.commit(); rid = cur.lastrowid; con.close()
    return {"msg": mem.T(f"task «{d['titolo'].strip()}» created",
                        f"task «{d['titolo'].strip()}» creato"), "id": rid}

def w_task_stato(d):
    _crm_serve(); _need(d, "id", "stato")
    stato = d["stato"].strip()
    if stato not in ("todo", "doing", "done"):
        raise ValueError("stato non valido (todo|doing|done)")
    chiuso = mem.now() if stato == "done" else None
    con = _rw()
    con.execute("UPDATE task SET stato=?, chiuso_il=? WHERE id=?", (stato, chiuso, int(d["id"])))
    con.commit(); con.close()
    return {"msg": f"task #{int(d['id'])} → {stato}"}

def w_rel(d):
    _crm_serve(); _need(d, "da_tipo", "da_id", "rel", "a_tipo", "a_id")
    con = _rw()
    con.execute("INSERT INTO relazioni(da_tipo,da_id,rel,a_tipo,a_id,creato_il) VALUES(?,?,?,?,?,?)",
                (d["da_tipo"].strip(), int(d["da_id"]), d["rel"].strip(), d["a_tipo"].strip(), int(d["a_id"]), mem.now()))
    con.commit(); con.close()
    return {"msg": mem.T("relation created", "relazione creata")}

def _backup_serve():
    if _backup is None:
        raise ValueError("modulo backup non disponibile in questa edizione")

def w_backup_create(d):
    _backup_serve()
    r = _backup.take_snapshot()
    if not r.get("ok"):
        raise ValueError(r.get("errore", "snapshot fallito"))
    return {"msg": mem.T(f"snapshot created: {r['name']} ({r.get('size_human','')})",
                        f"snapshot creato: {r['name']} ({r.get('size_human','')})"), **r}

def w_backup_restore(d):
    """Ripristino: distruttivo. Conferma OBBLIGATORIA lato server (non bypassabile via fetch),
    single-flight, identita' per NOME. La sicurezza vera (lock esclusivo, replace atomico) e' in backup.restore_to."""
    _backup_serve()
    if (d.get("conferma") or "").strip() != "RIPRISTINA":
        raise ValueError("conferma mancante: per ripristinare invia conferma='RIPRISTINA'")
    if not _restore_lock.acquire(blocking=False):
        raise ValueError("un ripristino è già in corso, attendi")
    try:
        r = _backup.restore_to(d.get("which"))
    finally:
        _restore_lock.release()
    if not r.get("ok"):
        raise ValueError(r.get("errore", "ripristino fallito"))
    _cache.update(t=0.0)             # invalida le cache: il DB e' cambiato sotto i piedi
    _notify_cache.update(t=0.0, data=None)
    safety = (" · stato precedente salvato in %s" % r["safety"]) if r.get("safety") else ""
    return {"msg": mem.T(f"restored from {r['restored_from']}{safety}",
                        f"ripristinato da {r['restored_from']}{safety}"), **r}

def w_ingest_git(d):
    """Riallinea la memoria al repo reale — è l'ingest-git del core, dal browser.
    Scrive fatti 'stato', quindi vive tra le write (admin-only quando auth è on)."""
    con = _rw()
    mem.do_ingest_git(con, verbose=False)
    con.close()
    _cache.update(t=0.0)                 # il prossimo /api/state legge lo stato fresco
    return {"msg": mem.T("memory realigned to git", "memoria riallineata a git")}

def w_area(d):
    """Crea/aggiorna un'area DALLA DASHBOARD: chi non vive nel terminale deve
    poter disegnare la struttura del progetto come scrive un fatto."""
    slug, path, tot, nuovo, esiste = mem.add_area(d.get("slug"), d.get("path"), d.get("label"))
    warn = "" if esiste else mem.T("  (that folder does not exist yet)",
                                   "  (quella cartella non esiste ancora)")
    verbo = mem.T("added", "aggiunta") if nuovo else mem.T("updated", "aggiornata")
    return {"msg": mem.T(f"area «{slug}» {verbo} -> {path} [{tot} total]{warn}",
                         f"area «{slug}» {verbo} -> {path} [{tot} in tutto]{warn}")}


def w_area_remove(d):
    slug, tot = mem.remove_area(d.get("slug"))
    return {"msg": mem.T(f"area «{slug}» removed [{tot} left] — its facts stay in history",
                         f"area «{slug}» rimossa [restano {tot}] — i suoi fatti restano nella storia")}


_WRITE = {"fatto": w_fatto, "fatto-close": w_fatto_close, "handoff": w_handoff,
          "area": w_area, "area-remove": w_area_remove,
          "entita": w_entita, "entita-close": w_entita_close,
          "task": w_task, "task-stato": w_task_stato, "rel": w_rel,
          "backup-create": w_backup_create, "backup-restore": w_backup_restore,
          "ingest-git": w_ingest_git}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype):
        b = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(b)
        except (BrokenPipeError, ConnectionAbortedError):
            pass

    def _json(self, obj):
        self._send(200, json.dumps(obj, ensure_ascii=False), "application/json")

    # ---- controllo accessi (attivo solo quando auth_on()) ----
    def _current_user(self):
        if not _SESS:
            return None
        cookies = _access.parse_cookies(self.headers.get("Cookie", ""))
        return _SESS.get(cookies.get(_access.COOKIE_NAME))

    def _redirect(self, location, cookie=None):
        self.send_response(302)
        self.send_header("Location", location)
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _login_form(self, error=""):
        self._send(200, _access.login_page(error, mem.BRAND), "text/html")

    def do_POST(self):
        u = urlparse(self.path)
        if u.path == "/login":
            if not auth_on():
                return self._send(404, "not found", "text/plain")
            try:
                ln = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(ln).decode("utf-8", "replace")
            except Exception:
                body = ""
            form = parse_qs(body)
            user = _access.verify((form.get("username", [""])[0]).strip(), form.get("password", [""])[0])
            if not user:
                return self._login_form("Credenziali errate.")
            tok = _SESS.create(user)
            return self._redirect("/", cookie=f"{_access.COOKIE_NAME}={tok}; Path=/; HttpOnly; SameSite=Lax")
        if u.path.startswith("/api/write/"):
            return self._do_write(u.path[len("/api/write/"):])
        self._send(404, "not found", "text/plain")

    def _do_write(self, op):
        """Scrittura dalla dashboard. Con controllo accessi attivo, solo un admin scrive
        (viewer e non autenticati: 403/401). Senza utenti (uso locale) è libero su 127.0.0.1.

        Difesa CSRF (importante ora che esistono operazioni DISTRUTTIVE come backup-restore):
        se il browser invia un Origin, deve essere SAME-ORIGIN (== Host). Un sito esterno aperto
        nel browser non puo' cosi' colpire 127.0.0.1:porta con una POST cross-origin."""
        origin = self.headers.get("Origin")
        if origin:
            host = self.headers.get("Host", "")
            if origin not in ("http://" + host, "https://" + host):
                return self._send(403, json.dumps({"errore": "origine non consentita (CSRF)"}, ensure_ascii=False), "application/json")
        if auth_on():
            user = self._current_user()
            if not user:
                return self._send(401, json.dumps({"errore": "non autenticato"}), "application/json")
            if user.get("role") != "admin":
                return self._send(403, json.dumps({"errore": "serve un account admin per scrivere"}, ensure_ascii=False), "application/json")
        else:
            # FAIL-CLOSED (era fail-open, annotato in review): senza controllo accessi la
            # scrittura e' consentita SOLO da loopback. Esporre in rete richiede utenti.
            ip = (self.client_address or ("",))[0]
            if ip not in ("127.0.0.1", "::1", "localhost"):
                return self._send(403, json.dumps(
                    {"errore": "scrittura remota disabilitata: attiva il controllo accessi "
                               "(pro/access: crea un utente) per scrivere da altre macchine"},
                    ensure_ascii=False), "application/json")
        try:
            ln = int(self.headers.get("Content-Length") or 0)
            data = json.loads(self.rfile.read(ln).decode("utf-8", "replace") or "{}")
        except Exception:
            return self._send(400, json.dumps({"errore": "corpo non valido (atteso JSON)"}, ensure_ascii=False), "application/json")
        fn = _WRITE.get(op)
        if not fn:
            return self._send(404, json.dumps({"errore": f"operazione sconosciuta: {op}"}, ensure_ascii=False), "application/json")
        try:
            res = fn(data if isinstance(data, dict) else {})
            self._json({"ok": True, **res})
        except ValueError as e:
            self._send(400, json.dumps({"errore": str(e)}, ensure_ascii=False), "application/json")
        except Exception as e:
            self._send(500, json.dumps({"errore": str(e)}, ensure_ascii=False), "application/json")

    def do_GET(self):
        u = urlparse(self.path)
        p, qs = u.path, parse_qs(u.query)
        g = lambda k: (qs.get(k, [""])[0] or "").strip()
        allowed = None                                   # None = vede tutto (auth off, o admin/'*')
        user = None
        if auth_on():
            if p == "/login":
                return self._login_form()
            if p == "/logout":
                cookies = _access.parse_cookies(self.headers.get("Cookie", ""))
                _SESS.drop(cookies.get(_access.COOKIE_NAME))
                return self._redirect("/login", cookie=f"{_access.COOKIE_NAME}=; Path=/; Max-Age=0")
            user = self._current_user()
            if not user:                                 # non loggato: API->401, pagine->/login
                if p.startswith("/api"):
                    return self._send(401, json.dumps({"errore": "non autenticato"}), "application/json")
                return self._redirect("/login")
            allowed = _access.visible_projects(user)
        try:
            if p in ("/", "/index.html"):
                with open(HTML, encoding="utf-8") as fh:
                    self._send(200, fh.read(), "text/html")
            elif p == "/api/state":
                st = build_state(allowed)
                st["puo_scrivere"] = (not auth_on()) or bool(user and user.get("role") == "admin")
                # edizione: la UI mostra le viste Pro come card ONESTE nella Free
                st["edizione"] = "pro" if _crm else "free"
                self._json(st)
            elif p == "/api/query":
                self._json(build_query(g("q"), g("progetto"), g("tipo"), g("stato"), allowed))
            elif p == "/api/brief":
                primo = next(iter(mem.PROGETTI), "globale")
                self._json(build_brief(g("slug") or primo, allowed))
            elif p == "/api/crm":                        # vista aggregata: solo per chi vede tutto
                self._json(build_crm() if allowed is None
                           else {"entita": [], "task": [], "scadenze": [], "ristretto": True})
            elif p == "/api/stats":
                self._json(build_stats() if allowed is None
                           else {"fatti_per_giorno": [], "bloccanti": [],
                                 "task_per_stato": {"todo": 0, "doing": 0, "done": 0},
                                 "momentum": {"recenti": 0, "precedenti": 0, "pct": 0}, "ristretto": True})
            elif p == "/api/notify":                     # allerte per il badge (poll lento lato UI)
                self._json(build_notify() if allowed is None
                           else {"disponibile": True, "count": 0, "allerte": [], "ristretto": True})
            elif p == "/api/backup":                     # lista snapshot (operazioni write via /api/write/backup-*)
                if _backup is None:
                    self._json({"disponibile": False, "snapshots": []})
                else:
                    self._json({"disponibile": True, "snapshots": _backup.snapshots() if allowed is None else [],
                                "ristretto": allowed is not None})
            else:
                self._send(404, "not found", "text/plain")
        except FileNotFoundError:
            self._send(500, "mission.html mancante accanto a questo script", "text/plain")
        except Exception as e:
            self._send(500, json.dumps({"errore": str(e)}), "application/json")


class _ServerSenzaDNS(ThreadingHTTPServer):
    """server_bind SENZA getfqdn: su macOS (es. runner CI) il reverse-DNS del
    hostname puo' bloccare l'avvio per decine di secondi. Il nome non ci serve:
    il server e' locale per design."""
    def server_bind(self):
        import socketserver
        socketserver.TCPServer.server_bind(self)
        host, port = self.socket.getsockname()[:2]
        self.server_name = host
        self.server_port = port


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8780)
    ap.add_argument("--host", default="127.0.0.1",
                    help="127.0.0.1 = solo locale (default). 0.0.0.0 = esposta in rete (usa il controllo accessi!)")
    ap.add_argument("--no-open", action="store_true",
                    help="non aprire il browser da solo (CI/headless)")
    a = ap.parse_args()
    srv = _ServerSenzaDNS((a.host, a.port), Handler)
    url = "http://%s:%d/" % ("127.0.0.1" if a.host == "0.0.0.0" else a.host, a.port)
    print(f"{mem.BRAND} - dashboard LIVE")
    print("  apri nel browser:  " + url)
    print("  API:  /api/state  /api/query?q=  /api/brief?slug=")
    if auth_on():
        n = len(_access.load_users())
        print(f"  controllo accessi: ATTIVO ({n} utenti) — login su /login, esci con /logout")
    else:
        print("  controllo accessi: aperto (uso locale). Per condividerla:  python pro/access/access.py add <utente>")
        if a.host != "127.0.0.1":
            print("  \033[38;2;255;93;110m! ATTENZIONE: esposta in rete SENZA login. Crea utenti prima di esporla.\033[0m")
    print("  Ctrl-C per fermare.")
    if not a.no_open:
        try:
            import webbrowser
            webbrowser.open(url)   # stdlib: fa la cosa giusta su Windows/macOS/Linux
        except Exception:
            pass
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstop.")
        srv.shutdown()


if __name__ == "__main__":
    main()
