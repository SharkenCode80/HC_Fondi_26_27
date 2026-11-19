# -*- coding: utf-8 -*-
"""
HC Fondi - Campionati 2026/2027 - versione dei file CSS e JavaScript
--------------------------------------------------------------------
Le pagine collegano css/ e js/ con "?v=X.Y.Z" (es. js/dettagli.js?v=2.4.2).
GitHub Pages fa tenere i file in cache per 10 minuti: cambiando il numero
a ogni pubblicazione, il browser scarica insieme la pagina nuova e i file
nuovi (senza, un telefono puo' usare la pagina nuova con un .js vecchio).

Uso:  python3 aggiorna_versione.py            mostra la versione attuale
      python3 aggiorna_versione.py 2.4.3      la imposta in pagine e temi
Da lanciare prima del commit quando si modifica qualcosa in css/ o js/
(di solito con lo stesso numero del tag). Nessuna libreria esterna.
"""

import glob, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
PAGINE = ["index.html", "mobile.html", "sincronizza.html", "calendario-google.html"]
# riferimenti locali: href/src a css/... o js/... nelle pagine, @import di base.css nei temi
RIF_PAGINE = re.compile(r'((?:href|src)="(?:css|js)/[^"?]+\.(?:css|js))(?:\?v=([^"]*))?"')
RIF_TEMI = re.compile(r'(@import url\("base\.css)(?:\?v=([^"]*))?("\);)')


def file_da_controllare():
    temi = sorted(glob.glob(os.path.join(HERE, "css", "tema-*.css")))
    return [(os.path.join(HERE, p), RIF_PAGINE) for p in PAGINE if os.path.exists(os.path.join(HERE, p))] + \
           [(p, RIF_TEMI) for p in temi]


def versioni():
    """{file: [versioni trovate]} (None = riferimento senza ?v=)."""
    out = {}
    for path, rx in file_da_controllare():
        with open(path, encoding="utf-8") as f:
            out[os.path.relpath(path, HERE)] = [m.group(2) for m in rx.finditer(f.read())]
    return out


def imposta(v):
    for path, rx in file_da_controllare():
        with open(path, encoding="utf-8") as f:
            testo = f.read()
        if rx is RIF_PAGINE:
            nuovo = rx.sub(lambda m: f'{m.group(1)}?v={v}"', testo)
        else:
            nuovo = rx.sub(lambda m: f'{m.group(1)}?v={v}{m.group(3)}', testo)
        if nuovo != testo:
            with open(path, "w", encoding="utf-8") as f:
                f.write(nuovo)


def main(argv):
    if argv:
        if not re.fullmatch(r"\d+\.\d+\.\d+", argv[0]):
            print("Versione non valida: usa X.Y.Z, es. 2.4.3")
            return 2
        imposta(argv[0])
    trovate = {v for vs in versioni().values() for v in vs}
    for nome, vs in versioni().items():
        print(f"{nome:<28} {', '.join(sorted({str(v) for v in vs})) or '-'}")
    if len(trovate) == 1 and None not in trovate:
        print(f"Versione: {trovate.pop()}")
        return 0
    print("ATTENZIONE: versioni diverse o mancanti")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
