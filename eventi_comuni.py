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


def data_partita(cal, m):
    """Data (datetime.date) di una voce: campo "year", altrimenti dall'inizio stagione."""
    d, mo = int(m["date"][:2]), int(m["date"][3:5])
    if m.get("year"):
        return datetime.date(m["year"], mo, d)
    y0, m0 = int(cal["start"][6:10]), int(cal["start"][3:5])
    return datetime.date(y0 if mo >= m0 else y0 + 1, mo, d)


def sigla(cal, nome):
    """Sigla di una squadra dalla tabella "sigle" di calendario.json (minuscola),
    oppure None se manca. Maiuscole e spazi nel nome non contano."""
    tab = {norm(k): v for k, v in (cal.get("sigle") or {}).items()}
    s = tab.get(norm(nome))
    return slug(s) if s else None


def squadre_senza_sigla(cal):
    """Nomi di squadre (partite, non eventi) che non hanno una sigla."""
    out = []
    for m in cal["matches"]:
        if m.get("event"):
            continue
        for n in (m["home"], m["away"]):
            if n and sigla(cal, n) is None and n not in out:
                out.append(n)
    return out


def id_base(cal, m, d):
    """Id "naturale" di una voce: data con anno, orario, categoria e sigle delle squadre.

    Es. 20261120-1530-u16f-fla-hcf. Senza orario: 20261213-u14-under-14.
    Per gli eventi e per le squadre senza sigla si usa il nome intero.
    """
    parti = [f"{d:%Y%m%d}"]
    if m.get("time"):
        parti.append(m["time"].replace(".", "").replace(":", "").zfill(4))
    parti.append(m["cat"])
    for n in (m.get("home"), m.get("away")):
        if n:
            parti.append((None if m.get("event") else sigla(cal, n)) or slug(n))
    return "-".join(p for p in parti if p)


def assegna_id(cal):
    """Aggiunge "id" (primo campo) alle voci di calendario.json che non ce l'hanno.

    Gli id gia' presenti non si toccano: i risultati li usano per trovare la partita.
    Se due voci avrebbero lo stesso id, dalla seconda si aggiunge -2, -3, ...
    Restituisce il numero di id aggiunti.
    """
    usati = {m["id"] for m in cal["matches"] if m.get("id")}
    nuovi, out = 0, []
    for m in cal["matches"]:
        if not m.get("id"):
            base = nuovo = id_base(cal, m, data_partita(cal, m))
            n = 2
            while nuovo in usati:
                nuovo, n = f"{base}-{n}", n + 1
            usati.add(nuovo)
            m = {"id": nuovo, **m}
            nuovi += 1
        out.append(m)
    cal["matches"] = out
    return nuovi


def eventi_con_uid(cal):
    """[(partita, data, base_uid)] nell'ordine di calendario.json.

    UID stabile: categoria + squadre (+ data per gli eventi senza squadre), cosi'
    una partita spostata si sposta invece di comparire due volte. Se due voci
    hanno la stessa base, dalla seconda si aggiunge -2, -3, ...
    """
    seen, events = {}, []
    for m in cal["matches"]:
        d = data_partita(cal, m)
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


# stati del risultato: "FINE" (o vuoto) = finale; gli altri indicano una partita in corso
# (DA_INIZIARE = nessun risultato: la partita viene trattata come se non ci fosse)
STATI = {"FINE": "FINE", "PARZIALE": "parziale", "1T": "parziale, I Tempo",
         "INTERVALLO": "parziale, Intervallo", "2T": "parziale, II Tempo"}
STATI_ALIAS = {"DA INIZIARE": "DA_INIZIARE", "I TEMPO": "1T", "PRIMO TEMPO": "1T", "1° TEMPO": "1T",
               "II TEMPO": "2T", "SECONDO TEMPO": "2T", "2° TEMPO": "2T"}


def codice_stato(stato):
    """Stato normalizzato: "da iniziare" -> "DA_INIZIARE", "I Tempo" -> "1T", ..."""
    s = " ".join(str(stato or "").upper().split())
    return STATI_ALIAS.get(s, s)


def etichetta_stato(stato):
    """Testo dello stato per la descrizione dell'evento (es. "1T" -> "parziale, I Tempo")."""
    s = codice_stato(stato)
    return STATI.get(s, str(stato or "").strip())


def id_sconosciuti(cal, ris):
    """Id usati in risultati.json che non corrispondono a nessuna voce di calendario.json
    (escluse le voci DA_INIZIARE, che non contengono risultati)."""
    ids = {m.get("id") for m in cal["matches"]}
    return [r["id"] for r in (ris or {}).get("results", [])
            if r.get("id") and r["id"] not in ids and codice_stato(r.get("status")) != "DA_INIZIARE"]


