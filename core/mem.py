#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FACTO — motore di memoria per agenti (stdlib pura)
==========================================================
Memoria a FATTI DATATI: sa cosa e' vero ADESSO. Se il progetto usa git, lo
stato si auto-verifica leggendo il repo reale; altrimenti lo stato si tiene a mano.

- Zero dipendenze: solo `sqlite3` + `subprocess` (stdlib). Nessun pip, nessun cloud.
- Una sola fonte di verita': il DB SQLite indicato nel config (ispezionabile con DB Browser for SQLite).
- Bi-temporale: un fatto nuovo CHIUDE il vecchio (valido_fino_a), non lo cancella.
- Tutto cio' che e' specifico del TUO progetto vive in `facto.config.json`
  (nomi, percorsi, git on/off). Il motore resta neutro e riusabile ovunque.

Comandi:
  python mem.py init                       # crea il DB
  python mem.py ingest-git                 # cattura lo stato reale da git (se abilitato)
  python mem.py brief <progetto>           # briefing di un progetto
  python mem.py dashboard                  # vista sintetica di tutti i progetti
  python mem.py health                     # semaforo di fiducia (verde/giallo/rosso)
  python mem.py dashboard-html             # genera una dashboard HTML statica
  python mem.py session-start --cwd <PATH> # usato dall'hook: ingest + briefing del progetto rilevato
  python mem.py query <testo...>           # ricerca testuale (FTS5)
  python mem.py add <prog> <tipo> <testo...> [--da DATA] [--fonte F]
  python mem.py close <prog> <tipo> [--like TXT]
  python mem.py handoff <prog> [--file F]  # salva il testimone di fine sessione

Config: cercato in $FACTO_CONFIG, poi risalendo da CWD, poi accanto a questo script.
"""
import sqlite3, subprocess, sys, os, re, json, argparse
from datetime import datetime, date

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
try:
    sys.stdin.reconfigure(encoding="utf-8")   # handoff via stdin: non corrompere i non-ASCII su Windows (cp1252)
except Exception:
    pass


# ======================  CONFIGURAZIONE  ======================
# Tutto cio' che era hardcoded (path, progetti, brand) ora viene da facto.config.json.
# Cosi' lo stesso motore serve QUALSIASI progetto: basta cambiare il file di config.

# ======================  LINGUA  ======================
# EN-first: l'inglese e' la lingua pubblica del prodotto; l'italiano resta
# completo con FACTO_LANG=it. T(en, it) tiene le due versioni ADIACENTI nel
# codice: niente dizionari lontani, niente chiavi orfane.
LANG = ((os.environ.get("FACTO_LANG") or os.environ.get("REGISTRO_LANG") or "en").strip().lower()[:2])

def T(en, it):
    return it if LANG == "it" else en


def _trova_config():
    """Ordine di ricerca: $FACTO_CONFIG -> risali da CWD -> accanto allo script."""
    env = (os.environ.get("FACTO_CONFIG") or os.environ.get("REGISTRO_CONFIG"))
    if env and os.path.isfile(env):
        return os.path.abspath(env)
    d = os.getcwd()
    while True:
        cand = os.path.join(d, "facto.config.json")
        if os.path.isfile(cand):
            return cand
        nd = os.path.dirname(d)
        if nd == d:
            break
        d = nd
    cand = os.path.join(os.path.dirname(os.path.abspath(__file__)), "facto.config.json")
    return cand if os.path.isfile(cand) else None


def _esci_senza_config():
    print(T("ERROR: no 'facto.config.json' found.\n"
            "  Run `facto init` in your project folder to create one, or point the\n"
            "  FACTO_CONFIG environment variable at it.\n"
            "  Start from 'facto.config.example.json' (see docs/SETUP.md).\n"
            "  Minimal example:",
            "ERRORE: non trovo 'facto.config.json'.\n"
            "  Lancia `facto init` nella cartella del progetto per crearlo, oppure indica\n"
            "  il percorso con la variabile d'ambiente FACTO_CONFIG.\n"
            "  Parti da 'facto.config.example.json' (vedi docs/SETUP.md).\n"
            "  Esempio minimo:"))
    print('    { "brand": "My Project", "db_path": ".facto/facto.db",\n'
          '      "git": { "enabled": true },\n'
          '      "projects": { "core": { "path": "src", "label": "Core" } } }')
    sys.exit(2)


def _carica_config():
    p = _trova_config()
    if not p:
        db = (os.environ.get("FACTO_DB") or os.environ.get("REGISTRO_DB"))
        if db:                                   # DB esplicito senza config di progetto (es. sync.py --db su un altro DB)
            d = os.path.dirname(os.path.abspath(db)) or "."
            return {"brand": "Facto", "root": ".", "db_path": os.path.basename(db),
                    "git": {"enabled": False}, "projects": {}, "_path": None, "_dir": d}
        _esci_senza_config()
    try:
        with open(p, encoding="utf-8-sig") as fh:   # utf-8-sig: tollera il BOM che gli editor Windows aggiungono
            cfg = json.load(fh)
    except (json.JSONDecodeError, OSError) as e:
        print(f"ERRORE: '{p}' non e' un JSON valido: {e}")
        sys.exit(2)
    cfg["_path"] = p
    cfg["_dir"] = os.path.dirname(p)
    return cfg


CFG = _carica_config()

# root del progetto: relativa al file di config (default = cartella del config).
ROOT = os.path.abspath(os.path.join(CFG["_dir"], CFG.get("root", ".")))

def _default_db_path():
    """Default '.facto/facto.db'; se esiste il layout legacy '_memoria/facto.db'
    (installazioni nate prima del rename) continua a usare quello: zero migrazioni."""
    legacy = os.path.join(ROOT, "_memoria", "facto.db")
    return "_memoria/facto.db" if os.path.isfile(legacy) else ".facto/facto.db"

DB = os.path.abspath(os.path.join(ROOT, CFG.get("db_path") or _default_db_path()))
BRAND = CFG.get("brand", "Facto")

_git_cfg = CFG.get("git", {}) if isinstance(CFG.get("git"), dict) else {}
GIT_ON = bool(_git_cfg.get("enabled", True))
MAIN_BRANCH = _git_cfg.get("main_branch", "main")

# progetti: slug -> {path, label}. PROGETTI tiene slug->path (come l'API interna si aspetta),
# LABELS tiene le etichette leggibili.
_prj = CFG.get("projects", {})
PROGETTI = {slug: info["path"] for slug, info in _prj.items()}
LABELS = {slug: (info.get("label") or slug) for slug, info in _prj.items()}

_CFG_MTIME = None


def ricarica_aree_se_cambiate():
    """Rilegge le AREE dal config se il file è cambiato da sotto.

    Serve al caso più importante del prodotto: la dashboard è aperta sul progetto
    vuoto mentre l'agente, in un'altra finestra, crea le aree dell'onboarding.
    Senza questo il config viene letto una volta sola all'avvio del processo e la
    pagina resterebbe vuota PER SEMPRE — con scritto "si aggiorna da sola".
    Ricarica solo aree ed etichette: percorso del DB e root non cambiano a caldo.
    Ritorna True se qualcosa è cambiato."""
    global PROGETTI, LABELS, _CFG_MTIME
    p = CFG.get("_path")
    if not p or not os.path.isfile(p):
        return False
    try:
        m = os.path.getmtime(p)
    except OSError:
        return False
    if _CFG_MTIME is None:
        _CFG_MTIME = m
        return False
    if m == _CFG_MTIME:
        return False
    _CFG_MTIME = m
    try:
        with open(p, encoding="utf-8-sig") as fh:
            prj = (json.load(fh) or {}).get("projects", {}) or {}
    except Exception:
        return False                      # config a metà scrittura: riprovo al giro dopo
    nuovi = {s: i["path"] for s, i in prj.items() if isinstance(i, dict) and i.get("path")}
    if nuovi == PROGETTI:
        return False
    PROGETTI = nuovi
    LABELS = {s: (i.get("label") or s) for s, i in prj.items() if isinstance(i, dict)}
    return True


# self_project (opzionale): traccia il sistema-memoria stesso o qualunque cartella
# che non vuoi nel semaforo/dashboard ma di cui vuoi lo "stato" (es. una cartella di tooling/build).
SELF = CFG.get("self_project") if isinstance(CFG.get("self_project"), dict) else None

# file d'identita' letti SEMPRE all'apertura (mission, regole...). Path relativi a ROOT. Opzionale.
IDENTITY = CFG.get("identity_files", []) or []


# ======================  SCHEMA  ======================
SCHEMA = """
CREATE TABLE IF NOT EXISTS fatti (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  progetto      TEXT NOT NULL,          -- <slug progetto> | globale
  tipo          TEXT NOT NULL,          -- stato|git|bloccante|decisione|bug|pattern|preferenza|identita|...
  contenuto     TEXT NOT NULL,
  valido_da     TEXT NOT NULL,          -- quando e' diventato vero (tempo del MONDO)
  valido_fino_a TEXT,                   -- NULL = vero ORA; data = superato
  fonte         TEXT,                   -- git:<hash> | gio | <chi> | sessione:<id>
  confidenza    REAL DEFAULT 1.0,
  scade_il      TEXT,                   -- NULL = non scade (TTL/forgetting)
  creato_il     TEXT NOT NULL,          -- quando REGISTRATO (tempo del SISTEMA)
  chiuso_il     TEXT                    -- quando INVALIDATO (tempo del SISTEMA)
);
CREATE INDEX IF NOT EXISTS i_vivo ON fatti(progetto, valido_fino_a);
CREATE VIRTUAL TABLE IF NOT EXISTS fatti_fts USING fts5(contenuto, content='fatti', content_rowid='id');
CREATE TRIGGER IF NOT EXISTS fatti_ai AFTER INSERT ON fatti BEGIN
  INSERT INTO fatti_fts(rowid, contenuto) VALUES (new.id, new.contenuto);
