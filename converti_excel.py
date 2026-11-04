#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HC Fondi - Campionati 2026/2027 - convertitore Excel -> calendario.json
-----------------------------------------------------------------------
Legge il foglio "Calendario HC Fondi" (8 blocchi mese da 3 colonne:
GIORNO | G | PARTITA HC FONDI) e scrive calendario.json nello stesso
formato usato dal Festival della Pallamano (event, categories, venues,
days, dow, mister, matches).

Formato atteso di ogni cella partita (3 righe):
    "SERIE B – 18:00 – CASA"
    "vs BENEVENTO 23"
    "Fondi Palasport - Fondi"
Le celle senza orario (es. "Selezione dei Talenti", "Finali U16",
"UNDER 14 - salerno") diventano eventi senza orario (time = "").

Uso:  python3 converti_excel.py [file.xlsx]      (richiede: pip install openpyxl)
"""

import datetime, glob, json, os, re, sys, unicodedata
import openpyxl

HERE = os.path.dirname(os.path.abspath(__file__))
TEAM = "HC Fondi"

MESI = {"GENNAIO": 1, "FEBBRAIO": 2, "MARZO": 3, "APRILE": 4, "MAGGIO": 5, "GIUGNO": 6,
        "LUGLIO": 7, "AGOSTO": 8, "SETTEMBRE": 9, "OTTOBRE": 10, "NOVEMBRE": 11, "DICEMBRE": 12}
DOW = ["LUN", "MAR", "MER", "GIO", "VEN", "SAB", "DOM"]
DOW1 = ["L", "M", "M", "G", "V", "S", "D"]          # lettera usata nella colonna "G"

# categorie: codice -> etichetta (l'ordine e' quello dei filtri nella pagina)
CATEGORIES = {"serieb": "Serie B", "u18f": "U18 F", "u16f": "U16 F", "u16m": "U16 M",
              "u14": "Under 14", "interna": "Gara interna", "sel": "Selezione Talenti"}
# durate (minuti) per la modalita' Mister: totale = 2*tempo + pausa
DURATE = {"serieb": {"tempo": 30, "pausa": 10}, "u18f": {"tempo": 30, "pausa": 10},
          "u16f": {"tempo": 25, "pausa": 10}, "u16m": {"tempo": 25, "pausa": 10},
          "u14": {"tempo": 20, "pausa": 10}, "interna": {"tempo": 30, "pausa": 10},
          "sel": {"tempo": 0, "pausa": 0}}

# impianti scritti in modi diversi nell'Excel ma che sono lo stesso posto:
# nome come compare nel file -> nome da usare
VENUE_ALIAS = {
    "Palasport - Gaeta": "Impianto Sportivo Polivalente Palasport - Gaeta",
}

HEAD_RE = re.compile(r"^(?P<cat>.+?)\s*[–-]\s*(?P<h>\d{1,2})[:.](?P<m>\d{2})\s*[–-]\s*(?P<ha>CASA|TRASFERTA)\s*$", re.I)


def cat_code(label):
    """Codice categoria dal testo della cella (prima riga)."""
    s = label.upper().replace(" ", "")
    if "/" in s:                       # "U18F/U16F ... vs HC Fondi U16F"
        return "interna"
    if s.startswith("SERIEB"):
        return "serieb"
    if "SELEZIONE" in s:
        return "sel"
    if "U18" in s:
        return "u18f"
    if "U16" in s:
        return "u16f" if s.endswith("F") or "U16F" in s or s == "FINALIU16" else "u16m"
    if "UNDER14" in s or "U14" in s:
        return "u14"
    return None


def clean(s):
    s = (s or "").replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", s).strip()


def slug(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def parse_cell(text):
    """Testo della cella -> dict partita/evento (senza data)."""
    lines = [clean(x) for x in str(text).split("\n") if clean(x)]
    m = HEAD_RE.match(lines[0])
    if m:
        cat = cat_code(m.group("cat"))
        opp = re.sub(r"^vs\.?\s*", "", lines[1], flags=re.I) if len(lines) > 1 else ""
        venue = lines[2] if len(lines) > 2 else ""
        casa = m.group("ha").upper() == "CASA"
        if cat == "interna":
            # "U18F/U16F ... vs HC Fondi U16F": la nostra squadra e' quella
            # dell'intestazione che NON compare nell'avversario -> "HC Fondi U18F"
            labels = [x.strip() for x in m.group("cat").split("/")]
            mine = [x for x in labels if x.upper().replace(" ", "") not in opp.upper().replace(" ", "")]
            team = f"{TEAM} {mine[0]}" if len(mine) == 1 else TEAM
            return {"time": f"{int(m.group('h')):02d}.{m.group('m')}", "cat": cat,
                    "gir": "Casa" if casa else "Trasferta",
                    "home": team if casa else opp, "away": opp if casa else team,
                    "venue_name": venue}
        return {"time": f"{int(m.group('h')):02d}.{m.group('m')}", "cat": cat,
                "gir": "Casa" if casa else "Trasferta",
                "home": TEAM if casa else opp, "away": opp if casa else TEAM,
                "venue_name": venue}
    # evento senza orario
    first = lines[0]
    return {"time": "", "cat": cat_code(first) or "sel", "gir": "Evento", "home": first,
            "away": "", "venue_name": "", "event": True}


def convert(xlsx):
    ws = openpyxl.load_workbook(xlsx, data_only=True).active

    # cella -> cella in alto a sinistra del suo merge (per i giorni su 2 righe)
    top = {}
    for rng in ws.merged_cells.ranges:
        for r in range(rng.min_row, rng.max_row + 1):
            for c in range(rng.min_col, rng.max_col + 1):
                top[(r, c)] = (rng.min_row, rng.min_col)
    val = lambda r, c: ws.cell(*top.get((r, c), (r, c))).value

    # blocchi mese: riga con "NOVEMBRE 2026", "DICEMBRE 2026", ...
    hdr_row = next(r for r in range(1, 15)
                   if any(str(ws.cell(r, c).value or "").split(" ")[0].upper() in MESI
                          for c in range(1, ws.max_column + 1)))
    blocks = []
    for c in range(1, ws.max_column + 1):
        v = str(ws.cell(hdr_row, c).value or "").strip().upper()
        mm = re.match(r"([A-Z]+)\s+(\d{4})", v)
        if mm and mm.group(1) in MESI:
            blocks.append((c, MESI[mm.group(1)], int(mm.group(2))))

    matches, warnings = [], []
    for col, month, year in blocks:
        for r in range(hdr_row + 2, ws.max_row + 1):
            day, g, text = val(r, col), val(r, col + 1), ws.cell(r, col + 2).value
            if not isinstance(day, (int, float)) or not text or not str(text).strip():
                continue
            d = datetime.date(year, month, int(day))
            if g and DOW1[d.weekday()] != str(g).strip().upper():
                warnings.append(f"{d:%d/%m/%Y}: giorno '{g}' nel file, ma e' {DOW[d.weekday()]}")
            rec = parse_cell(text)
            if not rec["cat"]:
                warnings.append(f"{d:%d/%m/%Y}: categoria non riconosciuta in {text!r}")
                continue
            rec["date"] = f"{d:%d/%m}"
            rec["_d"] = d
            matches.append(rec)

    matches.sort(key=lambda m: (m["_d"], m["time"] or "00.00", m["cat"]))

    venues, venue_code = {}, {}
    for m in matches:
        name = m.pop("venue_name")
        name = VENUE_ALIAS.get(name, name)
        if not name:
            m["venue"] = ""
            continue
        code = venue_code.get(name.lower())
        if not code:                       # codice completo e univoco per ogni impianto
            code, n = slug(name), 2
            while code in venues:
                code, n = f"{slug(name)}-{n}", n + 1
            venue_code[name.lower()] = code
        venues[code] = name
        m["venue"] = code

    dates = sorted({m["_d"] for m in matches})
    days = [f"{d:%d/%m}" for d in dates]
    out_matches = []
    for m in matches:
        d = m.pop("_d")
        out_matches.append({"date": m["date"], "time": m["time"], "cat": m["cat"], "gir": m["gir"],
                            "home": m["home"], "away": m["away"], "venue": m["venue"],
                            **({"event": True} if m.get("event") else {}),
                            "year": d.year})

    start, end = dates[0], dates[-1]
    cal = {
        "event": {
            "title": "HC Fondi Campionati 26-27",
            "eyebrow": "HC Fondi · Stagione 2026/2027",
            "subtitle": f"{start:%d/%m/%Y} – {end:%d/%m/%Y} · Serie B · U18 F · U16 F · U16 M · Under 14",
            "source": os.path.basename(xlsx),
            "updated": datetime.datetime.now().strftime("%d/%m/%Y %H:%M"),
        },
        "fondiTeam": TEAM,
        "year": start.year,
        "start": f"{start:%d/%m/%Y}",
        "end": f"{end:%d/%m/%Y}",
        "days": days,
        "dow": {f"{d:%d/%m}": DOW[d.weekday()] for d in dates},
        "categories": CATEGORIES,
        "venues": venues,
        "mister": {"buffer": 30, "durate": DURATE},
        "matches": out_matches,
    }
    return cal, warnings


def main():
    xlsx = sys.argv[1] if len(sys.argv) > 1 else sorted(
        f for f in glob.glob(os.path.join(HERE, "*.xlsx")) if not os.path.basename(f).startswith("~$"))[-1]
    cal, warnings = convert(xlsx)
    path = os.path.join(HERE, "calendario.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cal, f, ensure_ascii=False, indent=2)
        f.write("\n")
    per_cat = {}
    for m in cal["matches"]:
        per_cat[m["cat"]] = per_cat.get(m["cat"], 0) + 1
    print(f"Letto: {os.path.basename(xlsx)}")
    print(f"Scritto: {path} - {len(cal['matches'])} voci in {len(cal['days'])} giornate | {per_cat}")
    for w in warnings:
        print("  [attenzione]", w)

    # rigenera anche i calendari da sincronizzare (.ics) dal nuovo calendario.json
    import genera_ics
    print("Calendari .ics:")
    genera_ics.main()


if __name__ == "__main__":
    main()
