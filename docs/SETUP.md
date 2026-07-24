# Setup

## 0. The fast path (pip — recommended)

```bash
pip install <package-name>     # or pipx / uv tool install
cd your-project
facto init                     # config + DB + git ingest, areas auto-detected
facto connect --all            # Claude Code hook + MCP + git post-commit
facto dashboard                # Mission Control in the browser
```

That is the whole setup.

> **If `facto` is "not found" after install** (common on Windows with
> `pip install --user`): the scripts folder isn't on your PATH. Two fixes —
> install with **`pipx`** (it wires the PATH for you), or run it as
> **`python -m facto <command>`**, which works regardless of PATH.

Everything below is the **folder mode** (running the tool from a copied folder,
no pip) and the manual details — still fully supported, mostly useful for the
Pro/Max zip editions.

---

## 1. Prerequisiti

- **Python 3.8+** nel PATH (`python --version` o `python3 --version`).
- **git** (consigliato, non obbligatorio): serve per l'auto-verifica dello stato.
- Nessun altro requisito: il Registro usa solo la standard library di Python.

## 2. Installazione

> **Tre modi per creare `facto.config.json`** — dal più guidato al più manuale:
> - 🧭 **Wizard config** (consigliato): `python pro/wizard/wizard.py` — ti guida campo
>   per campo, con default intelligenti e validazione; sa anche **modificare** un
>   config esistente (aggiungi/rimuovi moduli) e fa un backup `.bak`.
> - 🚀 **Installer 1-click**: `python pro/installer/setup.py` — rileva il progetto e
>   scrive il config coi default, poi prepara DB + `doctor` + hook in un colpo solo.
> - ✍️ **A mano**: copia l'esempio e personalizzalo (passi sotto).

1. Copia la cartella `facto/` dove vuoi (es. accanto al tuo progetto, o dentro di esso).
2. Crea il file di configurazione nella **radice del tuo progetto**:
   ```
   cp facto/facto.config.example.json  facto.config.json
   ```
3. Apri `facto.config.json` e personalizzalo (vedi sezione 3).
4. Inizializza il database:
   ```
   python facto/core/mem.py init
   ```
5. Verifica che sia tutto a posto (prerequisiti, percorsi, DB):
   ```
   python facto/core/mem.py doctor
   ```
   Deve chiudere con **"Tutto a posto: sei pronto."** Se segnala qualcosa, ti dice cosa sistemare.

> **Primo avvio — semaforo ROSSO è normale:** appena creato, il Registro è vuoto e il semaforo è ROSSO (`nessuno stato registrato`). Lancia `python core/mem.py ingest-git` (se usi git) per catturare lo stato reale dai commit: diventa VERDE. Da quel momento il semaforo ti avvisa quando la memoria resta indietro rispetto al codice — è il suo lavoro, dirti *quando non fidarti*.

## 3. Il file `facto.config.json`

```json
{
  "brand": "Il Mio Progetto",
  "root": ".",
  "db_path": ".facto/facto.db",
  "git": { "enabled": true, "main_branch": "main" },
  "projects": {
    "core": { "path": "src",  "label": "Core" },
    "web":  { "path": "web",  "label": "Frontend Web" }
  },
  "self_project": null,
  "identity_files": []
}
```

| Campo | Significato |
|---|---|
| `brand` | Nome mostrato in dashboard e briefing. |
| `root` | Radice del progetto, **relativa al file di config**. `"."` = stessa cartella. |
| `db_path` | Dove vive il DB (relativo a `root`). Non versionarlo (già nel `.gitignore`). |
| `git.enabled` | `true` = stato auto-verificato da git. `false` = stato tenuto a mano. |
| `git.main_branch` | Nome del branch principale (`main`, `master`…). |
| `projects` | I moduli da tracciare: `slug → { path, label }`. Quanti ne vuoi. |
| `self_project` | Opzionale: una cartella di cui vuoi solo lo *stato*, fuori dal semaforo. `null` per ometterla. |
| `identity_files` | Opzionale: file letti **sempre** a inizio sessione (visione, regole). Path relativi a `root`. |

> Il motore cerca il config in quest'ordine: variabile d'ambiente `FACTO_CONFIG` →
> risalendo dalle cartelle a partire dalla directory corrente → accanto a `mem.py`.

> Non vuoi editarlo a mano? `python pro/wizard/wizard.py` genera o **aggiorna** questo
> file rispondendo a domande, e poi lo verifica col `doctor`.

## 4. Aggancio a Claude Code (briefing a ogni sessione)

Con l'hook, **ogni volta che apri una sessione** Claude riceve lo stato fresco del modulo su cui stai lavorando.

1. Apri (o crea) il `.claude/settings.json` del tuo progetto.
2. Copia il blocco `hooks` da [`hooks/settings.example.json`](../hooks/settings.example.json),
   correggendo il percorso dello script.
   - **Windows**: `on-session-start.ps1`
   - **Mac/Linux**: `on-session-start.sh` (rendilo eseguibile: `chmod +x`)
3. Riapri la sessione: vedrai in testa l'identità (se configurata) + il briefing git-verificato.

Se il config non sta nella radice del progetto, imposta `FACTO_CONFIG` dentro l'hook (c'è il commento pronto).

## 5. Uso senza Claude Code (qualsiasi altro AI/IDE)

Non serve un hook: a inizio sessione lancia tu il briefing e incollalo all'assistente:

```
python facto/core/mem.py session-start --cwd .
```

Oppure tieni aperta la **dashboard live** come cruscotto:

```
python facto/core/dashboard_server.py     # http://127.0.0.1:8780
```

Per **condividerla in rete** a un team, attiva il controllo accessi (login +
scoping per progetto) creando almeno un utente, poi esponila:

```
python pro/access/access.py add gio --role admin
python pro/access/access.py add team --role viewer --projects crm,sync
python core/dashboard_server.py --host 0.0.0.0
```

Senza utenti la dashboard resta aperta (uso locale). Mettila dietro un proxy
HTTPS se la esponi pubblicamente — vedi [`pro/access/README.md`](../pro/access/README.md).

## 6. Uso senza git

Metti `"git": { "enabled": false }`. In questa modalità:

- `ingest-git` non fa nulla; lo **stato** lo aggiorni tu:
  ```
  python core/mem.py add core stato "checkout flow completato, manca la mail di conferma"
  ```
- il **semaforo** guarda solo i bloccanti aperti (non potendo confrontare con git).
- tutto il resto (bussola, ricerca, storia bi-temporale, handoff, dashboard) funziona identico.

## 7. Ispezionare il database

Il DB è un normale file SQLite: aprilo con
[DB Browser for SQLite](https://sqlitebrowser.org/) per guardarci dentro quando vuoi.
Non sei mai chiuso dentro al tool.
