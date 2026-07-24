#!/usr/bin/env bash
# on-session-start.sh — SessionStart hook (FACTO) per Claude Code su Mac/Linux
# Equivalente di on-session-start.ps1. Inietta identita' + stato fresco all'apertura sessione.
# Generico: percorsi/progetti vivono in facto.config.json, NON qui dentro.

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MEMPY="$DIR/../core/mem.py"

if command -v python3 >/dev/null 2>&1; then PY=python3; else PY=python; fi

# payload JSON dell'hook su stdin: ne estraiamo il cwd (best-effort, senza dipendenze).
STDIN="$(cat 2>/dev/null || true)"
CWD="$(pwd)"
CWD_JSON="$(printf '%s' "$STDIN" | sed -n 's/.*"cwd"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')"
[ -n "$CWD_JSON" ] && CWD="$CWD_JSON"

# Se il config non sta nella root del progetto, esporta il percorso:
# export FACTO_CONFIG="/percorso/al/facto.config.json"

BRIEF="$("$PY" "$MEMPY" session-start --cwd "$CWD" 2>/dev/null || true)"
[ "${#BRIEF}" -lt 20 ] && BRIEF="Facto: motore non raggiungibile. Verifica Python e facto.config.json."

# emette il JSON dell'hook in modo robusto (escaping a cura di Python)
"$PY" - "$BRIEF" <<'PY'
import json, sys
print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                          "additionalContext": sys.argv[1]}}))
PY