END;
CREATE TRIGGER IF NOT EXISTS fatti_ad AFTER DELETE ON fatti BEGIN
  INSERT INTO fatti_fts(fatti_fts, rowid, contenuto) VALUES('delete', old.id, old.contenuto);
END;
"""

def now():   return datetime.now().strftime("%Y-%m-%d %H:%M")
def today(): return date.today().isoformat()

def git(*args):
    r = subprocess.run(["git", "-C", ROOT, *args],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.stdout.strip()

def db():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    con = sqlite3.connect(DB, timeout=5.0)         # attende se il DB e' occupato (sessioni parallele)
    con.execute("PRAGMA journal_mode=WAL")         # letture concorrenti anche durante una scrittura
    con.execute("PRAGMA busy_timeout=5000")
    con.executescript(SCHEMA)
    return con

def add_fatto(con, progetto, tipo, contenuto, valido_da, fonte, valido_fino_a=None, scade_il=None):
    con.execute(
        "INSERT INTO fatti(progetto,tipo,contenuto,valido_da,valido_fino_a,fonte,creato_il,chiuso_il,scade_il)"
        " VALUES(?,?,?,?,?,?,?,?,?)",
        (progetto, tipo, contenuto, valido_da, valido_fino_a, fonte, now(),
         (now() if valido_fino_a else None), scade_il))
    con.commit()

def chiudi_fatti(con, progetto, tipo, data_chiusura):
    """Il nuovo chiude il vecchio: invalida i fatti 'vero ora' di quel tipo, NON li cancella."""
    ids = [r[0] for r in con.execute(
        "SELECT id FROM fatti WHERE progetto=? AND tipo=? AND valido_fino_a IS NULL", (progetto, tipo))]
    for fid in ids:
        con.execute("UPDATE fatti SET valido_fino_a=?, chiuso_il=? WHERE id=?", (data_chiusura, now(), fid))
    con.commit()
    return len(ids)

def branch_di(h):
    """Su quale branch vive davvero un commit? Evidenzia se NON e' sul branch principale."""
    if git("branch", "--contains", h, "--list", MAIN_BRANCH).strip():
        return MAIN_BRANCH
    altri = [b.strip().lstrip("* ").strip() for b in git("branch", "--contains", h).splitlines()]
    altri = [b for b in altri if b and "(" not in b and b != MAIN_BRANCH]
    return altri[0] if altri else "?"

def rileva_progetto(cwd):
    """Quale progetto sto guardando, dato un percorso? Match sul path configurato piu' specifico."""
    c = os.path.abspath(cwd or ROOT).replace("/", "\\").lower()
    best, best_len = None, -1
    for slug, path in PROGETTI.items():
        ap = os.path.abspath(os.path.join(ROOT, path)).replace("/", "\\").lower()
        if (c == ap or c.startswith(ap + "\\")) and len(ap) > best_len:
            best, best_len = slug, len(ap)
    return best

# ---------- logica condivisa ----------
def upsert_singleton(con, progetto, tipo, contenuto, valido_da, fonte):
    """Fatti 'singleton' (UN solo stato corrente per progetto): aggiorna solo se CAMBIATO.
    Idempotente: se il contenuto e' identico non tocca nulla -> niente duplicati ad ogni apertura.
    Se il fatto e' git-derivato (fonte 'git:...') BONIFICA anche i git-derivati gia' aperti dello
    stesso tipo (duplicati esatti + commit superati) tenendone UNO solo; gli stati depositati a mano
    (fonte non-git) restano intatti. Il ramo non-git e' invariato (handoff ecc.)."""
    vivi = con.execute(
        "SELECT id,contenuto,fonte FROM fatti WHERE progetto=? AND tipo=? AND valido_fino_a IS NULL"
        " ORDER BY id DESC", (progetto, tipo)).fetchall()
    if (fonte or "").startswith("git:"):
        visto_uguale = False
        for fid, c, f in vivi:
            if not (f or "").startswith("git:"):
                continue                                     # preserva gli stati a mano
            if c == contenuto and not visto_uguale:
                visto_uguale = True; continue                # tiene UNO identico
            con.execute("UPDATE fatti SET valido_fino_a=?, chiuso_il=? WHERE id=?", (valido_da, now(), fid))
        if visto_uguale:
            con.commit(); return "invariato"
        add_fatto(con, progetto, tipo, contenuto, valido_da, fonte)
        return "aggiornato"
    cur = vivi[0] if vivi else None                          # ramo classico (fonti non-git)
    if cur and cur[1] == contenuto:
        return "invariato"
    if cur:                                                   # cambiato: chiudi il vecchio
        con.execute("UPDATE fatti SET valido_fino_a=?, chiuso_il=? WHERE id=?", (valido_da, now(), cur[0]))
    add_fatto(con, progetto, tipo, contenuto, valido_da, fonte)
    return "aggiornato" if cur else "nuovo"

