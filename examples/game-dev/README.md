# Esempio: progetto di creazione giochi

Configurazione pronta del **Facto** per un team (o un solo dev + agenti AI) che
sviluppa un videogioco. Mostra il caso reale: più moduli, git attivo, file d'identità.

## Cosa rappresenta

| Modulo (`projects`) | Cartella | A cosa serve |
|---|---|---|
| `engine`   | `src/engine`   | Core del motore (loop, rendering, fisica) |
| `gameplay` | `src/gameplay` | Meccaniche, regole di gioco, bilanciamento |
| `ui`       | `src/ui`       | Menu, HUD, schermate |
| `content`  | `content`      | Livelli, dialoghi, progressione |
| `assets`   | `assets`       | Arte e audio |
| `tooling`  | `tools`        | Build/strumenti (solo "stato", fuori dal semaforo) |

`identity_files` punta al **game design document** e alle **regole del team**: vengono
letti a ogni apertura sessione, così ogni agente AI parte già sapendo visione e paletti.

## Come si usa

1. Copia `facto.config.json` nella radice del tuo progetto-gioco (adatta i `path`).
2. Cambia `brand` col nome del gioco.
3. Da quella cartella:
   ```
   python /percorso/facto/core/mem.py init
   python /percorso/facto/core/mem.py dashboard
   ```
4. (Opzionale) aggancia l'hook a Claude Code: vedi `hooks/settings.example.json`.

## Senza git?

Se non versioni con git (o usi un altro flusso), metti `"git": { "enabled": false }`:
lo stato lo aggiorni a mano con `mem.py add <modulo> stato "..."` e `mem.py handoff`.
Il resto (bussola, ricerca, dashboard, storia bi-temporale) funziona identico.
