#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_wheel.py — costruisce la wheel del prodotto Free in STDLIB PURA.

Perche' non `pip wheel .`: su una macchina pulita (o dietro MITM aziendale)
la build isolata di pip deve SCARICARE setuptools; questo builder no — una
wheel e' solo uno zip con metadati, e ce la facciamo in casa (stessa filosofia
zero-dipendenze del prodotto). `pip install dist/<wheel>` funziona OFFLINE.

Uso:  python tools/build_wheel.py [--out dist]
"""
import argparse
import base64
import hashlib
import os
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORE = os.path.join(ROOT, "core")

# Nome della DISTRIBUZIONE su PyPI (ratificato 24 lug): `facto` secco e' occupato
# da un pacchetto altrui, quindi si installa `facto-memory` — e dice pure cosa fa.
# Il package importabile e il comando quotidiano restano `facto`: l'etichetta
# lunga la vedi una volta sola, all'installazione.
DIST_NAME = "facto-memory"
REPO = "https://github.com/giorgiocreazione-web/facto"


def leggi_version():
    with open(os.path.join(ROOT, "VERSION"), encoding="utf-8") as fh:
        return fh.read().strip()


def _hash_b64(data):
    return base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()


def build(out_dir):
    ver = leggi_version()
    # PEP 427: nel NOME FILE (e nella dist-info) il nome va normalizzato — i
    # trattini diventano underscore, altrimenti pip rifiuta la wheel con
    # «invalid wheel filename». Il campo `Name:` dei metadati resta col trattino.
    fname = DIST_NAME.replace("-", "_")
    dist_info = f"{fname}-{ver}.dist-info"
    wheel_name = f"{fname}-{ver}-py3-none-any.whl"
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, wheel_name)

    # contenuto del package: i moduli del core + dashboard html + i playbook (.md).
    # Ricorsivo cosi' core/playbooks/*.md entra come facto/playbooks/*.md.
    files = []
    for base, dirs, fnames in os.walk(CORE):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", ".pytest_cache")]
        for f in sorted(fnames):
            if f.endswith((".py", ".html", ".md", ".ico")):
                full = os.path.join(base, f)
                rel = os.path.relpath(full, CORE).replace("\\", "/")
                files.append((full, f"facto/{rel}"))

    # La pagina PyPI del pacchetto E' il README: entra qui come long_description.
    # Se manca, meglio accorgersene ora che scoprire una pagina vuota pubblicata.
    readme_path = os.path.join(ROOT, "README.free.md")
    with open(readme_path, encoding="utf-8") as fh:
        long_desc = fh.read()

    metadata = "\n".join([
        "Metadata-Version: 2.1",
        f"Name: {DIST_NAME}",
        f"Version: {ver}",
        "Summary: Project memory for AI agents that knows when it's wrong — "
        "dated facts, verified against git. Local, zero dependencies.",
        "Author: Giorgio Cristea",
        "License: MIT",
        f"Project-URL: Homepage, {REPO}",
        f"Project-URL: Repository, {REPO}",
        f"Project-URL: Issues, {REPO}/issues",
        f"Project-URL: Changelog, {REPO}/blob/main/CHANGELOG.md",
        "Keywords: ai,ai-agents,llm,memory,mcp,model-context-protocol,claude,"
        "cursor,copilot,cli,local-first,sqlite,developer-tools",
        "Classifier: Development Status :: 4 - Beta",
        "Classifier: Intended Audience :: Developers",
        "Classifier: License :: OSI Approved :: MIT License",
        "Classifier: Operating System :: OS Independent",
        "Classifier: Programming Language :: Python :: 3",
        "Classifier: Programming Language :: Python :: 3.9",
        "Classifier: Programming Language :: Python :: 3.10",
        "Classifier: Programming Language :: Python :: 3.11",
        "Classifier: Programming Language :: Python :: 3.12",
        "Classifier: Programming Language :: Python :: 3.13",
        "Classifier: Topic :: Software Development",
        "Classifier: Topic :: Software Development :: Documentation",
        "Classifier: Topic :: Utilities",
        "Requires-Python: >=3.9",
        "Description-Content-Type: text/markdown",
        "",
        long_desc, ""])
    wheel_meta = "\n".join([
        "Wheel-Version: 1.0",
        "Generator: facto-build (stdlib)",
        "Root-Is-Purelib: true",
        "Tag: py3-none-any",
        "", ""])
    entry_points = "\n".join([
        "[console_scripts]",
        "facto = facto.cli:main",
        "", ""])

    record_rows = []
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for src, arc in files:
            with open(src, "rb") as fh:
                data = fh.read()
            z.writestr(arc, data)
            record_rows.append(f"{arc},sha256={_hash_b64(data)},{len(data)}")
        for arc, testo in ((f"{dist_info}/METADATA", metadata),
                           (f"{dist_info}/WHEEL", wheel_meta),
                           (f"{dist_info}/entry_points.txt", entry_points)):
            data = testo.encode("utf-8")
            z.writestr(arc, data)
            record_rows.append(f"{arc},sha256={_hash_b64(data)},{len(data)}")
        record_rows.append(f"{dist_info}/RECORD,,")
        z.writestr(f"{dist_info}/RECORD", "\n".join(record_rows) + "\n")

    print(f"wheel: {path}  ({len(files)} file di package)")
    return path


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "dist"))
    a = ap.parse_args()
    build(os.path.abspath(a.out))