def esito_t(esito):
    """Gli esiti di upsert_singleton sono CHIAVI interne (stringhe italiane, stabili);
    alla STAMPA si traducono — altrimenti l'utente EN legge '(nuovo)' nel mezzo
    di una riga inglese (visto al collaudo del 24 lug)."""
    return {"aggiornato": T("updated", "aggiornato"),
            "nuovo":      T("new", "nuovo"),
            "invariato":  T("unchanged", "invariato")}.get(esito, esito)

def do_ingest_git(con, verbose=True):
    if not GIT_ON:
        if verbose:
            print(T("ingest-git: git disabled in the config (git.enabled=false). State is kept by hand.",
                    "ingest-git: git disabilitato nel config (git.enabled=false). Stato tenuto a mano."))
        return
    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    stash  = git("stash", "list").splitlines()
    wt     = git("worktree", "list").splitlines()
    g = T(f"active branch: {branch}", f"branch attivo: {branch}")
    if stash:        g += T(f" | (!) STASH pending: {len(stash)}", f" | (!) STASH in volo: {len(stash)}")
    if len(wt) > 1:  g += T(f" | {len(wt)} active worktrees", f" | {len(wt)} worktree attivi")
    upsert_singleton(con, "globale", "git", g, today(), "git:HEAD")
    for slug, path in PROGETTI.items():
        out = git("log", "--branches", "--tags", "-1", "--date=short", "--format=%ad|%h|%s", "--", path)
        if not out:
            continue
        d, h, subj = out.split("|", 2)
        br = branch_di(h)
        flag = "" if br == MAIN_BRANCH else T(f"  (!) on '{br}', NOT on {MAIN_BRANCH}",
                                              f"  (!) su '{br}', NON su {MAIN_BRANCH}")
        esito = upsert_singleton(con, slug, "stato",
                                 T(f"last work {d} ({h}, branch {br}): {subj}{flag}",
                                   f"ultimo lavoro {d} ({h}, branch {br}): {subj}{flag}"), d, f"git:{h}")
        if verbose:
            print(f"  {slug}: {d} {h} [{br}]  ({esito_t(esito)})")
    # self_project (opzionale): una cartella di cui vuoi lo "stato" ma fuori da semaforo/dashboard.
    if SELF and SELF.get("path"):
        out = git("log", "--branches", "--tags", "-1", "--date=short", "--format=%ad|%h|%s", "--", SELF["path"])
        if out:
            d, h, subj = out.split("|", 2)
            label = SELF.get("label", SELF.get("slug", "self"))
            esito = upsert_singleton(con, SELF.get("slug", "self"), "stato",
                                     T(f"last work on {label} {d} ({h}): {subj}",
                                       f"ultimo lavoro su {label} {d} ({h}): {subj}"), d, f"git:{h}")
            if verbose:
                print(f"  {SELF.get('slug','self')}: {d} {h}  ({esito_t(esito)})")
    if verbose:
        print(T("ingest-git: done.", "ingest-git: fatto."))

# --- BUSSOLA: le 8 sezioni del brief di un progetto -------------------------
# Ogni voce = (chiave breve · titolo mostrato · "cosa ci va"). Le descrizioni vivono
# QUI (fonte unica): CLI, dashboard.html e /api/brief le leggono da qui, niente doppione.
BUSSOLA = [
    ("meta",      T("GOAL — where this must land", "META — dove deve arrivare"),
     T("The end goal: where the project must land (written by hand, never auto-derived).",
       "L'obiettivo finale: dove deve arrivare il progetto (scritto a mano, non si auto-deriva).")),
    ("dove",      T("WHERE WE ARE NOW", "DOVE SIAMO ORA"),
     T("The current state, derived from git at every session start (or kept by hand if git is off).",
       "Lo stato corrente, derivato da git ad ogni apertura (o tenuto a mano se git e' off).")),
    ("handoff",   T("LAST HANDOFF — end-of-session baton (what was done + where it was heading)",
                    "ULTIMO HANDOFF — testimone fine sessione (cosa fatto + dove si stava andando)"),
     T("The baton the next agent inherits to resume exactly.",
       "Il testimone che il prossimo agente eredita per ripartire esatto.")),
    ("come",      T("NEXT — next steps", "COME — prossimi passi"),
     T("The heading + cross-session coordination notes: what to do/know NOW.",
       "La rotta + le note di coordinamento fra sessioni: cosa fare/sapere ADESSO.")),
    ("operativo", T("HOW WE WORK", "OPERATIVO — come si lavora"),
     T("Rules, ways of working, technical docs and reusable patterns of the project.",
       "Regole, modi di lavorare, documenti tecnici e pattern riusabili del progetto.")),
    ("bloccanti", T("BLOCKERS", "BLOCCANTI"),
     T("What prevents progress NOW (empty = nothing blocking).",
       "Cosa impedisce di procedere ORA (vuota = nessun blocco attivo).")),
    ("bug",       T("KNOWN BUGS", "BUG NOTI"),
     T("Catalogued problems still open.", "Problemi catalogati ancora aperti.")),
    ("decisioni", T("DECISIONS / CONSTRAINTS", "DECISIONI / VINCOLI"),
     T("Choices made, constraints and working preferences.",
       "Scelte prese, vincoli e preferenze di lavoro.")),
]

# Mappa canonica: OGNI tipo ha una tab di casa (0 fatti orfani/invisibili).
# I tipi non elencati cadono nel fallback esplicito 'operativo' (mai invisibili).
TIPO2TAB = {
    "obiettivo": "meta",       "identita":    "meta",
    "stato":     "dove",
    "handoff":   "handoff",
    "rotta":     "come",       "nota":        "come",
    "operativo": "operativo",  "doc-tecnico": "operativo",  "pattern": "operativo",
    "bloccante": "bloccanti",
    "bug":       "bug",
    "decisione": "decisioni",  "vincolo":     "decisioni",  "preferenza": "decisioni",
}
TAB_FALLBACK = "operativo"
BUS_MAX = 6   # dashboard "a colpo d'occhio": max fatti mostrati per sezione, il resto collassa (il brief CLI resta COMPLETO)

