# Concetti

Perché il Facto è diverso da un file di note, e come ragiona.

## Il problema: la memoria che invecchia in silenzio

I sistemi di memoria in markdown falliscono sempre allo stesso modo:

1. **Staleness invisibile** — il documento dice "fatto", il codice dice altro, e nessuno se ne accorge.
2. **Cattura che non avviene** — "ricordati di aggiornare le note" è un buon proposito, non un sistema.
3. **Troppe fonti di verità** — README, note, commenti, memoria del tool: divergono.
4. **Ignora la realtà** — il vero stato è nel repo (branch, commit, lavoro in volo), non in un file di prosa.

Il Registro nasce per chiudere questi buchi con un **patto di misura**: non promette di essere
"il migliore", ti dice da solo quando *non* fidarti.

## Fatti datati e bi-temporali

L'unità non è la "nota", è il **fatto**: una riga con un tipo, un testo e due tempi.

- `valido_da` — quando il fatto è diventato vero **nel mondo**.
- `valido_fino_a` — `NULL` se è vero **ora**; una data se è stato superato.

Quando arriva un'informazione nuova, la vecchia **non si cancella**: si *chiude*
(`valido_fino_a` = oggi) e resta nella storia. Così puoi sempre chiedere "cosa era vero a
giugno?" e "perché è cambiato?". Niente è perso, niente mente.

```
ID 12  decisione  "salute a barra HP"      valido_da 2026-05-01  → chiuso 2026-06-18
ID 19  decisione  "salute a cuori"         valido_da 2026-06-18  → VERO ORA
```

## Lo stato che si verifica da solo (git)

Per il tipo `stato`, il Registro non si fida della prosa: a ogni apertura legge l'**ultimo commit**
di ciascun modulo (`git log` sul path del modulo) e aggiorna lo stato con data, hash e branch reali.
Se un commit vive su un branch diverso da `main`, lo segnala. È idempotente: se nulla è cambiato,
non scrive nulla (niente duplicati).

Se non usi git, lo `stato` lo tieni a mano: il meccanismo è lo stesso, manca solo l'aggancio a git.

## La Bussola: 8 sezioni che si riempiono da sole

Aprendo un modulo l'agente legge sempre le stesse 8 sezioni, in quest'ordine:

1. **META** — dove deve arrivare (obiettivo, identità)
2. **DOVE SIAMO ORA** — lo stato (da git)
3. **ULTIMO HANDOFF** — il testimone di fine sessione
4. **COME** — i prossimi passi (rotta, note)
5. **OPERATIVO** — come si lavora (regole, pattern, doc tecnici)
6. **BLOCCANTI** — cosa impedisce di procedere adesso
7. **BUG NOTI** — problemi catalogati aperti
8. **DECISIONI / VINCOLI** — scelte prese e paletti

Ogni **tipo** di fatto ha una sezione di casa (mappa fissa), quindi **nessun fatto è mai invisibile**.
In più, un fatto di qualsiasi tipo che si apre con il marcatore `BLOCCANTE:` finisce tra i bloccanti —
marcatore esplicito = zero falsi positivi ("X blocca Y" come racconto non ci finisce).

## Il semaforo di fiducia

Il sistema dice da solo quando si sta perdendo:

- 🟢 **VERDE** — il registro è allineato al codice: fidati.
- 🟡 **GIALLO** — qualche divergenza (registro indietro di N commit, o bloccanti vecchi): verifica.
- 🔴 **ROSSO** — divergenza forte o nessuno stato: rinfresca prima di fidarti.

Con git, misura **quanto la memoria diverge dal repo reale**. Senza git, guarda i bloccanti aperti.
È questo che mantiene il *patto di misura*: la fiducia è dichiarata, non assunta.

## L'handoff: il testimone tra sessioni

A fine sessione un agente salva un **report** (cosa ha fatto + dove stava andando) con `handoff`.
Diventa la sezione *ULTIMO HANDOFF* del briefing successivo: il prossimo agente eredita la
**direzione**, non solo lo stato. È la staffetta che permette a più agenti (o a te in giorni diversi)
di non ripartire mai da zero.

## Perché solo standard library

Niente `pip`, niente servizi, niente account, un solo file di dati. Tre conseguenze pratiche:
è **immune** ai problemi di rete/proxy/antivirus, è **ispezionabile** (è SQLite), ed è **tuo per sempre**
— se domani butti via il Registro, i tuoi fatti restano in un file che qualsiasi cosa sa leggere.
