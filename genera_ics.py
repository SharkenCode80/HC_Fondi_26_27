#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HC Fondi - Campionati 2026/2027 - calendari da abbonamento (.ics)
-----------------------------------------------------------------
Legge calendario.json (+ risultati.json, se c'e') e scrive, nella stessa
cartella:
    calendario.ics            tutte le partite e gli eventi
    calendario-<cat>.ics      un calendario per categoria
    calendari.json            elenco dei calendari (letto da abbonati.html)

Le gare interne (es. U18F contro U16F) finiscono sia nel calendario U18 F
sia in quello U16 F; in "tutte" compaiono una volta sola.

Ogni evento ha un UID stabile (categoria + squadre, non la data): se una
partita viene spostata, nel calendario di chi e' abbonato si sposta invece
di comparire due volte. Se il contenuto non cambia, i file restano identici.

Uso:  python3 genera_ics.py          (nessuna libreria esterna)
"""

import datetime, json, os, re, unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
SITE_URL = "https://sharkencode80.github.io/HC_Fondi_26_27/"
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


def slug(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def norm(s):
    return re.sub(r"\s+", " ", (s or "")).strip().upper()


def load(name, default=None):
    path = os.path.join(HERE, name)
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main():
    cal = load("calendario.json")
    ris = load("risultati.json", {}) or {}
    cats, venues = cal["categories"], cal["venues"]
    durate = (cal.get("mister") or {}).get("durate") or {}
    team = cal.get("fondiTeam", "HC Fondi")

    # anno di ogni partita: campo "year", altrimenti dalla data di inizio stagione
    y0, m0 = int(cal["start"][6:10]), int(cal["start"][3:5])
    def date_of(m):
        d, mo = int(m["date"][:2]), int(m["date"][3:5])
        return datetime.date(m.get("year") or (y0 if mo >= m0 else y0 + 1), mo, d)

    results = {}
    for r in ris.get("results", []):
        results[(r["date"][:5], r["cat"], norm(r["home"]), norm(r["away"]))] = r

    def result_for(m):
        r = results.get((m["date"][:5], m["cat"], norm(m["home"]), norm(m["away"])))
        if r:
            return r["hs"], r["as"], r.get("status", "")
        r = results.get((m["date"][:5], m["cat"], norm(m["away"]), norm(m["home"])))
        if r:
            return r["as"], r["hs"], r.get("status", "")
        return None

    # DTSTAMP fisso = ultimo aggiornamento dei dati: file identici se nulla cambia
    stamp_src = ris.get("updated") or cal["event"].get("updated") or "01/01/2026 00:00"
    cal_upd = cal["event"].get("updated") or stamp_src
    def parse_upd(s):
        try:
            return datetime.datetime.strptime(s, "%d/%m/%Y %H:%M")
        except (TypeError, ValueError):
            return datetime.datetime(2026, 1, 1)
    stamp = max(parse_upd(stamp_src), parse_upd(cal_upd)).strftime("%Y%m%dT%H%M00")

    # UID stabile: categoria + squadre (+ data per gli eventi senza squadre)
    seen, events = {}, []
    for m in cal["matches"]:
        d = date_of(m)
        base = f"{m['cat']}-{slug(m['home'])}-{slug(m['away'])}" if not m.get("event") \
            else f"{m['cat']}-{slug(m['home'])}-{d:%Y%m%d}"
        seen[base] = seen.get(base, 0) + 1
        if seen[base] > 1:
            base += f"-{seen[base]}"
        events.append((m, d, base))

    def vevent(m, d, uid, calkey):
        label = cats.get(m["cat"], m["cat"])
        lines = ["BEGIN:VEVENT", f"UID:{uid}-{calkey}@hcfondi2627", f"DTSTAMP:{stamp}Z"]
        if m.get("time"):
            h, mi = map(int, m["time"].split("."))
            start = datetime.datetime(d.year, d.month, d.day, h, mi)
            dur = durate.get(m["cat"]) or {}
            minutes = 2 * int(dur.get("tempo", 0)) + int(dur.get("pausa", 0)) or 60
            end = start + datetime.timedelta(minutes=minutes)
            lines += [f"DTSTART;TZID=Europe/Rome:{start:%Y%m%dT%H%M%S}",
                      f"DTEND;TZID=Europe/Rome:{end:%Y%m%dT%H%M%S}"]
        else:
            lines += [f"DTSTART;VALUE=DATE:{d:%Y%m%d}",
                      f"DTEND;VALUE=DATE:{d + datetime.timedelta(days=1):%Y%m%d}",
                      "TRANSP:TRANSPARENT"]
        if m.get("event"):
            summary = m["home"] if m["cat"] == "sel" else f"{label} · {m['home']}"
        else:
            summary = f"{label} · {m['home']} – {m['away']}"
        lines.append(f"SUMMARY:{esc(summary)}")
        venue = venues.get(m.get("venue", ""), m.get("venue", ""))
        if venue:
            lines.append(f"LOCATION:{esc(venue)}")
        desc = []
        if not m.get("event"):
            desc.append("In casa" if m["home"].startswith(team) else "In trasferta")
        r = None if m.get("event") else result_for(m)
        if r:
            desc.append(f"Risultato: {m['home']} {r[0]} – {r[1]} {m['away']}"
                        + (f" ({r[2]})" if r[2] else ""))
        desc.append(f"Calendario completo: {SITE_URL}")
        lines += [f"DESCRIPTION:{esc(chr(10).join(desc))}", f"URL:{SITE_URL}",
                  f"CATEGORIES:{esc(label)}", "END:VEVENT"]
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
    print("calendari.json: elenco per abbonati.html")


if __name__ == "__main__":
    main()