# Un fatto di QUALSIASI tipo diventa BLOCCANTE se il testo si APRE con un marcatore esplicito.
# Marcatore (non keyword vaghe) = zero falsi positivi: "X blocca Y" (racconto) NON finisce in BLOCCANTI.
_RE_BLOCCO = re.compile(r"^\s*(?:🔴\s*)?\[?\s*blocca(?:nte|to)?\b\s*[:\]\-]", re.I)

def tab_di(tipo, contenuto):
    """In quale tab della Bussola finisce un fatto. Ritorna None = fuori bussola (es. git)."""
    if tipo == "git":
        return None
    if _RE_BLOCCO.match(contenuto or ""):
        return "bloccanti"
    return TIPO2TAB.get(tipo, TAB_FALLBACK)

def tipi_di_tab(chiave):
    """I tipi che hanno casa in questa tab (per l'etichetta 'si riempie dai fatti di tipo: ...')."""
    t = [tp for tp, k in TIPO2TAB.items() if k == chiave]
    if chiave == "bloccanti":
        t.append(T("+ leading 'BLOCKER:'/'BLOCCANTE:' marker", "+ marcatore 'BLOCCANTE:' in testa"))
    return t

_SEL_VIVI = ("SELECT id,progetto,tipo,contenuto,valido_da,valido_fino_a,fonte,creato_il,chiuso_il"
             " FROM fatti WHERE progetto=? AND valido_fino_a IS NULL ORDER BY valido_da DESC")

def assembla_sezioni(con, slug):
    """FONTE UNICA dello smistamento fatto->tab: usata da brief CLI, dashboard-html e /api/brief.
    Ritorna [(chiave, titolo, perche, [righe]) ...] nell'ordine della BUSSOLA.
    Le righe sono grezze: tuple da mem.py, Row dal server — l'accesso per indice r[i]
    (r[2]=tipo r[3]=contenuto r[4]=valido_da r[6]=fonte) funziona su entrambe."""
    buckets = {k: [] for k, _, _ in BUSSOLA}
    for r in con.execute(_SEL_VIVI, (slug,)):
        k = tab_di(r[2], r[3])
        if k in buckets:
            buckets[k].append(r)
    return [(k, titolo, perche, buckets[k]) for k, titolo, perche in BUSSOLA]

def brief(con, slug):
    print(f"================  {slug.upper()}  ================  " +
          T(f"(state at {now()})", f"(stato al {now()})"))
    for (c,) in con.execute("SELECT contenuto FROM fatti WHERE progetto='globale' AND tipo='git' AND valido_fino_a IS NULL"):
        print(T(f"  REAL GIT  >  {c}", f"  GIT REALE  >  {c}"))
    visti = False
    for k, titolo, perche, rows in assembla_sezioni(con, slug):
        if rows:
            visti = True
            print(f"  -------- {titolo} --------")
            for r in rows:
                print(f"  - {r[3]}   ({r[4]} · {r[6]})")
    if not visti:
        print(T("  (no facts yet: fill this project with its first facts)",
                "  (ancora nessun fatto: questo progetto va riempito col triage)"))
    chiusi = con.execute(
        "SELECT contenuto,valido_da,valido_fino_a FROM fatti WHERE progetto=? AND valido_fino_a IS NOT NULL"
        " ORDER BY chiuso_il DESC LIMIT 2", (slug,)).fetchall()
    if chiusi:
        print(T("  -------- history (CLOSED, not deleted) --------",
                "  -------- storia (CHIUSO, non cancellato) --------"))
        for c, vd, vf in chiusi:
            print(T(f"  - WAS true ({vd} -> closed {vf}): {c}",
                    f"  - ERA vero ({vd} -> chiuso {vf}): {c}"))

def dashboard(con):
    print("================  " + T("LIVE STATE — all projects", "STATO LIVE — tutti i progetti")
          + f"  ================  ({now()})")
    for (c,) in con.execute("SELECT contenuto FROM fatti WHERE progetto='globale' AND tipo='git' AND valido_fino_a IS NULL"):
        print(T(f"  REAL GIT  >  {c}", f"  GIT REALE  >  {c}"))
    for slug in PROGETTI:
        st = con.execute("SELECT contenuto FROM fatti WHERE progetto=? AND tipo='stato' AND valido_fino_a IS NULL"
                         " ORDER BY valido_da DESC LIMIT 1", (slug,)).fetchone()
        nb = con.execute("SELECT COUNT(*) FROM fatti WHERE progetto=? AND tipo='bloccante' AND valido_fino_a IS NULL",
                         (slug,)).fetchone()[0]
        extra = T(f"   [{nb} open blockers]", f"   [{nb} bloccanti aperti]") if nb else ""
        vuoto = T("(no status yet)", "(nessuno stato)")
        print(f"  - {slug.upper()}: {st[0] if st else vuoto}{extra}")

# ---------- comandi CLI ----------
def cmd_init(con, args):       print(T(f"database ready: {DB}", f"DB pronto: {DB}"))
def cmd_ingest_git(con, args): do_ingest_git(con, verbose=True)
def cmd_brief(con, args):      brief(con, args.progetto)
def cmd_dashboard(con, args):  dashboard(con)

def cmd_session_start(con, args):
    do_ingest_git(con, verbose=False)          # all'apertura lo stato git e' SEMPRE fresco (se abilitato)
    slug = rileva_progetto(args.cwd)
    for rel in IDENTITY:                        # identita' stabile (opzionale): mission/regole in testa al contesto
        fp = os.path.abspath(os.path.join(ROOT, rel))
        if os.path.isfile(fp):
            try:
                with open(fp, encoding="utf-8-sig") as fh:   # utf-8-sig: tollera il BOM di Windows
                    print(fh.read().rstrip() + "\n")
            except OSError:
                pass
    if GIT_ON:
        print(T(f">>> {BRAND} — state verified against git. This OVERRIDES any date found in documents. <<<\n",
                f">>> {BRAND} — stato verificato da git. Questo PREVALE su qualunque data nei documenti. <<<\n"))
    else:
        print(T(f">>> {BRAND} — state from the memory (git off: kept by hand). <<<\n",
                f">>> {BRAND} — stato dal registro (git off: tenuto a mano). <<<\n"))
    if slug:
        brief(con, slug)
    else:
        dashboard(con)

def cmd_query(con, args):
    q = " ".join(args.testo)
    print(T(f'Search: "{q}"', f'Ricerca: "{q}"'))
    rows = []
    try:
        rows = con.execute(
            "SELECT f.progetto,f.tipo,f.contenuto,f.valido_fino_a FROM fatti_fts"
            " JOIN fatti f ON f.id=fatti_fts.rowid WHERE fatti_fts MATCH ? ORDER BY rank", (q,)).fetchall()
    except sqlite3.OperationalError:
        pass
    if not rows:
        rows = con.execute(
            "SELECT progetto,tipo,contenuto,valido_fino_a FROM fatti WHERE contenuto LIKE ?", (f"%{q}%",)).fetchall()
    for p, t, c, vf in rows:
        stato = T("TRUE NOW", "VERO ORA") if vf is None else T("closed ", "chiuso ") + vf
        print(f"  [{p}/{t}] <{stato}>  {c}")
    if not rows:
        print(T("  (nothing)", "  (niente)"))

