# on-session-start.ps1 — SessionStart hook (FACTO) per Claude Code su Windows
# Inietta all'apertura sessione: identita' stabile (se configurata) + stato FRESCO verificato da git.
# Generico: percorsi/progetti vivono in facto.config.json, NON qui dentro.
#
# Installazione: vedi hooks/settings.example.json e docs/SETUP.md
# (di norma mantieni la struttura del repo: questo file in hooks/, il motore in core/).

$ErrorActionPreference = 'SilentlyContinue'

# Motore: percorso relativo a questo hook. Cambia solo se sposti i file altrove.
$MemPy = Join-Path $PSScriptRoot '..\core\mem.py'

# cwd della sessione (serve a mem.py per rilevare il progetto e trovare il config risalendo).
$cwd = (Get-Location).Path
try {
  $stdin = [Console]::In.ReadToEnd()
  if ($stdin) { $p = $stdin | ConvertFrom-Json; if ($p.cwd) { $cwd = $p.cwd } }
} catch {}

# Se il config non sta nella root del progetto, scommenta e indica il percorso:
# $env:FACTO_CONFIG = 'C:\percorso\al\facto.config.json'

$brief = ""
try {
  $brief = (& python $MemPy session-start --cwd "$cwd" | Out-String)
} catch {}

# Fallback robusto: se il motore non risponde, Claude non resta mai cieco.
if (-not $brief -or $brief.Trim().Length -lt 20) {
  $brief = "Facto: motore non raggiungibile. Verifica che Python sia nel PATH e che esista facto.config.json."
}

$out = @{ hookSpecificOutput = @{ hookEventName = 'SessionStart'; additionalContext = $brief } } | ConvertTo-Json -Depth 10 -Compress
Write-Output $out
