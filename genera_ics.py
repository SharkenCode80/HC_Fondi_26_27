#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HC Fondi - Campionati 2026/2027 - calendari da sincronizzare (.ics)
-----------------------------------------------------------------
Legge calendario.json (+ risultati.json, se c'e') e scrive, nella stessa
cartella:
    calendario.ics            tutte le partite e gli eventi
    calendario-<cat>.ics      un calendario per categoria
    calendari.json            elenco dei calendari (letto da sincronizza.html)

Le gare interne (es. U18F contro U16F) finiscono sia nel calendario U18 F
sia in quello U16 F; in "tutte" compaiono una volta sola.

Ogni evento ha un UID stabile (categoria + squadre, non la data): se una
partita viene spostata, nel calendario di chi lo segue si sposta invece
di comparire due volte. Se il contenuto non cambia, i file restano identici.

Uso:  python3 genera_ics.py          (nessuna libreria esterna)
"""

import datetime, json, os, shlex

from eventi_comuni import HERE, SITE_URL, load, eventi_con_uid, uid, cerca_risultato, campi_evento

CAL_PREFIX = "HC Fondi"
REFRESH = "PT6H"                      # ogni quanto suggeriamo alle app di riscaricare

# calendari per categoria: codice -> categorie incluse
PER_CATEGORIA = {
    "serieb": ["serieb"],
    "u18f":   ["u18f", "interna"],
    "u16f":   ["u16f", "interna"],
    "u16m":   ["u16m"],
    "u14":    ["u14"],
    "sel":    ["sel"],
}
NOTE = {"u18f": "con le gare interne", "u16f": "con le gare interne"}

VTIMEZONE = """BEGIN:VTIMEZONE
TZID:Europe/Rome
X-LIC-LOCATION:Europe/Rome
BEGIN:DAYLIGHT
TZOFFSETFROM:+0100
TZOFFSETTO:+0200
TZNAME:CEST
DTSTART:19700329T020000
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU
END:DAYLIGHT
BEGIN:STANDARD
TZOFFSETFROM:+0200
TZOFFSETTO:+0100
TZNAME:CET
DTSTART:19701025T030000
RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU
END:STANDARD
END:VTIMEZONE""".split("\n")


def esc(s):
    """Testo ICS: \\ ; , e a capo vanno protetti."""
    return (str(s).replace("\\", "\\\\").replace(";", "\\;")
            .replace(",", "\\,").replace("\n", "\\n"))


def fold(line):
    """Righe ICS al massimo 75 byte: le successive iniziano con uno spazio."""
    out, cur = [], b""
    for ch in line:
        b = ch.encode("utf-8")
        if len(cur) + len(b) > (75 if not out else 74):
            out.append(cur.decode("utf-8"))
            cur = b""
        cur += b
    out.append(cur.decode("utf-8"))
    return "\r\n ".join(out)


def main():
    cal = load("calendario.json")
    ris = load("risultati.json", {}) or {}
    cats = cal["categories"]
    result_for = cerca_risultato(ris)

    # DTSTAMP fisso = ultimo aggiornamento dei dati: file identici se nulla cambia
    stamp_src = ris.get("updated") or cal["event"].get("updated") or "01/01/2026 00:00"
    cal_upd = cal["event"].get("updated") or stamp_src
    def parse_upd(s):
        try:
            return datetime.datetime.strptime(s, "%d/%m/%Y %H:%M")
        except (TypeError, ValueError):
            return datetime.datetime(2026, 1, 1)
    stamp = max(parse_upd(stamp_src), parse_upd(cal_upd)).strftime("%Y%m%dT%H%M00")

    # UID stabile (vedi eventi_comuni.eventi_con_uid)
    events = eventi_con_uid(cal)

    def vevent(m, d, base, calkey):
        e = campi_evento(cal, m, d, result_for)
        lines = ["BEGIN:VEVENT", f"UID:{uid(base, calkey)}", f"DTSTAMP:{stamp}Z"]
        if not e["giornata"]:
            lines += [f"DTSTART;TZID=Europe/Rome:{e['start']:%Y%m%dT%H%M%S}",
                      f"DTEND;TZID=Europe/Rome:{e['end']:%Y%m%dT%H%M%S}"]
        else:
            lines += [f"DTSTART;VALUE=DATE:{e['start']:%Y%m%d}",
                      f"DTEND;VALUE=DATE:{e['end']:%Y%m%d}",
                      "TRANSP:TRANSPARENT"]
        lines.append(f"SUMMARY:{esc(e['summary'])}")
        if e["location"]:
            lines.append(f"LOCATION:{esc(e['location'])}")
        lines += [f"DESCRIPTION:{esc(e['description'])}", f"URL:{e['url']}",
                  f"CATEGORIES:{esc(e['label'])}", "END:VEVENT"]
        return lines

    def write_ics(fname, calkey, title, include):
        sel = [(m, d, b) for (m, d, b) in events if m["cat"] in include]
        lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//HC Fondi//Campionati 26-27//IT",
                 "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
                 f"X-WR-CALNAME:{esc(title)}",
                 f"X-WR-CALDESC:{esc('Partite HC Fondi stagione 2026/2027 - ' + SITE_URL)}",
                 "X-WR-TIMEZONE:Europe/Rome",
                 f"REFRESH-INTERVAL;VALUE=DURATION:{REFRESH}", f"X-PUBLISHED-TTL:{REFRESH}"]
        lines += VTIMEZONE
        for m, d, b in sel:
            lines += vevent(m, d, b, calkey)
        lines.append("END:VCALENDAR")
        with open(os.path.join(HERE, fname), "w", encoding="utf-8", newline="") as f:
            f.write("\r\n".join(fold(x) for x in lines) + "\r\n")
        return len(sel)

    manifest = []
    n = write_ics("calendario.ics", "tutte", f"{CAL_PREFIX} · Tutte le partite", set(cats))
    manifest.append({"key": "tutte", "label": "Tutte le partite", "note": "tutte le categorie ed eventi",
                     "file": "calendario.ics", "count": n, "all": True})
    print(f"calendario.ics: {n} eventi")
    for key, include in PER_CATEGORIA.items():
        if key not in cats:
            continue
        fname = f"calendario-{key}.ics"
        n = write_ics(fname, key, f"{CAL_PREFIX} · {cats[key]}", set(include))
        if n:
            manifest.append({"key": key, "label": cats[key], "note": NOTE.get(key, ""),
                             "file": fname, "count": n})
            print(f"{fname}: {n} eventi")

    with open(os.path.join(HERE, "calendari.json"), "w", encoding="utf-8") as f:
        json.dump({"site": SITE_URL, "calendars": manifest}, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print("calendari.json: elenco per sincronizza.html")

    # il calendario Google condiviso NON si aggiorna da qui: si lancia a parte
    script = os.path.relpath(os.path.join(HERE, "sincronizza_google.py"))
    if script.startswith(".."):
        script = os.path.join(HERE, "sincronizza_google.py")
    cmd = f"python3 {shlex.quote(script)}"
    print()
    print("Calendario Google condiviso (non aggiornato in automatico). Per sincronizzarlo:")
    print(f"  {cmd} --dry-run    # mostra cosa cambierebbe, senza toccare nulla")
    print(f"  {cmd}              # applica (chiede conferma)")
    print("Prima configurazione: README, sezione \"Calendario Google condiviso\".")


if __name__ == "__main__":
    main()