def cmd_add(con, args):
    vd = args.da or today()
    testo = " ".join(args.contenuto)
    add_fatto(con, args.progetto, args.tipo, testo, vd, args.fonte or T("manual", "manuale"))
    k = tab_di(args.tipo, testo)                                   # deposito guidato: dove finira'?
    tab = next((t for kk, t, _ in BUSSOLA if kk == k), T("(outside the compass)", "(fuori bussola)"))
    nota = "" if (args.tipo in TIPO2TAB or k == "bloccanti") else T("  [non-canonical type -> fallback]",
                                                                    "  [tipo non canonico -> fallback]")
    print(T(f"+ [{args.progetto}/{args.tipo}] valid_from={vd}  ->  Compass: «{tab}»{nota}",
            f"+ [{args.progetto}/{args.tipo}] valido_da={vd}  ->  Bussola: «{tab}»{nota}"))

def cmd_close(con, args):
    """Chiude (NON cancella) i fatti aperti di un tipo per un progetto. --like per restringere al testo."""
    q = "SELECT id,contenuto FROM fatti WHERE progetto=? AND tipo=? AND valido_fino_a IS NULL"
    params = [args.progetto, args.tipo]
    if args.like:
        q += " AND contenuto LIKE ?"
        params.append(f"%{args.like}%")
    rows = con.execute(q, params).fetchall()
    for fid, _ in rows:
        con.execute("UPDATE fatti SET valido_fino_a=?, chiuso_il=? WHERE id=?", (today(), now(), fid))
    con.commit()
    print(T(f"closed {len(rows)} facts [{args.progetto}/{args.tipo}] (history is kept)",
            f"chiusi {len(rows)} fatti [{args.progetto}/{args.tipo}] (restano nella storia)"))
    for _, c in rows:
        print(f"  - {c[:90]}")

def semaforo_progetto(con, slug, path):
    """(colore, dettagli) del semaforo per un progetto. Condiviso da health e dashboard.
    Con git: misura quanto il registro diverge dal codice reale.
    Senza git: misura solo i bloccanti aperti (lo stato non si auto-verifica)."""
    # Area SENZA NEMMENO UN FATTO: non e' "critica", e' NUOVA. Dire ROSSO qui e'
    # lo stesso errore, rovesciato, del dire VERDE su una memoria vuota: si
    # allarma chi ha appena creato l'area e non ha ancora scritto niente.
    if not con.execute("SELECT 1 FROM fatti WHERE progetto=? AND valido_fino_a IS NULL LIMIT 1",
                       (slug,)).fetchone():
        return ("NUOVO", [T("empty area — nothing recorded here yet",
                            "area vuota — qui non è ancora stato registrato nulla")])
    if not GIT_ON:
        nb = con.execute("SELECT COUNT(*) FROM fatti WHERE progetto=? AND tipo='bloccante'"
                         " AND valido_fino_a IS NULL", (slug,)).fetchone()[0]
        ha_stato = con.execute("SELECT 1 FROM fatti WHERE progetto=? AND tipo='stato'"
                               " AND valido_fino_a IS NULL LIMIT 1", (slug,)).fetchone()
        if nb > 3:
            return ("ROSSO", [T(f"{nb} open blockers", f"{nb} bloccanti aperti")])
        if nb > 0 or not ha_stato:
            det = []
            if nb: det.append(T(f"{nb} open blockers", f"{nb} bloccanti aperti"))
            if not ha_stato: det.append(T("no status recorded", "nessuno stato registrato"))
            return ("GIALLO", det)
        return ("VERDE", [])
    out = git("log", "--branches", "--tags", "-1", "--date=short", "--format=%h|%ad", "--", path)
    if not out:
        # Nessuna storia git per il path: e' lo stato NORMALE di un'area nuova
        # (cartella appena creata, niente commit ancora). Non e' un allarme:
        # e' "non posso ancora verificare" -> GIALLO con la spiegazione.
        return ("GIALLO", [T("no git history yet for this area's path — the first commit will align it",
                             "nessuna storia git ancora per il percorso dell'area — il primo commit la allineera'")])
    h_git, d_git = out.split("|", 1)
    row = con.execute("SELECT fonte FROM fatti WHERE progetto=? AND tipo='stato' AND fonte LIKE 'git:%'"
                      " AND valido_fino_a IS NULL ORDER BY id DESC LIMIT 1", (slug,)).fetchone()
    h_reg = row[0].split(":", 1)[1] if row and row[0] and ":" in row[0] else None
    # ATTENZIONE: h_reg e' lo stato ANCORATO A UN COMMIT (fonte "git:<hash>"), non
    # "uno stato qualsiasi". Un'area piena di fatti scritti dall'agente (fonte
    # "mcp") ha h_reg=None pur avendo eccome uno stato: dirle ROSSO «no status
    # recorded» e' FALSO, e lo si legge come «la tua memoria non vale niente»
    # subito dopo averla scritta. Serve distinguere i due casi.
    ha_stato = con.execute("SELECT 1 FROM fatti WHERE progetto=? AND tipo='stato'"
                           " AND valido_fino_a IS NULL LIMIT 1", (slug,)).fetchone() is not None
    indietro = 0
    if h_reg and h_reg != h_git:
        rl = git("rev-list", "--count", f"{h_reg}..{h_git}")
        indietro = int(rl) if rl.isdigit() else 999
    sospetti = con.execute(
        "SELECT COUNT(*) FROM fatti WHERE progetto=? AND valido_fino_a IS NULL"
        " AND tipo='bloccante' AND valido_da < ?", (slug, d_git)).fetchone()[0]
    if (h_reg is None and not ha_stato) or indietro > 3 or sospetti > 3:
        sem = "ROSSO"
    elif h_reg is None or indietro > 0 or sospetti > 0:
        sem = "GIALLO"          # stato scritto a mano/dall'agente: c'e', ma non
    else:                       # e' ancora agganciato alla storia git
        sem = "VERDE"
    det = []
    if h_reg is None:
        det.append(T("no status recorded", "nessuno stato registrato") if not ha_stato else
                   T("state not yet anchored to git — run `facto ingest-git`",
                     "stato non ancora agganciato a git — lancia `facto ingest-git`"))
    if indietro:      det.append(T(f"memory {indietro} commits behind git",
                                   f"registro indietro di {indietro} commit vs git"))
    if sospetti:      det.append(T(f"{sospetti} fact{'s' if sospetti != 1 else ''} possibly outdated by the code",
                                   f"{sospetti} fatt{'i' if sospetti != 1 else 'o'} forse superat{'i' if sospetti != 1 else 'o'} dal codice"))
    return (sem, det)

SEM_DISPLAY = {"VERDE": T("GREEN", "VERDE"), "GIALLO": T("YELLOW", "GIALLO"),
               "ROSSO": T("RED", "ROSSO"), "NUOVO": T("NEW", "NUOVA")}

