#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HC Fondi - Campionati 2026/2027 - controllo con il sito FIGH
-----------------------------------------------------------
Confronta calendario.json e risultati.json con le partite pubblicate dalla
FIGH (campionati territoriali, Area 7) e, solo se lo confermi, carica in
risultati.json i risultati presenti sul sito.

All'avvio mostra un menu:
    1  Scarica dati da FIGH            -> calendario-FIGH.json, risultati-FIGH.json
    2  Confronta con dati FIGH online   (non modifica nulla)
    3  Confronta con dati FIGH offline  (dai file scaricati, non modifica nulla)
    4  Carica risultati                 (dal sito o da risultati-FIGH.json;
                                         mostra cosa cambia e chiede conferma)
Le stesse azioni si lanciano anche direttamente:
    python3 verifica_figh.py scarica | online | offline | carica
(per "online"/"offline" il codice di uscita è 0 se tutto coincide, 1 se ci
sono differenze, 2 se i dati FIGH non si possono leggere).

Dove sono i dati sul sito: ogni pagina di girone contiene tutte le partite
in un blocco JSON  `const calendario = {...}`  (giornate -> partite, con
data, ora, squadre, impianto, giocata/punteggio). HC Fondi si riconosce
dal codice società FIGH "0031", non dal nome (che cambia tra i gironi).
U14, Selezione Talenti e finali non sono sul sito FIGH Area 7 e non
vengono controllati.
"""

import datetime, json, os, re, sys, urllib.request

from eventi_comuni import HERE, load, norm

BASE = "https://www.federhandball.it/campionati-territoriali/area-7/girone/"
# pagina del girone -> categoria del nostro calendario (None = dal nome squadra)
GIRONI = {
    "serie-b-maschile-area-7-girone-unico": "serieb",
    "under-16-maschile-area-7": "u16m",
    "under-18-16-femminile-area-7-girone-unic": None,
}
COD_FONDI = "0031"
CATEGORIE = {"serieb", "u16m", "u16f", "u18f", "interna"}   # quelle presenti sul sito
FILE_CAL_FIGH = "calendario-FIGH.json"
FILE_RIS_FIGH = "risultati-FIGH.json"


class ErroreFIGH(Exception):
    """Dati FIGH non disponibili (sito irraggiungibile, pagina cambiata, file mancante)."""


# --------------------------------------------------------------------------
#  Lettura del sito
# --------------------------------------------------------------------------
def scarica(slug):
    req = urllib.request.Request(BASE + slug, headers={"User-Agent": "Mozilla/5.0 (verifica_figh.py)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def estrai_calendario(html):
    i = html.find("const calendario = ")
    if i < 0:
        raise ValueError("blocco 'const calendario' non trovato: la pagina è cambiata?")
    return json.JSONDecoder().raw_decode(html, i + len("const calendario = "))[0]


def squadra_fondi(team):
    return team.get("cod_aff_societa") == COD_FONDI


def categoria_fondi(nome):
    """'HC BANCAPOPOLARE DI FONDI U16F' -> 'u16f'."""
    m = re.search(r"U1[68]F\s*$", norm(nome))
    return m.group(0).strip().lower() if m else None


def partite_figh(cal_figh, cat_girone):
    out = []
    for giornata in cal_figh.get("giornate", {}).values():
        for x in giornata:
            t1, t2 = x["team1"], x["team2"]
            f1, f2 = squadra_fondi(t1), squadra_fondi(t2)
            if not (f1 or f2):
                continue
            if f1 and f2:
                cat = "interna"
            elif cat_girone:
                cat = cat_girone
            else:
                cat = categoria_fondi((t1 if f1 else t2)["title"])
            out.append({
                "id": str(x.get("id")), "girone": norm(cal_figh.get("title")),
                "data": x["date"], "ora": x["time"], "cat": cat, "giornata": x["day"],
                "casa": norm(t1["title"]), "ospite": norm(t2["title"]),
                "fondi_in_casa": f1, "impianto": norm(x["deno_campo"]), "localita": norm(x["localita"]),
                "giocata": bool(x.get("played")),
                "punti": [x.get("team1-setwin"), x.get("team2-setwin")],
                "ufficiale": str(x.get("ris_ufficiale")) == "1",
            })
    return out


def leggi_online(stampa=print):
    figh = []
    for slug, cat in GIRONI.items():
        try:
            c = estrai_calendario(scarica(slug))
        except Exception as e:
            raise ErroreFIGH(f"impossibile leggere il girone {slug}: {e}")
        trovate = partite_figh(c, cat)
        stampa(f"FIGH  {c.get('title', slug).strip():<45} {len(trovate):>3} partite HC Fondi")
        figh += trovate
    return ordina(figh)


def ordina(figh):
    return sorted(figh, key=lambda f: (f["data"][6:], f["data"][3:5], f["data"][:2], f["ora"]))


# --------------------------------------------------------------------------
#  File FIGH scaricati (calendario-FIGH.json + risultati-FIGH.json)
# --------------------------------------------------------------------------
RISULTATO = ("id", "data", "cat", "casa", "ospite", "punti", "ufficiale")


def salva_json(nome, dati):
    path = os.path.join(HERE, nome)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(dati, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def salva_figh(figh):
    adesso = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
    testa = {"scaricato": adesso, "fonte": BASE, "gironi": list(GIRONI)}
    partite = [{k: v for k, v in f.items() if k not in ("giocata", "punti", "ufficiale")} for f in figh]
    giocate = [{k: f[k] for k in RISULTATO} for f in figh if f["giocata"]]
    salva_json(FILE_CAL_FIGH, dict(testa, partite=partite))
    salva_json(FILE_RIS_FIGH, dict(testa, risultati=giocate))
    return len(partite), len(giocate)


def leggi_offline(stampa=print):
    cal_f, ris_f = load(FILE_CAL_FIGH), load(FILE_RIS_FIGH)
    if not cal_f:
        raise ErroreFIGH(f"{FILE_CAL_FIGH} non trovato: prima scarica i dati da FIGH (opzione 1).")
    risultati = {r["id"]: r for r in (ris_f or {}).get("risultati", [])}
    figh = []
    for p in cal_f.get("partite", []):
        r = risultati.get(p["id"])
        figh.append(dict(p, giocata=bool(r), punti=r["punti"] if r else [None, None],
                         ufficiale=bool(r and r.get("ufficiale"))))
    stampa(f"Dati FIGH scaricati il {cal_f.get('scaricato', '?')}: {len(figh)} partite HC Fondi, "
           f"{len(risultati)} con risultato" + ("" if ris_f else f" ({FILE_RIS_FIGH} non trovato)"))
    return ordina(figh)


# --------------------------------------------------------------------------
#  Abbinamento e confronto
# --------------------------------------------------------------------------
def parole(s):
    return set(re.findall(r"[A-Z0-9]+", norm(s))) - {"ASD", "HC", "DI", "DELLO", "DEL", "LO"}


def stesso_nome(a, b):
    pa, pb = parole(a), parole(b)
    return bool(pa) and bool(pb) and (pa <= pb or pb <= pa)


def stesso_impianto(nostro, f):
    n = parole(nostro)
    loc = parole(f["localita"]) - {"PALASPORT"}
    campo = parole(f["impianto"])
    return bool(loc & n) or (bool(campo) and len(campo & n) * 2 >= len(campo))


def data_nostra(m):
    return f"{m['date'][:5]}/{m['year']}"


def descr(m):
    return f"{data_nostra(m)} {m.get('time') or '':>5} {m['cat']:<7} {m['home']} - {m['away']}"


def descr_figh(f):
    return f"{f['data']} {f['ora']:>5} {f['cat'] or '?':<7} {f['casa']} - {f['ospite']}"


def stesso_verso(m, f):
    """True se casa/ospite di calendario.json sono nello stesso ordine della FIGH."""
    if f["cat"] == "interna":
        return categoria_fondi(m["home"]) == categoria_fondi(f["casa"])
    return in_casa(m) == f["fondi_in_casa"]


def in_casa(m):
    return m.get("gir") == "Casa"


def abbina(cal, figh):
    """[(partita FIGH, nostra partita o None)], [nostre partite senza corrispondenza].

    Stessa data e stessa categoria; se non c'è, stessa data e categoria diversa
    (così una partita messa nella categoria sbagliata viene segnalata come tale).
    """
    nostre = [m for m in cal["matches"] if not m.get("event") and m["cat"] in CATEGORIE]
    usate, coppie = set(), []

    def scegli(f, stessa_cat):
        c = [m for m in nostre if id(m) not in usate and data_nostra(m) == f["data"]
             and (m["cat"] == f["cat"]) == stessa_cat]
        if stessa_cat and f["cat"] != "interna":
            c = [m for m in c if m["cat"] != "interna"]
        c.sort(key=lambda m: m.get("time") != f["ora"])
        return c[0] if c else None

    for f in figh:
        m = scegli(f, True) or scegli(f, False)
        if m:
            usate.add(id(m))
        coppie.append((f, m))
    return coppie, [m for m in nostre if id(m) not in usate]


def punti_nostro_verso(m, f):
    pc, po = f["punti"]
    return (pc, po) if stesso_verso(m, f) else (po, pc)


def cerca_nostro_risultato(ris, m):
    """Indice in ris["results"] e punteggio (casa, ospite) di calendario.json, o (None, None)."""
    for i, r in enumerate((ris or {}).get("results", [])):
        if r["date"][:5] != m["date"][:5] or r["cat"] != m["cat"]:
            continue
        if (norm(r["home"]), norm(r["away"])) == (norm(m["home"]), norm(m["away"])):
            return i, (r["hs"], r["as"])
        if (norm(r["home"]), norm(r["away"])) == (norm(m["away"]), norm(m["home"])):
            return i, (r["as"], r["hs"])
    return None, None


def confronta(cal, ris, figh):
    venues = cal.get("venues", {})
    coppie, solo_nostre = abbina(cal, figh)
    problemi, ok = [], 0

    for f, m in coppie:
        if not m:
            problemi.append(("MANCA DA NOI", descr_figh(f), ["sul sito FIGH ma non in calendario.json"]))
            continue
        diff = []
        if m["cat"] != f["cat"]:
            diff.append(f"categoria: noi {m['cat']}, FIGH {f['cat']}")
        if (m.get("time") or "") != f["ora"]:
            diff.append(f"ora: noi {m.get('time') or '-'}, FIGH {f['ora']}")
        if f["cat"] == "interna":
            noi, loro = categoria_fondi(m["home"]), categoria_fondi(f["casa"])
            if noi != loro:
                diff.append(f"casa/ospite invertite: noi in casa {(noi or '?').upper()}, FIGH in casa {(loro or '?').upper()}")
        else:
            if in_casa(m) != f["fondi_in_casa"]:
                diff.append(f"casa/trasferta: noi {'casa' if in_casa(m) else 'trasferta'}, "
                            f"FIGH {'casa' if f['fondi_in_casa'] else 'trasferta'}")
            avv_noi = m["away"] if in_casa(m) else m["home"]
            avv_figh = f["ospite"] if f["fondi_in_casa"] else f["casa"]
            if not stesso_nome(avv_noi, avv_figh):
                diff.append(f"avversario: noi {avv_noi}, FIGH {avv_figh}")
        nostro_impianto = venues.get(m.get("venue"), m.get("venue") or "")
        if not stesso_impianto(nostro_impianto, f):
            diff.append(f"impianto: noi {nostro_impianto or '-'}, FIGH {f['impianto'].title()} ({f['localita'].title()})")

        _, nostro = cerca_nostro_risultato(ris, m)
        if f["giocata"]:
            atteso = punti_nostro_verso(m, f)
            stato = "ufficiale" if f["ufficiale"] else "non ancora ufficiale"
            if not nostro:
                diff.append(f"risultato mancante in risultati.json: FIGH {atteso[0]}-{atteso[1]} ({stato})")
            elif tuple(nostro) != tuple(atteso):
                diff.append(f"risultato: noi {nostro[0]}-{nostro[1]}, FIGH {atteso[0]}-{atteso[1]} ({stato})")
        elif nostro:
            diff.append(f"risultato {nostro[0]}-{nostro[1]} in risultati.json, ma sul sito FIGH la partita non è giocata")

        if diff:
            problemi.append(("DIVERSA", descr(m), diff))
        else:
            ok += 1

    for m in solo_nostre:
        problemi.append(("SOLO DA NOI", descr(m), ["in calendario.json ma non sul sito FIGH"]))
    return ok, problemi


def stampa_confronto(ok, problemi):
    print(f"\nCoincidono: {ok}   Differenze: {len(problemi)}\n")
    for tipo, chi, dettagli in problemi:
        print(f"[{tipo}] {chi}")
        for d in dettagli:
            print(f"    - {d}")
    if not problemi:
        print("calendario.json e risultati.json sono coerenti con i dati FIGH.")
    print("\nNon controllati (non presenti sul sito FIGH Area 7): Under 14, Selezione Talenti, finali.")
    print("Nessun file è stato modificato.")


# --------------------------------------------------------------------------
#  Caricamento dei risultati in risultati.json
# --------------------------------------------------------------------------
def risultati_da_caricare(cal, ris, figh):
    """(nuovi, cambiati, non_abbinati): cosa cambierebbe in risultati.json.

    nuovi/cambiati: liste di (partita di calendario.json, voce per risultati.json,
    indice della voce esistente o None, punteggio attuale o None, partita FIGH).
    """
    coppie, _ = abbina(cal, figh)
    nuovi, cambiati, non_abbinati = [], [], []
    for f, m in coppie:
        if not f["giocata"]:
            continue
        if not m:
            non_abbinati.append(f)
            continue
        hs, as_ = punti_nostro_verso(m, f)
        voce = {"date": m["date"][:5], "cat": m["cat"], "home": m["home"], "away": m["away"],
                "hs": hs, "as": as_, "status": "FINE"}
        i, attuale = cerca_nostro_risultato(ris, m)
        if attuale is None:
            nuovi.append((m, voce, None, None, f))
        elif tuple(attuale) != (hs, as_):
            cambiati.append((m, voce, i, attuale, f))
    return nuovi, cambiati, non_abbinati


def applica_risultati(ris, nuovi, cambiati, fonte):
    ris = json.loads(json.dumps(ris or {"results": []}))   # copia
    results = ris.setdefault("results", [])
    for _, voce, i, _, _ in cambiati:
        results[i] = dict(results[i], **voce)
    for _, voce, _, _, _ in nuovi:
        results.append(voce)
    ris["updated"] = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
    ris["source"] = fonte
    return ris


def scrivi_risultati(ris):
    """Stesso formato di risultati.json scritto a mano: una partita su due righe."""
    def campi(d):
        return ", ".join(f"{json.dumps(k)}: {json.dumps(v, ensure_ascii=False)}" for k, v in d.items())

    righe = []
    for r in ris.get("results", []):
        a = {k: r[k] for k in ("date", "cat", "home", "away") if k in r}
        b = {k: v for k, v in r.items() if k not in a}
        righe.append(f"    {{ {campi(a)},\n      {campi(b)} }}")
    testa = {k: v for k, v in ris.items() if k != "results"}
    testo = "{\n" + "".join(f"  {json.dumps(k)}: {json.dumps(v, ensure_ascii=False)},\n" for k, v in testa.items())
    testo += '  "results": [\n' + ",\n".join(righe) + ("\n" if righe else "") + "  ]\n}\n"
    json.loads(testo)                                         # controllo prima di scrivere
    path = os.path.join(HERE, "risultati.json")
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        f.write(testo)
    os.replace(path + ".tmp", path)


# --------------------------------------------------------------------------
#  Menu
# --------------------------------------------------------------------------
def chiedi(domanda, scelte=None):
    while True:
        r = input(domanda).strip().lower()
        if scelte is None or r in scelte:
            return r
        print(f"  Rispondi con: {', '.join(scelte)}")


def carica_calendario():
    cal = load("calendario.json")
    if not cal:
        raise ErroreFIGH("calendario.json non trovato.")
    return cal, load("risultati.json", {"results": []})


def azione_scarica():
    figh = leggi_online()
    n, g = salva_figh(figh)
    print(f"\nSalvati {FILE_CAL_FIGH} ({n} partite) e {FILE_RIS_FIGH} ({g} risultati).")
    return 0


def azione_confronta(online):
    cal, ris = carica_calendario()
    figh = leggi_online() if online else leggi_offline()
    ok, problemi = confronta(cal, ris, figh)
    stampa_confronto(ok, problemi)
    return 1 if problemi else 0


def azione_carica():
    cal, ris = carica_calendario()
    print("\nDa dove prendo i risultati?")
    print("  1  dal sito FIGH (online)")
    print(f"  2  dal file {FILE_RIS_FIGH} (scaricato prima)")
    print("  0  annulla")
    s = chiedi("Scelta: ", {"1", "2", "0"})
    if s == "0":
        return 0
    online = s == "1"
    figh = leggi_online() if online else leggi_offline()
    nuovi, cambiati, non_abbinati = risultati_da_caricare(cal, ris, figh)

    def riga(m, voce, f):
        stato = "" if f["ufficiale"] else "  (non ancora ufficiale)"
        return f"{data_nostra(m)} {m['cat']:<7} {m['home']} - {m['away']}  {voce['hs']}-{voce['as']}{stato}"

    if nuovi:
        print("\nRisultati nuovi da aggiungere:")
        for m, voce, _, _, f in nuovi:
            print("  + " + riga(m, voce, f))
    if cambiati:
        print("\nRisultati diversi da quelli in risultati.json (verrebbero sostituiti):")
        for m, voce, _, att, f in cambiati:
            print(f"  ~ {riga(m, voce, f)}   (ora {att[0]}-{att[1]})")
    if non_abbinati:
        print("\nRisultati FIGH senza partita in calendario.json (NON caricabili):")
        for f in non_abbinati:
            print(f"  ! {descr_figh(f)}  {f['punti'][0]}-{f['punti'][1]}")
    if not nuovi and not cambiati:
        print("\nNessun risultato da caricare: risultati.json è già aggiornato.")
        return 0

    if chiedi(f"\nAggiorno risultati.json con {len(nuovi)} nuovi e {len(cambiati)} modificati? [s/N] ",
              {"s", "n", ""}) != "s":
        print("Annullato: risultati.json non è stato modificato.")
        return 0
    fonte = "sito FIGH" if online else f"sito FIGH ({FILE_RIS_FIGH})"
    scrivi_risultati(applica_risultati(ris, nuovi, cambiati, fonte))
    print("risultati.json aggiornato.")
    print("Ricorda: rilancia  python3 genera_ics.py  e pubblica risultati.json e i .ics.")
    return 0


AZIONI = {
    "1": ("Scarica dati da FIGH", azione_scarica),
    "2": ("Confronta con dati FIGH online", lambda: azione_confronta(True)),
    "3": ("Confronta con dati FIGH offline", lambda: azione_confronta(False)),
    "4": ("Carica risultati", azione_carica),
}
COMANDI = {"scarica": "1", "online": "2", "offline": "3", "carica": "4"}


def esegui(azione):
    try:
        return azione()
    except ErroreFIGH as e:
        print(f"\nErrore: {e}")
        return 2


def menu():
    while True:
        print("\nHC Fondi - controllo con il sito FIGH (Area 7)")
        for k, (nome, _) in AZIONI.items():
            print(f"  {k}  {nome}")
        print("  0  Esci")
        s = chiedi("Scelta: ", set(AZIONI) | {"0"})
        if s == "0":
            return 0
        esegui(AZIONI[s][1])


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    try:
        if not argv:
            return menu()
        if len(argv) == 1 and argv[0] in COMANDI:
            return esegui(AZIONI[COMANDI[argv[0]]][1])
        print("Uso: python3 verifica_figh.py [scarica | online | offline | carica]")
        return 2
    except (KeyboardInterrupt, EOFError):
        print("\nUscita.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
