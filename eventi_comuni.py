# -*- coding: utf-8 -*-
"""
HC Fondi - Campionati 2026/2027 - eventi in comune tra i calendari
------------------------------------------------------------------
Funzioni usate sia da genera_ics.py (file .ics) sia da sincronizza_google.py
(calendario Google condiviso), cosi' gli eventi sono gli stessi nei due casi:
stessi UID, stessi titoli, orari, luoghi e descrizioni.

Nessuna libreria esterna.
"""

import datetime, json, os, re, unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
SITE_URL = "https://sharkencode80.github.io/HC_Fondi_26_27/"
UID_DOMINIO = "hcfondi2627"


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


def eventi_con_uid(cal):
    """[(partita, data, base_uid)] nell'ordine di calendario.json.

    UID stabile: categoria + squadre (+ data per gli eventi senza squadre), cosi'
    una partita spostata si sposta invece di comparire due volte. Se due voci
    hanno la stessa base, dalla seconda si aggiunge -2, -3, ...
    """
    # anno di ogni partita: campo "year", altrimenti dalla data di inizio stagione
    y0, m0 = int(cal["start"][6:10]), int(cal["start"][3:5])
    def date_of(m):
        d, mo = int(m["date"][:2]), int(m["date"][3:5])
        return datetime.date(m.get("year") or (y0 if mo >= m0 else y0 + 1), mo, d)

    seen, events = {}, []
    for m in cal["matches"]:
        d = date_of(m)
        base = f"{m['cat']}-{slug(m['home'])}-{slug(m['away'])}" if not m.get("event") \
            else f"{m['cat']}-{slug(m['home'])}-{d:%Y%m%d}"
        seen[base] = seen.get(base, 0) + 1
        if seen[base] > 1:
            base += f"-{seen[base]}"
        events.append((m, d, base))
    return events


def uid(base, calkey):
    """UID completo dell'evento nel calendario `calkey` (tutte, u16f, ...)."""
    return f"{base}-{calkey}@{UID_DOMINIO}"


def cerca_risultato(ris):
    """Funzione partita -> (gol casa, gol ospite, stato) oppure None."""
    results = {}
    for r in (ris or {}).get("results", []):
        results[(r["date"][:5], r["cat"], norm(r["home"]), norm(r["away"]))] = r

    def result_for(m):
        r = results.get((m["date"][:5], m["cat"], norm(m["home"]), norm(m["away"])))
        if r:
            return r["hs"], r["as"], r.get("status", "")
        r = results.get((m["date"][:5], m["cat"], norm(m["away"]), norm(m["home"])))
        if r:
            return r["as"], r["hs"], r.get("status", "")
        return None
    return result_for


def campi_evento(cal, m, d, result_for):
    """Contenuto di un evento, indipendente dal formato.

    start/end: datetime locali (Europe/Rome) per le partite con orario;
    date per gli eventi di un'intera giornata (end = giorno dopo, escluso).
    """
    cats, venues = cal["categories"], cal["venues"]
    durate = (cal.get("mister") or {}).get("durate") or {}
    team = cal.get("fondiTeam", "HC Fondi")
    label = cats.get(m["cat"], m["cat"])

    if m.get("time"):
        h, mi = map(int, m["time"].split("."))
        start = datetime.datetime(d.year, d.month, d.day, h, mi)
        dur = durate.get(m["cat"]) or {}
        minutes = 2 * int(dur.get("tempo", 0)) + int(dur.get("pausa", 0)) or 60
        end = start + datetime.timedelta(minutes=minutes)
        giornata = False
    else:
        start, end, giornata = d, d + datetime.timedelta(days=1), True

    if m.get("event"):
        summary = m["home"] if m["cat"] == "sel" else f"{label} · {m['home']}"
    else:
        summary = f"{label} · {m['home']} – {m['away']}"
    venue = venues.get(m.get("venue", ""), m.get("venue", ""))
    desc = []
    if not m.get("event"):
        desc.append("In casa" if m["home"].startswith(team) else "In trasferta")
    r = None if m.get("event") else result_for(m)
    if r:
        desc.append(f"Risultato: {m['home']} {r[0]} – {r[1]} {m['away']}"
                    + (f" ({r[2]})" if r[2] else ""))
    desc.append(f"Calendario completo: {SITE_URL}")

    return {"label": label, "summary": summary, "location": venue,
            "description": "\n".join(desc), "url": SITE_URL,
            "start": start, "end": end, "giornata": giornata}
