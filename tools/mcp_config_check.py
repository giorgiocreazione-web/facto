#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FACTO — prova DETERMINISTICA del multi-agente (stdlib pura, nessuna app reale).

La domanda: «Facto si aggancia davvero a VS Code / Cursor / Codex / Gemini?»
Le app reali dipendono da login, licenze e bug loro — non deterministico.
Questo test toglie le app di mezzo e prova il CONTRATTO: prende il config che
Facto scrive per OGNI tool (la chiave `servers` di VS Code, il TOML di Codex,
`mcpServers` di Cursor/Gemini/base), lo interpreta ESATTAMENTE come farebbe
quel tool, avvia il server MCP che quel config descrive e fa un round-trip di
lettura+scrittura. In piu' prova un TOOL SCONOSCIUTO — nessun connector dedicato,
solo il kit universale (`facto connect any` -> command=facto, args=[mcp-serve]) —
a dimostrare che il meccanismo non dipende dal tool: funziona anche per un client
mai visto o che non esiste ancora. Se passa, l'unico modo in cui l'app reale può
fallire è un bug dell'app — non di Facto.

Bonus: ogni tool scrive un fatto marcato col proprio nome nella STESSA memoria;
alla fine li conta tutti -> «N config di N tool diversi, una sola memoria».

Uso:  python tools/mcp_config_check.py
Exit: 0 = tutti i config avviano un server MCP funzionante; 1 = almeno uno no.
"""
import glob
import json
import os
import queue
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WIN = os.name == "nt"
RES = []


def ok(n, d=""):   RES.append((True, n, d));  print(f"  [ OK ] {n}" + (f"  · {d}" if d else ""))
def bad(n, d=""):  RES.append((False, n, d)); print(f"  [FAIL] {n}" + (f"  · {d}" if d else ""))
def chk(c, n, d=""): (ok if c else bad)(n, d); return bool(c)


def sh(cmd, cwd=None, env=None, inp=None, timeout=90):
    try:
        r = subprocess.run(cmd, cwd=cwd, env=env, input=inp, capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=timeout)
        return r.returncode, r.stdout or "", r.stderr or ""
    except Exception as e:
        return -1, "", str(e)


# ---- client MCP minimale (una riga JSON per messaggio, su stdio) --------------
class MCP:
    def __init__(self, cmd, cwd, env):
        self.p = subprocess.Popen(cmd, cwd=cwd, env=env, stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  text=True, encoding="utf-8", errors="replace")
        self.q = queue.Queue(); self.rid = 0
        threading.Thread(target=self._r, daemon=True).start()

    def _r(self):
        for line in self.p.stdout:
            self.q.put(line)
        self.q.put(None)

    def call(self, method, params=None, timeout=25):
        self.rid += 1; rid = self.rid
        self.p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": rid,
                                       "method": method, "params": params or {}}) + "\n")
        self.p.stdin.flush()
        end = time.time() + timeout
        while time.time() < end:
            try:
                line = self.q.get(timeout=max(0.1, end - time.time()))
            except queue.Empty:
                break
            if line is None:
                raise RuntimeError("server chiuso (morto)")
            line = line.strip()
            if not line:
                continue
            try:
                m = json.loads(line)
            except json.JSONDecodeError:
                continue
            if m.get("id") == rid:
                return m
        raise RuntimeError(f"nessuna risposta a {method}")

    def notify(self, method):
        self.p.stdin.write(json.dumps({"jsonrpc": "2.0", "method": method}) + "\n")
        self.p.stdin.flush()

    def close(self):
        try:
            self.p.stdin.close(); self.p.wait(timeout=10)
        except Exception:
            self.p.kill()


def text_of(resp):
    try:
        return resp["result"]["content"][0]["text"]
    except Exception:
        return ""


# ---- estrazione del comando MCP dal config di CIASCUN tool --------------------
def _toml_facto(path):
    """command+args del server facto da un .codex/config.toml, come lo legge Codex."""
    try:
        import tomllib
        with open(path, "rb") as fh:
            d = tomllib.load(fh)
        s = d["mcp_servers"]["facto"]
        return s["command"], list(s.get("args", []))
    except ModuleNotFoundError:
        # Python < 3.11: mini-parse del blocco [mcp_servers.facto] (ci basta)
        cmd, args = None, []
        cur = None
        with open(path, encoding="utf-8-sig") as fh:
            for ln in fh:
                ln = ln.strip()
                if ln.startswith("[") and ln.endswith("]"):
                    cur = ln[1:-1]
                elif cur == "mcp_servers.facto" and "=" in ln:
                    k, v = [x.strip() for x in ln.split("=", 1)]
                    if k == "command":
                        cmd = v.strip('"')
                    elif k == "args":
                        args = json.loads(v)
        return cmd, args


def sources(proj):
    """(etichetta-tool, command, args) letti dal formato NATIVO di ogni config."""
    out = []
    def js(path, key):
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
        s = d[key]["facto"]
        return s["command"], list(s.get("args", []))
    mp = {
        "claude-code/mcp (.mcp.json → mcpServers)": (".mcp.json", "mcpServers"),
        "cursor (.cursor/mcp.json → mcpServers)":   (".cursor/mcp.json", "mcpServers"),
        "vscode (.vscode/mcp.json → servers)":      (".vscode/mcp.json", "servers"),
        "gemini (.gemini/settings.json → mcpServers)": (".gemini/settings.json", "mcpServers"),
    }
    for label, (rel, key) in mp.items():
        path = os.path.join(proj, *rel.split("/"))
        try:
            c, a = js(path, key); out.append((label, c, a))
        except Exception as e:
            out.append((label, None, str(e)))
    # codex: TOML
    tp = os.path.join(proj, ".codex", "config.toml")
    try:
        c, a = _toml_facto(tp); out.append(("codex (.codex/config.toml → mcp_servers)", c, a))
    except Exception as e:
        out.append(("codex (.codex/config.toml → mcp_servers)", None, str(e)))
    # TOOL SCONOSCIUTO: nessun connector dedicato, solo il kit universale
    # (`facto connect any` -> command=facto, args=[mcp-serve]). Prova che NON
    # dipendiamo dal tool: un client mai visto, configurato a mano col kit, funziona.
    out.append(("tool SCONOSCIUTO (kit universale — nessun connector dedicato)", "facto", ["mcp-serve"]))
    return out


def main():
    print("================  FACTO — prova deterministica multi-agente  ================")
    print(f"  OS: {sys.platform} · Python {sys.version.split()[0]}")

    # `facto` come lo lancerebbe un tool (comando nel PATH); in CI puo' essere
    # installato come package ma non nel PATH -> ripiego su `python -m facto`
    # (equivalente, gia' provato dallo smoke). FACTO_CMD e' la lista-base.
    if shutil.which("facto"):
        FACTO_CMD = [shutil.which("facto")]
    else:
        rc, _, _ = sh([sys.executable, "-m", "facto", "--version"])
        FACTO_CMD = [sys.executable, "-m", "facto"] if rc == 0 else None
    if not FACTO_CMD:
        print("  [FAIL] facto non disponibile (né nel PATH né come package `python -m facto`).")
        print("         Installa la wheel:  uv tool install <facto-...whl>")
        return 1

    tmp = tempfile.mkdtemp(prefix="facto-mcpchk-")
    try:
        proj = os.path.join(tmp, "proj"); os.makedirs(proj)
        env = dict(os.environ)
        for k in ("FACTO_CONFIG", "FACTO_DB", "FACTO_AREA", "FACTO_FONTE",
                  "REGISTRO_CONFIG", "REGISTRO_DB", "REGISTRO_AREA"):
            env.pop(k, None)
        # git (serve al connect git) + config + TUTTI i target, espliciti
        for cmd in (["git", "init"], ["git", "config", "user.email", "a@b.c"],
                    ["git", "config", "user.name", "x"]):
            sh(cmd, cwd=proj, env=env)
        rc, out, err = sh(FACTO_CMD + ["connect", "claude-code", "mcp", "cursor",
                          "vscode", "codex", "gemini", "agents", "git"], cwd=proj, env=env)
        if not chk(rc == 0, "facto connect (tutti i target)", err.strip()[-160:] if rc else ""):
            return done()
        # un'area su cui lavorare
        sh(FACTO_CMD + ["connect"], cwd=proj, env=env)  # scrive facto.config.json se manca
        cfgp = os.path.join(proj, "facto.config.json")
        with open(cfgp, encoding="utf-8-sig") as fh:
            cfg = json.load(fh)
        cfg["projects"] = {"t": {"path": ".", "label": "T"}}
        with open(cfgp, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(cfg, fh, ensure_ascii=False, indent=2)

        print("\n  Per ogni tool: avvio il server MCP che il SUO config descrive,")
        print("  handshake + scrivo un fatto marcato + lo rileggo (round-trip).\n")

        attesi = {"facto_status", "facto_brief", "facto_add_fact", "facto_search"}
        marcatori = []
        for label, command, args in sources(proj):
            if not command:
                bad(f"{label}", f"config non leggibile: {args}"); continue
            # risolve il command come farebbe il tool: "facto" -> FACTO_CMD
            # (PATH o `python -m facto`); altri comandi via PATH
            cmdline = (FACTO_CMD + list(args)) if command == "facto" \
                else [shutil.which(command) or command] + list(args)
            try:
                m = MCP(cmdline, cwd=proj, env=env)
                r = m.call("initialize", {"protocolVersion": "2024-11-05",
                                          "capabilities": {}, "clientInfo": {"name": "chk", "version": "0"}})
                if r.get("result", {}).get("serverInfo", {}).get("name") != "facto":
                    m.close(); bad(f"{label}", "initialize non-facto"); continue
                m.notify("notifications/initialized")
                names = {t["name"] for t in m.call("tools/list").get("result", {}).get("tools", [])}
                if not attesi <= names:
                    m.close(); bad(f"{label}", "tool mancanti"); continue
                mark = "reached-via-" + label.split(" ")[0]
                marcatori.append(mark)
                w = m.call("tools/call", {"name": "facto_add_fact",
                                          "arguments": {"area": "t", "type": "nota", "text": mark}})
                s = m.call("tools/call", {"name": "facto_search", "arguments": {"text": mark}})
                m.close()
                good = "✓ fact recorded" in text_of(w) and mark in text_of(s)
                chk(good, f"{label}", "handshake + scrittura + rilettura OK" if good else "round-trip KO")
            except Exception as e:
                bad(f"{label}", str(e))

        # PROVA REGINA: una sola memoria raggiunta da N config diversi
        db = os.path.join(proj, ".facto", "facto.db")
        try:
            con = sqlite3.connect(db)
            n = con.execute("SELECT COUNT(DISTINCT contenuto) FROM fatti WHERE contenuto LIKE 'reached-via-%'").fetchone()[0]
            con.close()
        except Exception as e:
            n = -1
        chk(n == len(marcatori) and n >= 5,
            "UNA memoria, tanti agenti — inclusi i tool sconosciuti (kit universale)",
            f"{n} fatti da {len(marcatori)} sorgenti diverse" if n >= 0 else "DB illeggibile")
        return done()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def done():
    nko = sum(1 for e, _, _ in RES if not e)
    print("  " + "-" * 60)
    if nko:
        print(f"  ESITO: ROSSO — {nko}/{len(RES)} FAIL")
        for e, n, d in RES:
            if not e:
                print(f"    ✗ {n}" + (f" — {d}" if d else ""))
    else:
        print(f"  ESITO: VERDE — {len(RES)}/{len(RES)} · ogni config di ogni tool avvia Facto e legge/scrive")
    return 1 if nko else 0


if __name__ == "__main__":
    sys.exit(main())