def cerca_risultato(ris):
    """Funzione partita -> (gol casa, gol ospite, stato) oppure None.

    Le voci di risultati.json si abbinano alla partita con "id" (formato attuale:
    gol e squadre nell'ordine di calendario.json) oppure, per le voci nel formato
    precedente, con data, categoria e squadre (girate in automatico se invertite).
    """
    per_id, results = {}, {}
    for r in (ris or {}).get("results", []):
        if codice_stato(r.get("status")) == "DA_INIZIARE":
            continue
        if r.get("id"):
            per_id[r["id"]] = r
        else:
            results[(r["date"][:5], r["cat"], norm(r["home"]), norm(r["away"]))] = r

    def result_for(m):
        r = per_id.get(m.get("id")) if m.get("id") else None
        if r:
            return r["hs"], r["as"], r.get("status", "")
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
                    + (f" ({etichetta_stato(r[2])})" if r[2] else ""))
    desc.append(f"Calendario completo: {SITE_URL}")

    return {"label": label, "summary": summary, "location": venue,
            "description": "\n".join(desc), "url": SITE_URL,
            "start": start, "end": end, "giornata": giornata}


# --------------------------------------------------------------------------
#  risultati.json: scrittura e conversione al formato con "id"
# --------------------------------------------------------------------------
def testo_risultati(ris):
    """Testo di risultati.json, leggibile a mano.

    Voci con "id": una riga  { "id": ..., "hs": .., "as": .., "status": .. }
    Voci nel formato precedente: due righe (data, categoria, squadre / punteggio).
    """
    def campi(d):
        return ", ".join(f"{json.dumps(k)}: {json.dumps(v, ensure_ascii=False)}" for k, v in d.items())

    righe = []
    for r in ris.get("results", []):
        if r.get("id"):
            righe.append(f"    {{ {campi(r)} }}")
            continue
        a = {k: r[k] for k in ("date", "cat", "home", "away") if k in r}
        b = {k: v for k, v in r.items() if k not in a}
        righe.append(f"    {{ {campi(a)},\n      {campi(b)} }}")
    testa = {k: v for k, v in ris.items() if k != "results"}
    testo = "{\n" + "".join(f"  {json.dumps(k)}: {json.dumps(v, ensure_ascii=False)},\n" for k, v in testa.items())
    testo += '  "results": [\n' + ",\n".join(righe) + ("\n" if righe else "") + "  ]\n}\n"
    json.loads(testo)                                         # controllo prima di scrivere
    return testo


def scrivi(nome, testo):
    """Scrive un file della cartella del progetto in modo sicuro (prima .tmp, poi rinomina)."""
    path = os.path.join(HERE, nome)
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        f.write(testo)
    os.replace(path + ".tmp", path)


def testo_calendario(cal):
    return json.dumps(cal, ensure_ascii=False, indent=2) + "\n"


def converti_risultati(cal, ris):
    """(ris convertito, non_trovate): le voci nel formato precedente diventano
    { "id", "hs", "as", "status" } con i gol nell'ordine di calendario.json.
    Le voci che non corrispondono a nessuna partita restano com'erano."""
    out, non_trovate = [], []
    for r in (ris or {}).get("results", []):
        if r.get("id"):
            out.append(r)
            continue
        trovata = None
        for m in cal["matches"]:
            if m.get("event") or m["date"][:5] != r["date"][:5] or m["cat"] != r["cat"]:
                continue
            if (norm(m["home"]), norm(m["away"])) == (norm(r["home"]), norm(r["away"])):
                trovata = (m, r["hs"], r["as"])
            elif (norm(m["home"]), norm(m["away"])) == (norm(r["away"]), norm(r["home"])):
                trovata = (m, r["as"], r["hs"])
            if trovata:
                break
        if not trovata or not trovata[0].get("id"):
            out.append(r)
            non_trovate.append(r)
            continue
        m, hs, as_ = trovata
        extra = {k: v for k, v in r.items() if k not in ("date", "cat", "home", "away", "hs", "as", "status")}
        out.append({"id": m["id"], "hs": hs, "as": as_, "status": r.get("status", ""), **extra})
    return dict(ris or {}, results=out), non_trovate


def prepara_risultati(cal, ris):
    """(ris, aggiunte, tolte): risultati.json con una voce per ogni partita.

    - Le partite (non gli eventi) senza voce ricevono
      { "id", "hs": 0, "as": 0, "status": "DA_INIZIARE" }: basta poi scrivere
      gol e stato.
    - Le voci con id sono messe nell'ordine di calendario.json; quelle nel formato
      precedente o con un id che non esiste restano in fondo, com'erano.
    - Le voci DA_INIZIARE con un id che non esiste piu' (partita spostata o tolta)
      vengono tolte: non contengono risultati.
    """
    per_id, altre, tolte = {}, [], 0
    ids = {m.get("id") for m in cal["matches"]}
    for r in (ris or {}).get("results", []):
        if r.get("id") and r["id"] in ids and r["id"] not in per_id:
            per_id[r["id"]] = r
        elif r.get("id") and r["id"] not in ids and codice_stato(r.get("status")) == "DA_INIZIARE":
            tolte += 1
        else:
            altre.append(r)
    out, aggiunte = [], 0
    for m in cal["matches"]:
        if m.get("event") or not m.get("id"):
            continue
        if m["id"] in per_id:
            out.append(per_id[m["id"]])
        else:
            out.append({"id": m["id"], "hs": 0, "as": 0, "status": "DA_INIZIARE"})
            aggiunte += 1
    return dict(ris or {}, results=out + altre), aggiunte, tolte
