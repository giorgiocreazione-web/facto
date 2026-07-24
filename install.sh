#!/bin/sh
# Facto — installer per macOS e Linux.
#
#   curl -LsSf https://raw.githubusercontent.com/giorgiocreazione-web/facto/main/install.sh | sh
#
# Oppure, da una copia locale:   ./install.sh  [percorso/facto-*.whl]
#
# Non chiede nulla, non lascia sporcizia, e alla fine dice cosa fare.
# Sceglie da solo la via migliore disponibile: uv (consigliata) -> pipx -> pip.
set -eu

DIM='\033[2m'; OK='\033[32m'; HI='\033[36m'; WARN='\033[33m'; BAD='\033[31m'; R='\033[0m'
say()  { printf '%b\n' "$1"; }
step() { printf '%b\n' "${DIM}  $1${R}"; }
good() { printf '%b%b\n' "${OK}  [OK] ${R}" "$1"; }
bad()  { printf '%b%b\n' "${BAD}  [!!] ${R}" "$1"; }
has()  { command -v "$1" >/dev/null 2>&1; }

say ""
say "${HI}  facto${R}"
say "${DIM}  project memory for people who build with AI agents${R}"
say ""

# ---------------------------------------------------------------- sorgente
WHEEL="${1:-}"
if [ -z "$WHEEL" ]; then
  # una wheel accanto allo script? (copia locale / cartella di release)
  QUI=$(CDPATH= cd -- "$(dirname -- "$0")" 2>/dev/null && pwd || echo ".")
  WHEEL=$(ls -t "$QUI"/facto-*.whl 2>/dev/null | head -1 || true)
fi
if [ -n "$WHEEL" ] && [ -f "$WHEEL" ]; then
  SORGENTE="$WHEEL"
  step "sorgente: $(basename "$WHEEL")"
else
  SORGENTE="git+https://github.com/giorgiocreazione-web/facto.git"
  step "sorgente: GitHub"
fi

# ---------------------------------------------------------------- installa
VIA=""
if has uv; then VIA="uv"
elif has pipx; then VIA="pipx"
elif has python3 && python3 -m pip --version >/dev/null 2>&1; then VIA="pip"
fi

if [ -z "$VIA" ]; then
  # Niente uv, niente pip (Debian/Ubuntu appena installati sono così):
  # uv è la via pulita e non chiede sudo — si porta dietro anche Python.
  step "né uv né pip disponibili: installo uv (non serve sudo)"
  if curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null 2>&1; then
    PATH="$HOME/.local/bin:$PATH"; export PATH
    has uv && VIA="uv"
  fi
  if [ -z "$VIA" ]; then
    bad "non sono riuscito a installare uv."
    say ""
    say "${WARN}  Installa uv a mano:  curl -LsSf https://astral.sh/uv/install.sh | sh${R}"
    say "${DIM}  (oppure, su Debian/Ubuntu:  sudo apt install pipx  e rilancia)${R}"
    exit 1
  fi
fi

step "installo con $VIA..."
case "$VIA" in
  uv)   uv tool install --force "$SORGENTE" >/dev/null 2>&1 || { bad "installazione fallita"; exit 1; } ;;
  pipx) pipx install --force "$SORGENTE"    >/dev/null 2>&1 || { bad "installazione fallita"; exit 1; } ;;
  pip)  python3 -m pip install --user --upgrade --quiet "$SORGENTE" || { bad "installazione fallita"; exit 1; } ;;
esac

# ---------------------------------------------------------------- verifica
# uv e pip --user mettono i comandi in ~/.local/bin: se questa shell non ce
# l'ha ancora nel PATH, aggiungilo per il controllo qui sotto.
[ -d "$HOME/.local/bin" ] && PATH="$HOME/.local/bin:$PATH" && export PATH

VER=$(facto --version 2>/dev/null || python3 -m facto --version 2>/dev/null || true)

say ""
if [ -n "$VER" ]; then
  good "$VER"
  case ":$PATH:" in
    *":$HOME/.local/bin:"*) : ;;
    *) say "${WARN}     Aggiungi ~/.local/bin al PATH del tuo profilo (.zshrc / .bashrc).${R}" ;;
  esac
else
  bad "installato, ma il comando non risponde ancora"
  say "${WARN}     Apri un terminale NUOVO e prova:  facto --version${R}"
  say "${DIM}     (se ancora non va:  python3 -m facto --version)${R}"
fi

say ""
say "${DIM}  Ora, nella cartella di un tuo progetto:${R}"
say "${HI}    facto connect --all${R}"
say "${DIM}  poi apri il tuo agente AI (claude, cursor...) e lascialo lavorare.${R}"
say ""