def cmd_health(con, args):
    """SEMAFORO DI FIDUCIA: il sistema dice DA SOLO quando si sta perdendo."""
    print("================  " + T("TRUST LIGHT", "SEMAFORO DI FIDUCIA") + f"  ================  ({now()})")
    if not PROGETTI:
        # Memoria VUOTA: dire "VERDE, fidati" qui sarebbe la bugia peggiore che
        # questo strumento possa raccontare — non sa nulla, e deve dirlo.
        print(T("  NO MEMORY YET — this project has no areas, so there is nothing to trust.",
                "  MEMORIA NON ANCORA COSTRUITA — nessuna area, quindi non c'è nulla di cui fidarsi."))
        print("  ----")
        print(T("  Open your AI agent in this folder: it will design the areas with you.",
                "  Apri il tuo agente AI in questa cartella: disegnerà le aree con te."))
        print(T("  Prefer doing it by hand?  facto add-area <slug> <path>",
                "  Preferisci farlo a mano?   facto add-area <slug> <percorso>"))
        return
    if not GIT_ON:
        print(T("  (git off: the light only watches open blockers)",
                "  (git off: il semaforo guarda solo i bloccanti aperti)"))
    rank = {"NUOVO": -1, "VERDE": 0, "GIALLO": 1, "ROSSO": 2}
    peggiore = None          # se TUTTE le aree sono nuove, il globale e' NUOVO:
                             # dire "fidati" quando non c'e' ancora nulla sarebbe
                             # la stessa bugia del verde su memoria vuota.
    for slug, path in PROGETTI.items():
        sem, det = semaforo_progetto(con, slug, path)
        if peggiore is None or rank[sem] > rank[peggiore]:
            peggiore = sem
        riga = ", ".join(det) if det else T("aligned", "allineato")
        print(f"  [{SEM_DISPLAY[sem]:6}] {slug.upper():9} · {riga}")
    print("  ----")
    peggiore = peggiore or "NUOVO"
    print(T(f"  GLOBAL: {SEM_DISPLAY[peggiore]}   (GREEN=trust it · YELLOW=verify · RED=refresh/do not trust)",
            f"  GLOBALE: {peggiore}   (VERDE=fidati · GIALLO=verifica · ROSSO=rinfresca/non fidarti)"))

