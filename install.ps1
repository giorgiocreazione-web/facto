# Facto — installer per Windows.
#
#   irm https://raw.githubusercontent.com/giorgiocreazione-web/facto/main/install.ps1 | iex
#
# Oppure, da una copia locale:   .\install.ps1  [-Wheel <percorso.whl>]
#
# Non chiede nulla, non lascia sporcizia, e alla fine dice cosa fare.
# Sceglie da solo la via migliore disponibile: uv (consigliata) -> pipx -> pip.
param([string]$Wheel = "")

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"   # niente barre di download a schermo

$C = @{ dim = "DarkGray"; ok = "Green"; hi = "Cyan"; warn = "Yellow"; bad = "Red" }
function Say($t, $c = "Gray") { Write-Host $t -ForegroundColor $c }
function Step($t) { Write-Host "  $t" -ForegroundColor $C.dim }
function Good($t) { Write-Host "  [OK] " -ForegroundColor $C.ok -NoNewline; Write-Host $t }
function Bad($t) { Write-Host "  [!!] " -ForegroundColor $C.bad -NoNewline; Write-Host $t }

Say ""
Say "  facto" $C.hi
Say "  project memory for people who build with AI agents" $C.dim
Say ""

# ---------------------------------------------------------------- sorgente
# Wheel locale se indicata (o se ne trovo una accanto allo script), altrimenti GitHub.
if (-not $Wheel) {
    $qui = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
    $cand = Get-ChildItem -Path $qui -Filter "facto-*.whl" -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($cand) { $Wheel = $cand.FullName }
}
if ($Wheel) {
    $sorgente = $Wheel
    Step "sorgente: $(Split-Path $Wheel -Leaf)"
} else {
    $sorgente = "git+https://github.com/giorgiocreazione-web/facto.git"
    Step "sorgente: GitHub"
}

# ---------------------------------------------------------------- installa
function Has($cmd) { [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }

$via = $null
if (Has "uv") { $via = "uv" }
elseif (Has "pipx") { $via = "pipx" }
elseif (Has "python") { $via = "pip" }

if (-not $via) {
    # Nessun Python sul sistema: installo uv, che se lo porta dietro da solo.
    Step "nessun Python trovato: installo uv (si porta dietro Python)"
    try {
        Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
        $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
        if (Has "uv") { $via = "uv" }
    } catch {
        Bad "non sono riuscito a installare uv: $($_.Exception.Message)"
        Say ""
        Say "  Installa Python da https://python.org e rilancia questo script." $C.warn
        exit 1
    }
}

Step "installo con $via..."
# PowerShell 5.1: lo stderr di un programma esterno diventa un ErrorRecord e con
# ErrorActionPreference=Stop farebbe fallire tutto anche quando l'installazione
# e' andata bene (uv scrive il suo resoconto proprio li'). Si guarda il codice
# di uscita, non lo stderr.
$ErrorActionPreference = "Continue"
$log = switch ($via) {
    "uv"   { & uv tool install --force $sorgente 2>&1 | Out-String }
    "pipx" { & pipx install --force $sorgente 2>&1 | Out-String }
    "pip"  { & python -m pip install --user --upgrade --quiet $sorgente 2>&1 | Out-String }
}
$rc = $LASTEXITCODE
$ErrorActionPreference = "Stop"
if ($rc -ne 0) {
    Bad "installazione fallita (codice $rc)"
    if ($log) { Say ($log.Trim() -split "`n" | Select-Object -Last 4 | Out-String) $C.dim }
    exit 1
}

# ---------------------------------------------------------------- verifica
# uv mette i comandi in ~\.local\bin: se il PATH di QUESTA sessione non lo ha
# ancora, aggiungilo — così il controllo qui sotto non fallisce per un dettaglio.
$binDir = Join-Path $env:USERPROFILE ".local\bin"
if ((Test-Path $binDir) -and ($env:Path -notlike "*$binDir*")) { $env:Path = "$binDir;$env:Path" }

$ver = $null
try { $ver = (& facto --version) 2>$null } catch {}
if (-not $ver) {
    try { $ver = (& python -m facto --version) 2>$null } catch {}
}

Say ""
if ($ver) {
    Good "$ver"
} else {
    Bad "installato, ma il comando non risponde ancora"
    Say "     Apri un terminale NUOVO e prova:  facto --version" $C.warn
    Say "     (se ancora non va:  python -m facto --version)" $C.dim
}

Say ""
Say "  Ora, nella cartella di un tuo progetto:" $C.dim
Say "    facto connect --all" $C.hi
Say "  poi apri il tuo agente AI (claude, cursor...) e lascialo lavorare." $C.dim
Say ""
