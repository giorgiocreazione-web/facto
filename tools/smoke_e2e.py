#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FACTO — smoke E2E cross-platform del RUNTIME (stdlib pura, headless).

Prova il CONTRATTO del prodotto senza Claude vero, su qualunque OS (Windows,
macOS, Linux — locale o CI): la wheel si installa, `connect` scrive i file
giusti (con EOL giusti), il claude-hook risponde il JSON del protocollo nei due
rami (setup/daily), il server MCP fa l'handshake e il round-trip di scrittura,
la CLI copre il ciclo add/close/handoff/status/doctor, il post-commit
auto-ingesta, la dashboard web serve pagina e API.

Uso:  python tools/smoke_e2e.py            # build wheel + venv + tutte le fasi
Exit: 0 = tutto verde; 1 = almeno un FAIL (report riga per riga in fondo).
"""
import glob
import json
import os
import queue
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import zipfile

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WIN = os.name == "nt"
RES = []          # (ok: bool, nome, dettaglio)


def ok(nome, dettaglio=""):
    RES.append((True, nome, dettaglio))
    print(f"  [ OK ] {nome}" + (f"  · {dettaglio}" if dettaglio else ""))


def fail(nome, dettaglio=""):
    RES.append((False, nome, dettaglio))
    print(f"  [FAIL] {nome}" + (f"  · {dettaglio}" if dettaglio else ""))


def check(cond, nome, dettaglio=""):
    (ok if cond else fail)(nome, dettaglio)
    return bool(cond)


def sh(cmd, cwd=None, env=None, inp=None, timeout=90):
    """subprocess.run text/utf-8, mai solleva: ritorna (rc, out, err)."""
    try:
        r = subprocess.run(cmd, cwd=cwd, env=env, input=inp, capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=timeout)
        return r.returncode, r.stdout or "", r.stderr or ""
    except subprocess.TimeoutExpired:
        return -1, "", f"timeout {timeout}s: {cmd}"
    except Exception as e:
        return -2, "", f"{e}"


def porta_libera():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


# ---------------------------------------------------------------- client MCP
class MCP:
    """Client minimo per il server stdio: una riga JSON per messaggio."""

    def __init__(self, cmd, cwd, env):
        self.p = subprocess.Popen(cmd, cwd=cwd, env=env, stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  text=True, encoding="utf-8", errors="replace")
        self.q = queue.Queue()
        threading.Thread(target=self._reader, daemon=True).start()
        self.rid = 0

    def _reader(self):
        for line in self.p.stdout:
            self.q.put(line)
        self.q.put(None)

    def call(self, method, params=None, timeout=25):
        """Richiesta con id -> attende la risposta con QUELLO stesso id."""
        self.rid += 1
        rid = self.rid
        msg = {"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}}
        self.p.stdin.write(json.dumps(msg, ensure_ascii=False) + "\n")
        self.p.stdin.flush()
        fine = time.time() + timeout
        while time.time() < fine:
            try:
                line = self.q.get(timeout=max(0.1, fine - time.time()))
            except queue.Empty:
                break
            if line is None:
                raise RuntimeError("mcp: stdout chiuso (server morto)")
            line = line.strip()
            if not line:
                continue
            try:
                m = json.loads(line)
            except json.JSONDecodeError:
                continue                      # rumore: non e' del protocollo
            if m.get("id") == rid:
                return m
        raise RuntimeError(f"mcp: nessuna risposta a {method} entro {timeout}s")

    def notify(self, method):
        self.p.stdin.write(json.dumps({"jsonrpc": "2.0", "method": method}) + "\n")
        self.p.stdin.flush()

    def close(self):
        try:
            self.p.stdin.close()
            self.p.wait(timeout=10)
        except Exception:
            self.p.kill()


def testo_tool(resp):
    """result.content[0].text di una risposta tools/call (o '')."""
    try:
        return resp["result"]["content"][0]["text"]
    except Exception:
        return ""


# ---------------------------------------------------------------- install
def _installa_wheel(tmp, wheel):
    """Installa la wheel in un venv usa-e-getta, provando le vie in ordine di
    realismo. Ritorna (facto_bin, vpy, bindir, via) o None."""
    venv = os.path.join(tmp, "venv")
    bindir = os.path.join(venv, "Scripts" if WIN else "bin")
    vpy = os.path.join(bindir, "python.exe" if WIN else "python")
    fbin = os.path.join(bindir, "facto.exe" if WIN else "facto")

    # via 1 — uv: il percorso che la guida raccomanda ai clienti
    if shutil.which("uv"):
        rc, _, e1 = sh(["uv", "venv", venv], timeout=120)
        if rc == 0:
            rc, _, e2 = sh(["uv", "pip", "install", "--python", vpy, wheel], timeout=180)
            if rc == 0 and os.path.isfile(fbin):
                return fbin, vpy, bindir, "uv"
        shutil.rmtree(venv, ignore_errors=True)

    # via 2 — venv + pip interno (python.org, CI runner)
    rc, _, _ = sh([sys.executable, "-m", "venv", venv], timeout=180)
    if rc == 0:
        rc, _, _ = sh([vpy, "-m", "pip", "install", "--no-index", "--quiet", wheel], timeout=180)
        if rc == 0 and os.path.isfile(fbin):
            return fbin, vpy, bindir, "venv+pip"
    shutil.rmtree(venv, ignore_errors=True)

    # via 3 — venv --without-pip + pip di SISTEMA puntato al venv (pip>=22.3)
    rc, _, _ = sh([sys.executable, "-m", "venv", "--without-pip", venv], timeout=120)
    if rc != 0:
        return None
    rc, _, _ = sh([sys.executable, "-m", "pip", "--version"])
    if rc == 0:
        rc, _, _ = sh([sys.executable, "-m", "pip", "install", "--python", vpy,
                       "--no-index", "--quiet", wheel], timeout=180)
        if rc == 0 and os.path.isfile(fbin):
            return fbin, vpy, bindir, "pip di sistema --python"

    # via 4 — stdlib pura: wheel = zip -> site-packages + script console a mano
    # (stesso lavoro che farebbe pip: Debian/Ubuntu senza ensurepip ne' pip).
    rc, purelib, _ = sh([vpy, "-c", "import sysconfig;print(sysconfig.get_paths()['purelib'])"])
    purelib = purelib.strip()
    if rc != 0 or not purelib:
        return None
    try:
        with zipfile.ZipFile(wheel) as z:
            z.extractall(purelib)
    except Exception:
        return None
    if WIN:
        fbin = os.path.join(bindir, "facto.cmd")
        with open(fbin, "w", encoding="utf-8") as fh:
            fh.write(f'@echo off\r\n"{vpy}" -m facto %*\r\n')
    else:
        with open(fbin, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(f'#!{vpy}\nimport sys\nfrom facto.cli import main\nsys.exit(main())\n')
        os.chmod(fbin, 0o755)
    rc, out, _ = sh([fbin, "--version"])
    if rc == 0 and out.startswith("facto"):
        return fbin, vpy, bindir, "unzip stdlib (niente pip/uv sul sistema)"
    return None


# ---------------------------------------------------------------- fasi
def main():
    t0 = time.time()
    print(f"================  FACTO — smoke E2E runtime  ================")
    print(f"  OS: {sys.platform} · Python {sys.version.split()[0]} · repo: {ROOT}")

    tmp = tempfile.mkdtemp(prefix="facto-smoke-")
    try:
        return _fasi(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _fasi(tmp):
    # --- fase 0: build della wheel (lo strumento di casa, offline) ------------
    rc, out, err = sh([sys.executable, os.path.join(ROOT, "tools", "build_wheel.py")], cwd=ROOT)
    wheels = sorted(glob.glob(os.path.join(ROOT, "dist", "*.whl")), key=os.path.getmtime)
    if not check(rc == 0 and wheels, "build wheel", err.strip()[-200:] if rc else os.path.basename(wheels[-1]) if wheels else ""):
        return riepilogo()
    wheel = wheels[-1]

    # --- fase 1: venv pulito + install della wheel (il percorso del cliente) --
    # Cascata realistica: uv (percorso raccomandato) -> venv+pip (CI, python.org)
    # -> pip di sistema --python -> unzip stdlib (Debian/Ubuntu senza ensurepip/pip:
    # e' il mondo vero dei clienti Linux, la guida li manda su uv).
    esito = _installa_wheel(tmp, wheel)
    if not check(bool(esito), "install della wheel in venv pulito",
                 esito[3] if esito else "nessuna via disponibile (ne' uv, ne' ensurepip, ne' pip)"):
        return riepilogo()
    FACTO, vpy, bindir, via = esito
    check(os.path.isfile(FACTO), "comando `facto` installato", f"{FACTO}  (via: {via})")

    # ambiente ISOLATO: venv davanti al PATH (per hook git/doctor), niente
    # variabili FACTO_* della macchina che inquinerebbero la sandbox
    env = dict(os.environ)
    env["PATH"] = bindir + os.pathsep + env.get("PATH", "")
    for k in ("FACTO_CONFIG", "REGISTRO_CONFIG", "FACTO_DB", "REGISTRO_DB",
              "FACTO_AREA", "REGISTRO_AREA", "FACTO_LANG", "REGISTRO_LANG", "FACTO_FONTE"):
        env.pop(k, None)

    # cwd NEUTRO (tmp): nel repo dev c'e' facto.py (launcher legacy) che farebbe
    # ombra al package con `python -m facto` — il cliente non ce l'ha, il CI si'.
    rc, out, _ = sh([FACTO, "--version"], cwd=tmp, env=env)
    check(rc == 0 and out.startswith("facto "), "facto --version", out.strip())
    rc, out, _ = sh([vpy, "-m", "facto", "--version"], cwd=tmp, env=env)
    check(rc == 0 and out.startswith("facto "), "python -m facto (fallback senza PATH)", out.strip())

    # --- fase 2: sandbox progetto con git vero --------------------------------
    proj = os.path.join(tmp, "proj")
    os.makedirs(os.path.join(proj, "src"))
    with open(os.path.join(proj, "README.md"), "w", encoding="utf-8") as fh:
        fh.write("# smoke project\n")
    for cmd in (["git", "init"],
                ["git", "config", "user.email", "smoke@example.com"],
                ["git", "config", "user.name", "Smoke"],
                ["git", "add", "-A"],
                ["git", "commit", "-m", "init"],
                ["git", "branch", "-M", "main"]):
        rc, _, err = sh(cmd, cwd=proj, env=env)
        if rc != 0:
            fail("setup git sandbox", f"{' '.join(cmd)}: {err.strip()[-200:]}")
            return riepilogo()
    ok("sandbox git pronta", proj)

    # --- fase 3: connect --all (i file che scrive, i loro EOL, idempotenza) ---
    rc, out, _ = sh([FACTO, "connect", "--all"], cwd=proj, env=env)
    check(rc == 0, "facto connect --all", out.strip().splitlines()[-1] if out.strip() else "")
    sett = os.path.join(proj, ".claude", "settings.json")
    mcpj = os.path.join(proj, ".mcp.json")
    cfgj = os.path.join(proj, "facto.config.json")
    hookp = os.path.join(proj, ".git", "hooks", "post-commit")
    try:
        with open(sett, encoding="utf-8") as fh:
            d = json.load(fh)
        cmds = [h.get("command", "") for e in d["hooks"]["SessionStart"] for h in e["hooks"]]
        check(any("facto claude-hook" in c for c in cmds), "hook SessionStart scritto", str(cmds))
    except Exception as e:
        fail("hook SessionStart scritto", str(e))
    try:
        with open(mcpj, encoding="utf-8") as fh:
            d = json.load(fh)
        blk = d["mcpServers"]["facto"]
        check(blk.get("command") == "facto" and blk.get("args") == ["mcp-serve"],
              "server MCP in .mcp.json", json.dumps(blk))
    except Exception as e:
        fail("server MCP in .mcp.json", str(e))
    try:
        with open(cfgj, encoding="utf-8") as fh:
            d = json.load(fh)
        check(d.get("projects") == {}, "config scaffold (aree VUOTE: le disegna l'agente)")
    except Exception as e:
        fail("config scaffold", str(e))
    try:
        with open(hookp, "rb") as fh:
            hb = fh.read()
        check(hb.startswith(b"#!/bin/sh") and b"facto ingest-git" in hb and b"\r" not in hb,
              "post-commit sh POSIX senza CRLF")
    except Exception as e:
        fail("post-commit sh POSIX senza CRLF", str(e))
    for p in (sett, mcpj, cfgj):
        try:
            with open(p, "rb") as fh:
                raw = fh.read()
            check(b"\r" not in raw, f"EOL LF in {os.path.basename(p)}")
        except Exception as e:
            fail(f"EOL LF in {os.path.basename(p)}", str(e))
    # idempotenza: un secondo connect non deve duplicare nulla
    rc, _, _ = sh([FACTO, "connect", "--all"], cwd=proj, env=env)
    with open(sett, encoding="utf-8") as fh:
        n_hook = fh.read().count("facto claude-hook")
    with open(hookp, encoding="utf-8") as fh:
        n_git = fh.read().count("facto ingest-git")
    check(rc == 0 and n_hook == 1 and n_git == 1, "connect idempotente",
          f"hook claude x{n_hook}, hook git x{n_git}")

    # --- fase 3-bis: la PRIMA IMPRESSIONE (i 10 attriti del test «utente vero»)
    # Sono i difetti che uno sconosciuto incontra nei primi due minuti: qui
    # restano inchiodati, perché sono anche i più facili da far tornare.
    # --help DEVE funzionare anche SENZA un progetto: e' la prima cosa che prova
    # chi ha appena installato (prima rispondeva «no facto.config.json», exit 2).
    rc, out, err = sh([FACTO, "--help"], cwd=tmp, env=env)
    check(rc == 0 and "facto connect --all" in (out + err) and "no facto.config.json" not in (out + err),
          "`facto --help` funziona anche fuori da un progetto",
          f"rc={rc} " + (out + err).strip().splitlines()[0][:60] if (out + err).strip() else "")
    rc, out, err = sh([FACTO, "--help"], cwd=proj, env=env)
    testo = out + err
    check("usage: mem" not in testo and "facto —" in testo,
          "l'help non mostra piu' il nome pre-rebrand ('mem')",
          testo.strip().splitlines()[0][:60] if testo.strip() else "")
    check("facto add-area" in testo and "facto init" not in testo,
          "help: c'è add-area, non c'è più init (abolito)")
    try:
        with open(os.path.join(proj, ".gitignore"), encoding="utf-8") as fh:
            gi = fh.read()
        check(".facto/" in gi, "connect protegge il repo: .facto/ nel .gitignore")
    except Exception as e:
        fail("connect protegge il repo: .facto/ nel .gitignore", str(e))
    # il progetto non usa nessun editor: connect --all NON deve creargli cartelle
    intrusi = [d for d in (".cursor", ".vscode", ".gemini", ".codex")
               if os.path.isdir(os.path.join(proj, d))]
    check(not intrusi, "connect --all non è invadente (nessuna cartella editor non richiesta)",
          "trovate: " + ", ".join(intrusi) if intrusi else "")
    rc, out, _ = sh([FACTO, "status"], cwd=proj, env=env)
    check(rc == 0 and "NO MEMORY YET" in out and "GLOBAL: GREEN" not in out,
          "semaforo su memoria VUOTA: ammette di non sapere (non dice 'trust it')",
          out.strip().splitlines()[1][:70] if len(out.strip().splitlines()) > 1 else "")
    # --- fase 3-ter: connect multi-agente (vscode/codex/gemini/AGENTS.md) -----
    # Espliciti (il rilevamento dipende dalla macchina; il contratto no) e DUE
    # volte: i formati devono essere giusti E idempotenti.
    for _ in (1, 2):
        rc, out, _ = sh([FACTO, "connect", "vscode", "codex", "gemini", "agents"], cwd=proj, env=env)
        if rc != 0:
            break
    check(rc == 0, "facto connect vscode codex gemini agents (x2)")
    try:
        with open(os.path.join(proj, ".vscode", "mcp.json"), encoding="utf-8") as fh:
            d = json.load(fh)
        blk = d["servers"]["facto"]         # chiave 'servers': il dialetto VS Code
        check(blk.get("command") == "facto" and blk.get("args") == ["mcp-serve"],
              "vscode .vscode/mcp.json (chiave 'servers')", json.dumps(blk))
    except Exception as e:
        fail("vscode .vscode/mcp.json (chiave 'servers')", str(e))
    try:
        with open(os.path.join(proj, ".codex", "config.toml"), encoding="utf-8") as fh:
            toml_txt = fh.read()
        n_blk = toml_txt.count("[mcp_servers.facto]")
        okp = True
        try:
            import tomllib
            with open(os.path.join(proj, ".codex", "config.toml"), "rb") as fh:
                t = tomllib.load(fh)
            okp = t["mcp_servers"]["facto"]["command"] == "facto"
        except ModuleNotFoundError:
            pass
        check(n_blk == 1 and 'command = "facto"' in toml_txt and okp,
              "codex .codex/config.toml (TOML valido, 1 blocco)", f"blocchi x{n_blk}")
    except Exception as e:
        fail("codex .codex/config.toml (TOML valido, 1 blocco)", str(e))
    try:
        with open(os.path.join(proj, ".gemini", "settings.json"), encoding="utf-8") as fh:
            d = json.load(fh)
        check(d["mcpServers"]["facto"]["command"] == "facto",
              "gemini .gemini/settings.json (mcpServers)")
    except Exception as e:
        fail("gemini .gemini/settings.json (mcpServers)", str(e))
    try:
        with open(os.path.join(proj, "AGENTS.md"), "rb") as fh:
            ab = fh.read()
        atxt = ab.decode("utf-8")
        check(atxt.count("<!-- facto:begin -->") == 1 and "facto_handoff" in atxt
              and b"\r" not in ab, "AGENTS.md (1 blocco marcato, LF)")
    except Exception as e:
        fail("AGENTS.md (1 blocco marcato, LF)", str(e))

    # --- fase 4: claude-hook, ramo SETUP (progetto senza aree) ----------------
    rc, out, err = sh([FACTO, "claude-hook"], cwd=tmp, env=env,
                      inp=json.dumps({"cwd": proj}))
    try:
        ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
    except Exception:
        ctx = ""
    check(rc == 0 and "first-run onboarding" in ctx,
          "claude-hook ramo setup (onboarding agente-guidato)",
          (ctx[:80] + "…") if ctx else f"stdout: {out[:120]!r} err: {err[:120]!r}")

    # add-area DOPO il ramo setup: creare un'area qui renderebbe il progetto
    # "gia' strutturato" e il hook darebbe il brief quotidiano invece dell'onboarding.
    rc, out, _ = sh([FACTO, "add-area", "shell", "src", "--label", "From shell"], cwd=proj, env=env)
    check(rc == 0 and "area 'shell'" in out, "facto add-area: si crea un'area SENZA MCP",
          out.strip()[:70])
    rc, out, _ = sh([FACTO, "status"], cwd=proj, env=env)
    check(rc == 0 and "SHELL" in out and "NO MEMORY YET" not in out,
          "il semaforo vede l'area creata da shell")
    # remove-area: chi prova lo strumento crea aree per sbaglio al primo giro e
    # deve poterle togliere senza editare il JSON a mano (segnalato dal collaudo).
    rc, out, _ = sh([FACTO, "add-area", "usaegetta", "src"], cwd=proj, env=env)
    rc, out, _ = sh([FACTO, "remove-area", "usaegetta"], cwd=proj, env=env)
    check(rc == 0 and "usaegetta" in out and "removed" in out,
          "facto remove-area: si toglie un'area creata per sbaglio", out.strip()[:60])
    rc, out, _ = sh([FACTO, "remove-area", "mai-esistita"], cwd=proj, env=env)
    check("no area" in out.lower() or "nessuna area" in out.lower(),
          "remove-area: errore gentile se il nome non esiste", out.strip()[:60])


    # --- fase 5: MCP — handshake e round-trip di scrittura --------------------
    try:
        m = MCP([FACTO, "mcp-serve"], cwd=proj, env=env)
        r = m.call("initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                                  "clientInfo": {"name": "smoke", "version": "0"}})
        si = r.get("result", {}).get("serverInfo", {})
        check(si.get("name") == "facto", "MCP initialize", json.dumps(si))
        m.notify("notifications/initialized")
        r = m.call("tools/list")
        nomi = {t["name"] for t in r.get("result", {}).get("tools", [])}
        attesi = {"facto_status", "facto_brief", "facto_search", "facto_add_fact",
                  "facto_close_fact", "facto_handoff", "facto_add_area"}
        check(attesi <= nomi, "MCP tools/list (7 tool core)", ", ".join(sorted(nomi)))
        r = m.call("tools/call", {"name": "facto_add_area",
                                  "arguments": {"slug": "app", "path": "src", "label": "App"}})
        check("✓ area 'app'" in testo_tool(r), "MCP facto_add_area", testo_tool(r))
        r = m.call("tools/call", {"name": "facto_add_fact",
                                  "arguments": {"area": "app", "type": "stato",
                                                "text": "smoke: primo stato dell'area app"}})
        check("✓ fact recorded" in testo_tool(r), "MCP facto_add_fact", testo_tool(r))
        r = m.call("tools/call", {"name": "facto_search", "arguments": {"text": "primo stato"}})
        check("smoke: primo stato" in testo_tool(r), "MCP facto_search ritrova il fatto")
        # IL CASO WCA: questo server MCP e' partito quando il progetto era VUOTO.
        # Senza rilettura del config, l'area appena creata non esiste per lui e
        # facto_brief risponde «Unknown area» — mentre il CLI la vede benissimo.
        r = m.call("tools/call", {"name": "facto_brief", "arguments": {"area": "app"}})
        tb = testo_tool(r)
        check("Unknown area" not in tb and "app" in tb.lower(),
              "MCP: vede un'area creata DOPO il suo avvio (config riletto)", tb[:70])
        r = m.call("tools/call", {"name": "facto_status", "arguments": {}})
        ts = testo_tool(r)
        # e il semaforo non deve gridare «no status recorded» col fatto appena scritto
        check("app" in ts.lower() and "no status recorded" not in ts,
              "MCP status: niente falso «nessuno stato» su un'area appena scritta",
              [l for l in ts.splitlines() if "app" in l.lower()][:1])
        m.close()
    except Exception as e:
        fail("MCP round-trip", str(e))

    # --- fase 6: claude-hook, ramo DAILY (ora il config ha l'area) ------------
    rc, out, _ = sh([FACTO, "claude-hook"], cwd=tmp, env=env,
                    inp=json.dumps({"cwd": proj}))
    try:
        ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
    except Exception:
        ctx = ""
    # il reminder daily deve ORDINARE all'agente di orientare l'umano e proporre
    # i prossimi passi: senza, descrive lo stato e si ferma (difetto del collaudo).
    check(rc == 0 and "[Facto]" in ctx and "first-run onboarding" not in ctx
          and ("PROPOSE" in ctx or "ORIENT" in ctx),
          "claude-hook ramo daily: brief + istruzione di orientare/proporre",
          (ctx[ctx.find("[Facto]"):][:90] + "…") if "[Facto]" in ctx else out[:120])

    # --- fase 7: la CLI del ciclo quotidiano ----------------------------------
    # PARALLELO: il README promette «piu' agenti insieme». Quattro scritture
    # simultanee sullo stesso DB non devono perdere nulla (SQLite WAL + attesa).
    import concurrent.futures as _cf
    with _cf.ThreadPoolExecutor(max_workers=4) as ex:
        esiti = list(ex.map(
            lambda i: sh([FACTO, "add", "app", "nota", f"parallelo {i}"], cwd=proj, env=env)[0],
            range(4)))
    n_par = 0
    try:
        _c = sqlite3.connect(os.path.join(proj, ".facto", "facto.db"))
        n_par = _c.execute("SELECT COUNT(*) FROM fatti WHERE contenuto LIKE 'parallelo %'").fetchone()[0]
        _c.close()
    except Exception:
        pass
    check(all(e == 0 for e in esiti) and n_par == 4,
          "quattro scritture SIMULTANEE: nessun fatto perso", f"{n_par}/4 nel DB")

    rc, out, _ = sh([FACTO, "add", "app", "decisione", "smoke: decisione di prova"], cwd=proj, env=env)
    check(rc == 0, "facto add", out.strip()[:80])
    rc, out, _ = sh([FACTO, "close", "app", "decisione", "--like", "smoke"], cwd=proj, env=env)
    check(rc == 0, "facto close --like", out.strip()[:80])
    hpath = os.path.join(tmp, "handoff.txt")
    with open(hpath, "w", encoding="utf-8") as fh:
        fh.write("FATTO: smoke run.\nPROSSIMO: niente, sono un test.\n")
    rc, out, _ = sh([FACTO, "handoff", "app", "--file", hpath], cwd=proj, env=env)
    check(rc == 0, "facto handoff --file", out.strip()[:80])
    rc, out, _ = sh([FACTO, "brief", "app"], cwd=proj, env=env)
    check(rc == 0 and "smoke run" in out, "facto brief mostra l'handoff")
    rc, out, _ = sh([FACTO, "status"], cwd=proj, env=env)
    check(rc == 0 and "TRUST LIGHT" in out, "facto status (semaforo)")
    rc, out, _ = sh([FACTO, "doctor"], cwd=proj, env=env)
    check(rc == 0 and "command on PATH" in out, "facto doctor (incluso check PATH)",
          next((l.strip() for l in out.splitlines() if "PATH" in l), "")[:100])

    # --- fase 7-bis: tray opt-in (solo la parte headless: autostart on/status/off)
    # L'ICONA è GUI e non si prova in CI — resta il collaudo a mano. --no-launch
    # evita di accendere processi in CI.
    rc, out, err = sh([FACTO, "tray", "on", "--no-launch"], cwd=proj, env=env)
    check(rc == 0 and "ON" in out, "facto tray on (autostart registrato)",
          (out.strip().splitlines()[0][:80] if out.strip()
           else f"rc={rc} stderr: {err.strip()[-200:]}"))
    rc, out, _ = sh([FACTO, "tray", "status"], cwd=proj, env=env)
    check(rc == 0 and "ON" in out, "facto tray status (lo vede)", out.strip()[:80])
    rc, out, _ = sh([FACTO, "tray", "off"], cwd=proj, env=env)
    check(rc == 0 and "OFF" in out, "facto tray off (autostart rimosso)", out.strip().splitlines()[0][:80] if out.strip() else "")
    rc, out, _ = sh([FACTO, "tray", "status"], cwd=proj, env=env)
    check(rc == 0 and "OFF" in out, "facto tray status (spento davvero)")

    # --- fase 8: post-commit -> auto-ingest nel DB ----------------------------
    with open(os.path.join(proj, "src", "file.txt"), "w", encoding="utf-8") as fh:
        fh.write("x\n")
    rc, _, err = sh(["git", "add", "-A"], cwd=proj, env=env)
    rc2, _, err2 = sh(["git", "commit", "-m", "feat: smoke change"], cwd=proj, env=env)
    n_git_fatti = 0
    if rc == 0 and rc2 == 0:
        try:
            con = sqlite3.connect(os.path.join(proj, ".facto", "facto.db"))
            n_git_fatti = con.execute(
                "SELECT COUNT(*) FROM fatti WHERE tipo='git' AND valido_fino_a IS NULL").fetchone()[0]
            con.close()
        except Exception as e:
            err2 = str(e)
    check(rc == 0 and rc2 == 0 and n_git_fatti >= 1,
          "post-commit auto-ingest (fatto 'git' nel DB)",
          f"{n_git_fatti} fatti git" if n_git_fatti else (err or err2).strip()[-160:])

    # --- fase 9: dashboard web (server + pagina + API) ------------------------
    porta = porta_libera()
    dp = subprocess.Popen([FACTO, "dashboard", "--port", str(porta), "--no-open"],
                          cwd=proj, env=env, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
    base = f"http://127.0.0.1:{porta}"
    pagina, stato, derr = "", {}, ""
    scritto, ritrovato, area_a_caldo = {}, False, False
    area_web = {}
    try:
        fine = time.time() + 40
        while time.time() < fine:
            try:
                with urllib.request.urlopen(base + "/", timeout=4) as r:
                    pagina = r.read().decode("utf-8", "replace")
                break
            except Exception as e:
                derr = str(e)
                if dp.poll() is not None:
                    derr = f"server morto rc={dp.poll()}"
                    break
                time.sleep(0.4)
        if pagina:
            with urllib.request.urlopen(base + "/api/state", timeout=5) as r:
                stato = json.loads(r.read().decode("utf-8", "replace"))
            # scrittura DAL BROWSER (Componi) col server ANCORA VIVO
            try:
                req = urllib.request.Request(
                    base + "/api/write/fatto",
                    data=json.dumps({"progetto": "app", "tipo": "nota",
                                     "contenuto": "smoke: scritto dal browser (free)"}).encode("utf-8"),
                    headers={"Content-Type": "application/json"}, method="POST")
                with urllib.request.urlopen(req, timeout=5) as r:
                    scritto = json.loads(r.read().decode("utf-8", "replace"))
                with urllib.request.urlopen(base + "/api/state", timeout=5) as r:
                    st2 = json.loads(r.read().decode("utf-8", "replace"))
                ritrovato = any("scritto dal browser" in (f.get("testo") or "")
                                for f in st2.get("fatti", []))
            except Exception as e:
                scritto = {"errore": str(e)}
            # HOT-RELOAD delle aree: e' il flusso dell'onboarding — la dashboard
            # e' aperta mentre l'agente crea le aree. Se il config si leggesse
            # solo all'avvio, resterebbe vuota per sempre.
            try:
                sh([FACTO, "add-area", "live", "src", "--label", "Added live"], cwd=proj, env=env)
                # e un FATTO dentro l'area appena nata: e' il caso vero segnalato
                # dal collaudo (un agente scrive un handoff in un'area creata dopo
                # l'avvio della dashboard). Se l'area non viene ricaricata, il
                # fatto non ha un nodo a cui attaccarsi e sparisce dal grafo.
                sh([FACTO, "add", "live", "stato", "scritto nell'area appena nata"],
                   cwd=proj, env=env)
                with urllib.request.urlopen(base + "/api/state", timeout=5) as r:
                    st3 = json.loads(r.read().decode("utf-8", "replace"))
                area_a_caldo = (any(p.get("slug") == "live" for p in st3.get("progetti", []))
                                and any(f.get("progetto") == "live"
                                        for f in st3.get("fatti", [])))
                # crea/rimuovi AREA dalla dashboard (Componi): chi non vive nel
                # terminale deve poter disegnare la struttura da browser.
                for op, dati, atteso in (
                        ("area", {"slug": "dashcreata", "path": "src"}, "dashcreata"),
                        ("area-remove", {"slug": "dashcreata"}, "removed")):
                    rq = urllib.request.Request(
                        base + "/api/write/" + op, data=json.dumps(dati).encode("utf-8"),
                        headers={"Content-Type": "application/json"}, method="POST")
                    with urllib.request.urlopen(rq, timeout=5) as r:
                        area_web[op] = json.loads(r.read().decode("utf-8", "replace"))
                    if atteso not in str(area_web[op]):
                        area_web[op] = {"errore": "risposta inattesa", **area_web[op]}
            except Exception as e:
                area_a_caldo = False
                derr = derr or str(e)
    finally:
        dp.kill()
        try:                       # l'output del server e' la diagnosi del fail
            srv_out = (dp.communicate(timeout=5)[0] or "").strip()
        except Exception:
            srv_out = ""
    # se il server muore, la pagina DEVE dirlo: prima i fetch falliti venivano
    # ingoiati (.catch vuoto) e restavano a schermo i dati di un'altra area.
    check("offBar" in pagina and "off_brief" in pagina,
          "dashboard: c'e' l'avviso di server irraggiungibile (niente errori muti)")
    # e deve poter SPARIRE: con un id, [hidden] perde contro #offBar{display:flex}
    # e il banner resta a schermo col server vivo (successo davvero, su fire-lab).
    check("#offBar[hidden]" in pagina,
          "dashboard: l'avviso sa anche NASCONDERSI (regola [hidden] esplicita)")
    check("<html" in pagina.lower() or "<!doctype" in pagina.lower(),
          "facto dashboard serve Mission Control su /",
          "" if pagina else (derr[:100] + " · server: " + srv_out[:200].replace("\n", " | ")))
    check(stato.get("edizione") == "free", "dashboard della wheel = edizione FREE",
          str(stato.get("edizione")))
    # decisione 23 lug: Componi anche nel Free — la wheel (core puro) deve scrivere.
    check(scritto.get("ok") is True and ritrovato,
          "Componi nel Free: POST /api/write/fatto scrive e il fatto riappare",
          str(scritto)[:100])
    check(area_a_caldo,
          "dashboard: area E fatti creati MENTRE e' aperta (hot-reload del config)")
    check(area_web.get("area", {}).get("ok") is True and area_web.get("area-remove", {}).get("ok") is True,
          "dashboard: si crea e si rimuove un'AREA dal browser (Componi)",
          str(area_web.get("area", {}).get("msg", ""))[:70])
    check(isinstance(stato, dict) and stato, "dashboard /api/state risponde JSON",
          ", ".join(sorted(stato)[:6]))

    return riepilogo()


def riepilogo():
    n_ok = sum(1 for e, _, _ in RES if e)
    n_ko = len(RES) - n_ok
    print("  " + "-" * 58)
    if n_ko:
        print(f"  ESITO: ROSSO — {n_ko} FAIL su {len(RES)} check")
        for e, nome, det in RES:
            if not e:
                print(f"    ✗ {nome}" + (f" — {det}" if det else ""))
    else:
        print(f"  ESITO: VERDE — {n_ok}/{len(RES)} check passati")
    return 1 if n_ko else 0


if __name__ == "__main__":
    sys.exit(main())