def _esc(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

DASH_CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,Segoe UI,Roboto,sans-serif;background:#0f1115;color:#e6e8ec;line-height:1.5;padding:24px}
header{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:22px;border-bottom:1px solid #232733;padding-bottom:16px}
h1{font-size:21px;font-weight:700}
.sub{color:#8b909a;font-size:13px;margin-top:2px}
.globale{font-weight:700;font-size:12px;color:#0f1115;padding:7px 16px;border-radius:999px;letter-spacing:.5px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:16px}
.card{background:#171a21;border:1px solid #232733;border-left:4px solid #555;border-radius:12px;padding:18px}
.cardhead{display:flex;justify-content:space-between;align-items:center;margin-bottom:3px}
.card h2{font-size:15px;letter-spacing:1px}
.badge{font-size:10px;font-weight:700;color:#0f1115;padding:3px 11px;border-radius:999px;letter-spacing:.5px}
.detr{font-size:11px;color:#8b909a;margin-bottom:12px}
.gitline{font-size:11.5px;color:#c9a36b;background:#1f232c;padding:7px 10px;border-radius:6px;margin-bottom:14px;font-family:ui-monospace,SFMono-Regular,monospace}
.sez{margin-bottom:13px}
.sez h4{font-size:10px;text-transform:uppercase;letter-spacing:1.2px;color:#6f7785;margin-bottom:6px}
.sez ul{list-style:none}
.sez li{font-size:13px;padding:4px 0 4px 12px;border-left:2px solid #2a2f3a;margin-bottom:3px}
.meta{display:block;font-size:10.5px;color:#5f6673;margin-top:1px}
details{margin-top:8px}
summary{font-size:11px;color:#6f7785;cursor:pointer}
.sez details.more{margin-top:2px}
.sez details.more>summary{color:#c9a36b;padding-left:12px}
.storia li{border-left-color:#3a2a2a;color:#9aa0aa}
footer{margin-top:24px;color:#5f6673;font-size:11px;text-align:center}
"""

def cmd_dashboard_html(con, args):
    """Genera una dashboard HTML autoconsistente (zero dipendenze) ispezionabile dall'utente."""
    col = {"VERDE": "#2ecc71", "GIALLO": "#f1c40f", "ROSSO": "#e74c3c"}
    rank = {"VERDE": 0, "GIALLO": 1, "ROSSO": 2}
    peggiore = "VERDE"
    gitrow = con.execute("SELECT contenuto FROM fatti WHERE progetto='globale' AND tipo='git' AND valido_fino_a IS NULL").fetchone()
    git_glob = _esc(gitrow[0]) if gitrow else ""
    cards = []
    for slug, path in PROGETTI.items():
        sem, det = semaforo_progetto(con, slug, path)
        if rank[sem] > rank[peggiore]:
            peggiore = sem
        sez_html = ""
        li = lambda r: f"<li>{_esc(r[3])}<span class=meta>{r[4]} · {_esc(r[6])}</span></li>"
        for k, titolo, perche, rows in assembla_sezioni(con, slug):
            if not rows:
                continue
            if len(rows) <= BUS_MAX:                          # "a colpo d'occhio": collassa l'eccesso
                sez_html += f"<div class=sez><h4>{_esc(titolo)}</h4><ul>{''.join(li(r) for r in rows)}</ul></div>"
            else:
                piu = T(f"show {len(rows)-BUS_MAX} more", f"mostra altre {len(rows)-BUS_MAX}")
                sez_html += (f"<div class=sez><h4>{_esc(titolo)}</h4>"
                             f"<ul>{''.join(li(r) for r in rows[:BUS_MAX])}</ul>"
                             f"<details class=more><summary>{piu}</summary>"
                             f"<ul>{''.join(li(r) for r in rows[BUS_MAX:])}</ul></details></div>")
        chiusi = con.execute(
            "SELECT contenuto,valido_da,valido_fino_a FROM fatti WHERE progetto=? AND valido_fino_a IS NOT NULL"
            " ORDER BY chiuso_il DESC LIMIT 6", (slug,)).fetchall()
        storia = ""
        if chiusi:
            chiuso_lbl = T("closed", "chiuso")
            si = "".join(f"<li>{_esc(c)}<span class=meta>{vd} → {chiuso_lbl} {vf}</span></li>" for c, vd, vf in chiusi)
            storia = (f"<details><summary>" + T(f"history · {len(chiusi)} closed facts",
                                                f"storia · {len(chiusi)} fatti chiusi")
                      + f"</summary><ul class=storia>{si}</ul></details>")
        det_txt = _esc(" · ".join(det)) if det else T("aligned", "allineato")
        cards.append(
            f'<section class=card style="border-left-color:{col[sem]}">'
            f'<div class=cardhead><h2>{_esc(LABELS.get(slug, slug).upper())}</h2>'
            f'<span class=badge style="background:{col[sem]}">{sem}</span></div>'
            f'<div class=detr>{det_txt}</div>'
            f'<div class=gitline>{git_glob}</div>'
            f'{sez_html}{storia}</section>')
    html = (
        f"<!doctype html><html lang={'it' if LANG == 'it' else 'en'}><head><meta charset=utf-8>"
        "<meta name=viewport content=\"width=device-width,initial-scale=1\">"
        f"<title>{_esc(BRAND)}</title><style>" + DASH_CSS + "</style></head><body>"
        f"<header><div><h1>{_esc(BRAND)}</h1>"
        f"<div class=sub>" + T(f"living project memory — generated {now()}",
                               f"memoria viva dei progetti — generata {now()}") + "</div></div>"
        f"<div class=globale style=\"background:{col[peggiore]}\">{SEM_DISPLAY[peggiore]}</div></header>"
        f"<main class=grid>{''.join(cards)}</main>"
        f"<footer>" + T(f"source: {_esc(os.path.basename(DB))} · 🟢 trust · 🟡 verify · 🔴 refresh",
                        f"fonte: {_esc(os.path.basename(DB))} · 🟢 fidati · 🟡 verifica · 🔴 rinfresca")
        + "</footer></body></html>")
    out = os.path.join(ROOT, "dashboard.html")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(T(f"dashboard generated: {out} ({len(html)} bytes)",
            f"dashboard generata: {out} ({len(html)} byte)"))

def cmd_handoff(con, args):
    """Salva il REPORT DI FINE SESSIONE (testimone): cosa fatto + prossime direttive.
    Cosi' il prossimo agente eredita la DIREZIONE, non solo lo stato. Il vecchio va in storia."""
    if args.file:
        with open(args.file, encoding="utf-8-sig") as fh:   # utf-8-sig: tollera il BOM di Windows
            testo = fh.read().strip()
    else:
        testo = sys.stdin.read().strip()
    if len(testo) < 10:
        print(T("empty handoff, skipped", "handoff vuoto, skip")); return
    esito = upsert_singleton(con, args.progetto, "handoff", testo, today(),
                             args.fonte or T("session", "sessione"))
    print(T(f"handoff saved [{args.progetto}] ({esito_t(esito)}, {len(testo)} chars)",
            f"handoff salvato [{args.progetto}] ({esito_t(esito)}, {len(testo)} char)"))

def cmd_doctor(args):
    """Controlla DA SOLO che sia tutto a posto: prerequisiti, config, percorsi, DB.
    Pensato per chi installa: lo lancia e sa subito se è pronto o cosa manca."""
    import shutil, platform
    checks = []   # (esito, testo)  esito: True=ok, False=problema, None=avviso
    v = sys.version_info
    checks.append((v >= (3, 8), T(f"Python {platform.python_version()} (>= 3.8 required)",
                                  f"Python {platform.python_version()} (serve >= 3.8)")))
    fb = shutil.which("facto")
    checks.append((True if fb else None,
                   T(f"`facto` command on PATH: {fb}", f"comando `facto` nel PATH: {fb}") if fb
                   else T("`facto` NOT on PATH: the Claude hook and the git hook call it by name and "
                          "would not fire. Open a NEW terminal or run `uv tool update-shell`; "
                          "fallback: `python -m facto`.",
                          "`facto` NON è nel PATH: l'hook Claude e l'hook git lo chiamano per nome e "
                          "non partirebbero. Apri un terminale NUOVO oppure `uv tool update-shell`; "
                          "ripiego: `python -m facto`.")))
    try:
        t = sqlite3.connect(":memory:"); t.execute("CREATE VIRTUAL TABLE x USING fts5(c)"); t.close()
        checks.append((True, T("SQLite + FTS5 full-text search available",
                               "SQLite + ricerca full-text FTS5 disponibili")))
    except Exception as e:
        checks.append((False, T(f"FTS5 not available in this Python: {e}",
                                f"FTS5 non disponibile in questo Python: {e}")))
    checks.append((True, T(f"config found: {CFG['_path']}", f"config trovato: {CFG['_path']}")))
    checks.append((bool(PROGETTI), T(f"{len(PROGETTI)} areas configured: {', '.join(PROGETTI) or '(none!)'}",
                                     f"{len(PROGETTI)} moduli configurati: {', '.join(PROGETTI) or '(nessuno!)'}")))
    mancanti = [s for s, p in PROGETTI.items() if not os.path.isdir(os.path.join(ROOT, p))]
    checks.append((None if mancanti else True,
                   T("all area paths exist", "tutti i percorsi dei moduli esistono")
                   if not mancanti else T(f"paths not present yet: {', '.join(mancanti)}",
                                          f"percorsi non ancora presenti: {', '.join(mancanti)}")))
    try:
        os.makedirs(os.path.dirname(DB), exist_ok=True)
        checks.append((os.access(os.path.dirname(DB), os.W_OK),
                       T(f"DB folder writable: {os.path.dirname(DB)}",
                         f"cartella del DB scrivibile: {os.path.dirname(DB)}")))
    except Exception as e:
        checks.append((False, T(f"DB folder not writable: {e}", f"cartella del DB non scrivibile: {e}")))
    if GIT_ON:
        if shutil.which("git"):
            inside = git("rev-parse", "--is-inside-work-tree") == "true"
            checks.append((None if not inside else True,
                           T("git repo detected", "repo git rilevato") if inside
                           else T(f"git is installed but {ROOT} is not a git repo (need 'git init'?)",
                                  f"git presente ma {ROOT} non è un repo git (serve 'git init'?)")))
            if inside:
                # il branch del config esiste davvero? un main_branch sbagliato
                # tagga ogni stato con "NOT on <branch>" e confonde il semaforo.
                cur = git("branch", "--show-current").strip()
                esiste = bool(git("branch", "--list", MAIN_BRANCH).strip())
                checks.append((True if esiste else None,
                               T(f"main branch '{MAIN_BRANCH}' exists", f"branch principale '{MAIN_BRANCH}' esiste")
                               if esiste else
                               T(f"config says main_branch '{MAIN_BRANCH}' but the repo doesn't have it "
                                 f"(current: '{cur or '?'}'): set \"git\": {{\"main_branch\": \"{cur or '...'}\"}} "
                                 "in facto.config.json",
                                 f"il config dice main_branch '{MAIN_BRANCH}' ma il repo non ce l'ha "
                                 f"(attuale: '{cur or '?'}'): metti \"git\": {{\"main_branch\": \"{cur or '...'}\"}} "
                                 "in facto.config.json")))
        else:
            checks.append((False, T("git.enabled=true but 'git' is not on PATH (install git, or set git.enabled=false)",
                                    "git.enabled=true ma 'git' non è nel PATH (installa git, oppure metti git.enabled=false)")))
    else:
        checks.append((True, T("git disabled in the config: state kept by hand (ok)",
                               "git disabilitato nel config: stato tenuto a mano (ok)")))
    print(f"================  DOCTOR — {BRAND}  ================")
    glyph = {True: "  OK  ", False: " FAIL ", None: " WARN "}
    for e, txt in checks:
        print(f"  [{glyph[e]}] {txt}")
    nf = sum(1 for e, _ in checks if e is False)
    nw = sum(1 for e, _ in checks if e is None)
    print("  ----")
    if nf:
        print(T(f"  {nf} problem(s) to fix before using it" + (f" (+{nw} warnings)" if nw else "") + ".",
                f"  {nf} problema/i da risolvere prima di usarlo" + (f" (+{nw} avvisi)" if nw else "") + "."))
    elif nw:
        print(T(f"  Everything essential is in place. {nw} non-blocking warning(s) (e.g. folders not created yet).",
                f"  Tutto l'essenziale è a posto. {nw} avviso/i non bloccante/i (es. cartelle non ancora create)."))
    else:
        print(T("  All good: you are ready.", "  Tutto a posto: sei pronto."))


def add_area(slug, path, label=None):
    """Registra un'area nel config. UNICA implementazione: la usano sia il CLI
    (`facto add-area`) sia il tool MCP facto_add_area — senza MCP un utente
    resterebbe senza modo di creare la prima area, e non potrebbe nemmeno
    iniziare."""
    slug = re.sub(r"[^a-z0-9_-]", "", (slug or "").strip().lower().replace(" ", "-"))
    path = (path or "").strip().replace("\\", "/").strip("/")
    label = (label or slug).strip()
    if not slug or not path:
        raise ValueError(T("slug and path are both required", "servono sia slug sia percorso"))
    if slug in ("globale", "progetto"):
        # non basta rifiutare: chi ci prova (agente o umano) deve sapere che
        # quell'area C'E' GIA' e come usarla — succede al primo onboarding.
        raise ValueError(T(
            f"'{slug}' already exists and is reserved for project-wide facts — "
            f"don't create it, just write into it: facto_add_fact(area='{slug}', ...)",
            f"'{slug}' esiste già ed è riservata ai fatti trasversali — non va creata, "
            f"ci si scrive direttamente: facto_add_fact(area='{slug}', ...)"))
    cfg_path = CFG.get("_path")
    if not cfg_path or not os.path.isfile(cfg_path):
        raise ValueError(T("no facto.config.json here — run `facto connect` first",
                           "nessun facto.config.json qui — lancia prima `facto connect`"))
    with open(cfg_path, encoding="utf-8-sig") as fh:
        cfg = json.load(fh)
    prj = cfg.setdefault("projects", {})
    nuovo = slug not in prj
    prj[slug] = {"path": path, "label": label}
    with open(cfg_path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(cfg, fh, ensure_ascii=False, indent=2)
    return slug, path, len(prj), nuovo, os.path.isdir(os.path.join(ROOT, path))


def cmd_add_area(con, args):
    try:
        slug, path, tot, nuovo, esiste = add_area(args.slug, args.path, args.label)
    except ValueError as e:
        print(f"  {e}")
        return
    verbo = T("added", "aggiunta") if nuovo else T("updated", "aggiornata")
    print(T(f"✓ area '{slug}' {verbo} -> {path}  [{tot} area(s) total]",
            f"✓ area '{slug}' {verbo} -> {path}  [{tot} aree in tutto]"))
    if not esiste:
        print(T("  (note: that folder does not exist yet)",
                "  (nota: quella cartella non esiste ancora)"))


def remove_area(slug):
    """Toglie un'area dal config. UNICA implementazione (CLI + tool MCP). Chi
    prova lo strumento crea aree di prova al primo giro e deve poterle togliere
    senza editare il JSON a mano. I FATTI restano nel DB (bi-temporale: non si
    cancella), l'area sparisce solo dalla vista — restano cercabili con query."""
    slug = (slug or "").strip().lower()
    cfg_path = CFG.get("_path")
    if not cfg_path or not os.path.isfile(cfg_path):
        raise ValueError(T("no facto.config.json here", "nessun facto.config.json qui"))
    with open(cfg_path, encoding="utf-8-sig") as fh:
        cfg = json.load(fh)
    prj = cfg.get("projects", {})
    if slug not in prj:
        raise ValueError(T(f"no area '{slug}' (have: {', '.join(prj) or 'none'})",
                           f"nessuna area '{slug}' (ci sono: {', '.join(prj) or 'nessuna'})"))
    del prj[slug]
    with open(cfg_path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(cfg, fh, ensure_ascii=False, indent=2)
    return slug, len(prj)


def cmd_remove_area(con, args):
    n_fatti = con.execute("SELECT COUNT(*) FROM fatti WHERE progetto=? AND valido_fino_a IS NULL",
                          (args.slug.strip().lower(),)).fetchone()[0]
    try:
        slug, tot = remove_area(args.slug)
    except ValueError as e:
        print(f"  {e}")
        return
    print(T(f"✓ area '{slug}' removed  [{tot} area(s) left]",
            f"✓ area '{slug}' rimossa  [restano {tot} aree]"))
    if n_fatti:
        print(T(f"  ({n_fatti} fact(s) kept in history — find them with `facto query`)",
                f"  ({n_fatti} fatto/i restano nella storia — cercali con `facto query`)"))


def main():
    ap = argparse.ArgumentParser(prog="facto")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ingest-git")
    sub.add_parser("dashboard")
    sub.add_parser("health")
    sub.add_parser("dashboard-html")
    sub.add_parser("doctor")
    p = sub.add_parser("close"); p.add_argument("progetto"); p.add_argument("tipo"); p.add_argument("--like")
    p = sub.add_parser("handoff"); p.add_argument("progetto"); p.add_argument("--file"); p.add_argument("--fonte")
    p = sub.add_parser("brief");  p.add_argument("progetto")
    p = sub.add_parser("query");  p.add_argument("testo", nargs="+")
    p = sub.add_parser("session-start"); p.add_argument("--cwd", default=ROOT)
    p = sub.add_parser("add")
    p.add_argument("progetto"); p.add_argument("tipo"); p.add_argument("contenuto", nargs="+")
    p.add_argument("--da"); p.add_argument("--fonte")
    p = sub.add_parser("add-area"); p.add_argument("slug"); p.add_argument("path")
    p.add_argument("--label")
    p = sub.add_parser("remove-area"); p.add_argument("slug")
    args = ap.parse_args()
    if args.cmd == "doctor":          # gira anche se il DB/FTS5 è problematico: è il suo scopo
        return cmd_doctor(args)
    con = db()
    {"ingest-git": cmd_ingest_git, "brief": cmd_brief, "dashboard": cmd_dashboard,
     "session-start": cmd_session_start, "query": cmd_query, "add": cmd_add,
     "add-area": cmd_add_area, "remove-area": cmd_remove_area, "health": cmd_health,
     "close": cmd_close, "dashboard-html": cmd_dashboard_html, "handoff": cmd_handoff}[args.cmd](con, args)
    con.close()

if __name__ == "__main__":
    main()
