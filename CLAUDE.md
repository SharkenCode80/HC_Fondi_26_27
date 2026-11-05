# CLAUDE.md — HC Fondi Campionati 26-27

Sito statico (GitHub Pages da `main`) con il calendario delle squadre HC Fondi, stagione
2026/2027: <https://sharkencode80.github.io/HC_Fondi_26_27/>. Documentazione completa
nel `README.md`; appunti di lavoro locali in `STATO_LAVORI.md` (non nel repository).
Testi, commenti e messaggi di commit in **italiano**.

## Struttura in breve
- `index.html` (tabellone) e `mobile.html` (agenda): `js/vista.js` sceglie in base allo
  schermo. Pulsante **📅 Sincronizza** + guida **?** (`js/sincronizza-aiuto.js`) →
  `sincronizza.html`. `index-old.html`/`mobile-old.html`: versioni precedenti (`noindex`).
  `calendario-google.html`: nascosta (link commentati).
- Dati: `calendario.json` (dall'Excel con `converti_excel.py`) e `risultati.json`.
- `genera_ics.py` → `calendario*.ics` + `calendari.json` (UID da `eventi_comuni.py`).
- `sincronizza_google.py`: sincronizzazione con un calendario Google proprio (oggi non
  usata: i calendari Google pubblici sono "Da URL", ID in `js/calendari-google.js`).
- `verifica_figh.py`: confronto con il sito FIGH (Area 7) e caricamento dei risultati.
- Stile: `css/base.css` + un tema `css/tema-*.css` (attivo: `tema-rossoblu`), `css/mobile.css`,
  `css/sincronizza.css`. Nessuno stile dentro le pagine HTML.

## Comandi
```bash
python3 converti_excel.py          # Excel -> calendario.json (+ genera_ics.py)
python3 genera_ics.py              # dopo OGNI modifica a calendario.json o risultati.json
python3 verifica_figh.py           # menu: scarica / confronta online / offline / carica risultati
python3 -m unittest test_sincronizza test_verifica_figh
python3 -m http.server 8000        # prova in locale (http://localhost:8000)
```
Solo libreria standard di Python (3.9), tranne `sincronizza_google.py` (`requirements.txt`).

## Regole
- **Mai committare**: l'Excel `Calendario_…xlsx`, `STATO_LAVORI.md`, `TestCalendario1.jpeg`,
  `mockup/`, i file `*-FIGH.json`, chiavi/token Google. Non stampare mai segreti.
- Mai pubblicare iframe personalizzati o ID di calendari Google privati: solo gli ID
  `…@import.calendar.google.com` pubblici già in `js/calendari-google.js`.
- Commit, tag e push solo quando l'utente lo chiede. Tag annotati `vX.Y.Z`; per spostare
  un tag: `git tag -d` + `git push origin --delete` + nuovo tag + push, poi verificare con
  `git ls-remote --tags origin`. L'utente modifica a volte file direttamente su GitHub:
  fare `git pull --rebase` prima di lavorare.
- Non modificare `calendario.json`/`risultati.json` senza richiesta esplicita: le
  differenze con la FIGH vanno segnalate, non corrette d'ufficio.
- Pagine: niente parole come "abbonati"/"iscriviti" (sembrano a pagamento): si usa
  "Sincronizza". Verificare le modifiche grafiche anche a 360/390/430 px (versione cellulare).
- Dopo modifiche a `calendario.json`/`risultati.json`: rigenerare i `.ics` e pubblicarli insieme.
