#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HC Fondi - Campionati 2026/2027 - sincronizzazione del calendario Google condiviso
--------------------------------------------------------------------------------
Porta gli eventi di calendario.json (+ risultati.json) in un calendario Google
gia' esistente, aggiornando sempre lo stesso calendario (stesso ID): crea gli
eventi nuovi, aggiorna quelli cambiati, elimina quelli tolti dal JSON.

Tocca SOLO gli eventi creati da questo script (marcatore in
extendedProperties.private): gli eventi aggiunti a mano non vengono mai
modificati ne' cancellati. Gli UID sono gli stessi di calendario.ics.

Uso:
    python3 sincronizza_google.py               riepilogo, conferma, applica
    python3 sincronizza_google.py --dry-run     solo riepilogo, nessuna modifica
    python3 sincronizza_google.py --yes         applica senza chiedere conferma
    python3 sincronizza_google.py --reconfigure rifa' le domande iniziali

Configurazione (metodo di accesso, percorsi, ID del calendario) e token in
~/.config/calendario-sync/ (fuori dal repository). Librerie: requirements.txt.
Configurazione iniziale: README, sezione "Calendario Google condiviso".
"""

import argparse, dataclasses, hashlib, json, os, random, sys, time
from urllib.parse import parse_qs, unquote, urlparse

from eventi_comuni import HERE, load, eventi_con_uid, uid, cerca_risultato, campi_evento

MARCATORE = "calendario-sync"          # extendedProperties.private.source
CALKEY = "tutte"                       # stessi UID di calendario.ics
VERSIONE_HASH = "1"                    # cambiarla forza l'aggiornamento di tutti gli eventi
TZ = "Europe/Rome"
SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
CONFIG_DIR = os.environ.get("CALENDARIO_SYNC_DIR") or \
    os.path.join(os.path.expanduser("~"), ".config", "calendario-sync")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
TOKEN_FILE = os.path.join(CONFIG_DIR, "token.json")

TENTATIVI = 6                          # retry su 429 / 403 rateLimitExceeded
_dormi = time.sleep                    # sostituito nei test


# ==========================================================================
#  Eventi desiderati (dal JSON)
# ==========================================================================

def hash_corpo(corpo):
    testo = json.dumps([VERSIONE_HASH, corpo], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(testo.encode("utf-8")).hexdigest()[:16]


def corpo_google(e, u):
    """Evento Google Calendar dai campi comuni (eventi_comuni.campi_evento)."""
    if e["giornata"]:                  # intera giornata: date, fine esclusa
        start, end = {"date": e["start"].isoformat()}, {"date": e["end"].isoformat()}
    else:                              # ora locale di Roma, l'ora legale la gestisce Google
        start = {"dateTime": e["start"].strftime("%Y-%m-%dT%H:%M:%S"), "timeZone": TZ}
        end = {"dateTime": e["end"].strftime("%Y-%m-%dT%H:%M:%S"), "timeZone": TZ}
    corpo = {"summary": e["summary"], "location": e["location"],
             "description": e["description"], "start": start, "end": end,
             "transparency": "transparent" if e["giornata"] else "opaque"}
    corpo["iCalUID"] = u
    corpo["extendedProperties"] = {"private": {
        "source": MARCATORE, "uid": u, "hash": hash_corpo(corpo)}}
    return corpo


def eventi_desiderati(cal, ris):
    """{uid: corpo} per tutte le categorie (come calendario.ics)."""
    result_for = cerca_risultato(ris)
    out = {}
    for m, d, base in eventi_con_uid(cal):
        if m["cat"] not in cal["categories"]:
            continue
        u = uid(base, CALKEY)
        out[u] = corpo_google(campi_evento(cal, m, d, result_for), u)
    return out


# ==========================================================================
#  Chiamate all'API con retry
# ==========================================================================

def stato_errore(e):
    """(codice HTTP, motivo) di un errore dell'API Google, se lo e'."""
    status = getattr(getattr(e, "resp", None), "status", None)
    try:
        status = int(status) if status is not None else None
    except (TypeError, ValueError):
        status = None
    motivo = ""
    try:
        content = e.content.decode("utf-8") if isinstance(e.content, bytes) else e.content
        err = json.loads(content)["error"]
        motivo = (err.get("errors") or [{}])[0].get("reason", "") or err.get("status", "")
    except Exception:
        det = getattr(e, "error_details", None)
        if isinstance(det, list) and det and isinstance(det[0], dict):
            motivo = det[0].get("reason", "")
    return status, motivo


def descrivi_errore(e):
    status, motivo = stato_errore(e)
    if status is None:
        return f"{type(e).__name__}: {e}"
    return f"HTTP {status}" + (f" {motivo}" if motivo else "")


def esegui(richiesta):
    """richiesta.execute() con backoff esponenziale su 429 e 403 rateLimitExceeded."""
    for n in range(TENTATIVI):
        try:
            return richiesta.execute()
        except Exception as e:
            status, motivo = stato_errore(e)
            limite = status == 429 or (status == 403 and motivo in
                                       ("rateLimitExceeded", "userRateLimitExceeded"))
            if not limite or n == TENTATIVI - 1:
                raise
            _dormi(min(2 ** n, 32) + random.random())


def leggi_esistenti(api, cal_id):
    """Eventi del calendario con il marcatore, anche quelli in stato "cancelled"."""
    items, token = [], None
    while True:
        res = esegui(api.events().list(
            calendarId=cal_id, privateExtendedProperty=f"source={MARCATORE}",
            showDeleted=True, maxResults=2500, pageToken=token))
        items += res.get("items", [])
        token = res.get("nextPageToken")
        if not token:
            return items


# ==========================================================================
#  Confronto
# ==========================================================================

@dataclasses.dataclass
class Operazione:
    tipo: str                          # crea / aggiorna / ripristina / elimina / invariato
    uid: str
    corpo: dict = None                 # evento desiderato (non per elimina)
    evento: dict = None                # evento esistente su Google (non per crea)

    @property
    def titolo(self):
        return (self.corpo or self.evento or {}).get("summary", "(senza titolo)")

    @property
    def inizio(self):
        s = (self.corpo or self.evento or {}).get("start") or {}
        return s.get("dateTime") or s.get("date") or ""


@dataclasses.dataclass
class Piano:
    crea: list
    aggiorna: list                     # comprende i "ripristina" (eventi cancelled)
    elimina: list
    invariati: list

    def da_fare(self):
        return self.crea + self.aggiorna + self.elimina


def privato(ev):
    return ((ev.get("extendedProperties") or {}).get("private")) or {}


def confronta(desiderati, esistenti):
    """Piano delle operazioni: confronto per UID, solo eventi con il marcatore."""
    attivi, cancellati, doppi = {}, {}, []
    for ev in esistenti:
        p = privato(ev)
        if p.get("source") != MARCATORE:          # mai toccare eventi non nostri
            continue
        u = p.get("uid") or ev.get("iCalUID")
        gruppo = cancellati if ev.get("status") == "cancelled" else attivi
        if u in gruppo:
            if gruppo is attivi:
                doppi.append(ev)
            continue
        gruppo[u] = ev

    piano = Piano([], [], [], [])
    for u, corpo in desiderati.items():
        ev = attivi.get(u)
        if ev is not None:
            if privato(ev).get("hash") == privato(corpo)["hash"]:
                piano.invariati.append(Operazione("invariato", u, corpo, ev))
            else:
                piano.aggiorna.append(Operazione("aggiorna", u, corpo, ev))
        elif u in cancellati:
            piano.aggiorna.append(Operazione("ripristina", u, corpo, cancellati[u]))
        else:
            piano.crea.append(Operazione("crea", u, corpo))
    for u, ev in attivi.items():
        if u not in desiderati:
            piano.elimina.append(Operazione("elimina", u, None, ev))
    for ev in doppi:                              # copie con lo stesso UID: si tiene la prima
        piano.elimina.append(Operazione("elimina", privato(ev).get("uid", ""), None, ev))
    for lista in (piano.crea, piano.aggiorna, piano.elimina, piano.invariati):
        lista.sort(key=lambda op: (op.inizio, op.titolo))
    return piano


# ==========================================================================
#  Applicazione
# ==========================================================================

class AccessoNegato(Exception):
    """Il calendario si legge ma non si puo' scrivere: inutile continuare."""


def _negato(e):
    status, motivo = stato_errore(e)
    return status == 403 and motivo in ("forbidden", "requiredAccessLevel",
                                        "forbiddenForServiceAccounts", "PERMISSION_DENIED")


def _confermato(corpo):
    return dict(corpo, status="confirmed")       # ripristina anche gli eventi "cancelled"


def _crea(api, cal_id, op):
    """Crea l'evento; se l'iCalUID esiste gia' (anche "cancelled") lo riusa."""
    try:
        esegui(api.events().insert(calendarId=cal_id, body=op.corpo))
        return "creati"
    except Exception as e:
        if stato_errore(e)[0] != 409:
            raise
    # caso noto di Google: l'iCalUID esiste gia', spesso in stato "cancelled"
    res = esegui(api.events().list(calendarId=cal_id, iCalUID=op.uid, showDeleted=True))
    trovati = res.get("items", [])
    ev = next((x for x in trovati if x.get("status") == "cancelled"), None) or \
        next((x for x in trovati if privato(x).get("source") == MARCATORE), None)
    if ev is None:
        raise RuntimeError("esiste già un evento con lo stesso UID, non creato da questo "
                           "script: lasciato com'è")
    esegui(api.events().update(calendarId=cal_id, eventId=ev["id"], body=_confermato(op.corpo)))
    return "ripristinati"


def applica(api, cal_id, piano, log=print):
    """Esegue il piano. Un errore su un evento non blocca gli altri."""
    fatti = {"creati": 0, "aggiornati": 0, "ripristinati": 0, "eliminati": 0}
    errori = []
    for op in piano.da_fare():
        try:
            if op.tipo == "crea":
                fatti[_crea(api, cal_id, op)] += 1
            elif op.tipo in ("aggiorna", "ripristina"):
                esegui(api.events().update(calendarId=cal_id, eventId=op.evento["id"],
                                           body=_confermato(op.corpo)))
                fatti["aggiornati" if op.tipo == "aggiorna" else "ripristinati"] += 1
            else:
                try:
                    esegui(api.events().delete(calendarId=cal_id, eventId=op.evento["id"]))
                except Exception as e:
                    if stato_errore(e)[0] != 410:   # 410: gia' eliminato
                        raise
                fatti["eliminati"] += 1
        except Exception as e:
            if _negato(e):
                raise AccessoNegato(descrivi_errore(e)) from e
            msg = str(e) if isinstance(e, RuntimeError) else descrivi_errore(e)
            errori.append((op, msg))
            log(f"  ERRORE {op.tipo}: {quando(op)}  {op.titolo} — {msg}")
    return fatti, errori


# ==========================================================================
#  Riepilogo
# ==========================================================================

def quando(op):
    s = op.inizio
    if len(s) == 10:                              # AAAA-MM-GG: tutto il giorno
        return f"{s[8:10]}/{s[5:7]}/{s[:4]} (giornata)"
    if len(s) >= 16:
        return f"{s[8:10]}/{s[5:7]}/{s[:4]} {s[11:16]}   "
    return s or "?"


def stampa_piano(piano, out=print):
    rip = sum(op.tipo == "ripristina" for op in piano.aggiorna)
    out(f"Da creare: {len(piano.crea)} · da aggiornare: {len(piano.aggiorna)}"
        + (f" (di cui {rip} da ripristinare)" if rip else "")
        + f" · da eliminare: {len(piano.elimina)} · invariati: {len(piano.invariati)}")
    for nome, segno, lista in (("Da creare", "+", piano.crea),
                               ("Da aggiornare", "~", piano.aggiorna),
                               ("Da eliminare", "-", piano.elimina)):
        if lista:
            out(f"\n{nome}:")
            for op in lista:
                extra = "  (era cancellato: ripristino)" if op.tipo == "ripristina" else ""
                out(f"  {segno} {quando(op)}  {op.titolo}{extra}")


# ==========================================================================
#  Configurazione
# ==========================================================================

def carica_config():
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def salva_privato(path, testo):
    """File leggibile solo dall'utente, nella cartella di configurazione."""
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(testo)
    os.chmod(path, 0o600)


def salva_config(cfg):
    salva_privato(CONFIG_FILE, json.dumps(cfg, ensure_ascii=False, indent=2) + "\n")


def pulisci_percorso(s):
    """Percorso incollato o trascinato nel Terminale: virgolette e "\\ " tolti."""
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "'\"":
        s = s[1:-1]
    s = s.replace("\\ ", " ")
    return os.path.abspath(os.path.expanduser(s))


def pulisci_id(s):
    """Accetta l'ID oppure il link pubblico / il codice <iframe> (primo src con "@")."""
    s = s.strip()
    if "src=" in s:
        q = s[s.index("calendar/embed"):] if "calendar/embed" in s else s
        q = q.split('"')[0].split("'")[0].replace("&amp;", "&")
        srcs = [x for x in parse_qs(urlparse(q).query).get("src", []) if "@" in x]
        if srcs:
            s = srcs[0]
    return unquote(s).strip()


def chiedi(domanda, predefinito=None):
    suff = f" [{predefinito}]" if predefinito else ""
    r = input(f"{domanda}{suff}: ").strip()
    return r or (predefinito or "")


def chiedi_file(domanda, predefinito=None):
    while True:
        p = pulisci_percorso(chiedi(domanda, predefinito))
        if os.path.isfile(p):
            if os.path.commonpath([p, HERE]) == HERE:
                print(f"  Attenzione: il file è dentro il repository. Spostalo in {CONFIG_DIR}"
                      " (è comunque escluso da .gitignore, ma è più sicuro fuori).")
            return p
        print("  File non trovato, riprova.")


def chiedi_config(prec=None):
    prec = prec or {}
    print("Configurazione della sincronizzazione (salvata in "
          f"{CONFIG_DIR}, fuori dal repository).\n")
    print("Come accedo al calendario Google?")
    print("  1) Account di servizio (file chiave JSON) — consigliato per l'uso ricorrente")
    print("  2) Il tuo account Google (OAuth, si apre il browser)")
    pred = {"servizio": "1", "oauth": "2"}.get(prec.get("metodo"), "1")
    while True:
        s = chiedi("Scelta 1 o 2", pred)
        if s in ("1", "2"):
            break
    cfg = {"metodo": "servizio" if s == "1" else "oauth"}
    if cfg["metodo"] == "servizio":
        cfg["chiave"] = chiedi_file("Percorso del file chiave JSON dell'account di servizio",
                                    prec.get("chiave"))
    else:
        cfg["client_secret"] = chiedi_file("Percorso del file client_secret (app desktop)",
                                           prec.get("client_secret"))
    while True:
        cid = pulisci_id(chiedi("ID del calendario Google (Impostazioni del calendario → "
                                "Integra calendario)", prec.get("calendar_id")))
        if cid.endswith("@import.calendar.google.com"):
            print("  Questo è un calendario aggiunto \"Da URL\": Google lo gestisce in sola"
                  " lettura e non si può aggiornare. Crea un calendario nuovo"
                  " (Altri calendari → + → Crea nuovo calendario) e usa il suo ID.")
            continue
        if "@" in cid or cid == "primary":
            break
        print("  Non sembra un ID di calendario (es. …@group.calendar.google.com), riprova.")
    cfg["calendar_id"] = cid
    salva_config(cfg)
    print(f"Configurazione salvata in {CONFIG_FILE}\n")
    return cfg


# ==========================================================================
#  Accesso a Google
# ==========================================================================

def credenziali_servizio(cfg):
    from google.oauth2 import service_account
    creds = service_account.Credentials.from_service_account_file(cfg["chiave"], scopes=SCOPES)
    return creds, creds.service_account_email


def credenziali_oauth(cfg, nuova=False):
    from google.auth.exceptions import RefreshError
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = None
    if not nuova and os.path.exists(TOKEN_FILE):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        except ValueError:
            creds = None
    if creds and creds.valid:
        return creds, None
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            salva_privato(TOKEN_FILE, creds.to_json())
            return creds, None
        except RefreshError:
            print("L'autorizzazione Google è scaduta o è stata revocata: la rifaccio.")
    print("Si apre il browser per autorizzare l'accesso al calendario.")
    print("Nota: se il progetto Google Cloud è in stato \"Testing\", l'autorizzazione dura"
          " 7 giorni; poi lo script la richiede di nuovo da solo.")
    flow = InstalledAppFlow.from_client_secrets_file(cfg["client_secret"], SCOPES)
    creds = flow.run_local_server(
        port=0, prompt="consent",
        authorization_prompt_message="Se il browser non si apre, visita questo indirizzo: {url}",
        success_message="Autorizzazione completata: puoi chiudere questa finestra.")
    salva_privato(TOKEN_FILE, creds.to_json())
    return creds, None


def costruisci_api(creds):
    from googleapiclient.discovery import build
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def messaggio_condivisione(cfg, email):
    if cfg["metodo"] == "servizio":
        return ("Il calendario non è accessibile in scrittura all'account di servizio.\n"
                "Da Google Calendar (computer): impostazioni del calendario → \"Condividi con"
                " persone e gruppi specifici\" → Aggiungi persone → inserisci\n"
                f"    {email}\n"
                "con il permesso \"Apportare modifiche agli eventi\", poi rilancia lo script.")
    return ("Il calendario non è accessibile in scrittura con il tuo account Google.\n"
            "Controlla l'ID del calendario (--reconfigure) e di averlo autorizzato con l'account"
            " che ne è proprietario o che ha il permesso \"Apportare modifiche agli eventi\".")


def connetti(cfg):
    """(api, email account di servizio o None). Rifa' OAuth se il token e' revocato."""
    for chiave in ("chiave", "client_secret"):
        if chiave in cfg and not os.path.isfile(cfg[chiave]):
            sys.exit(f"File non trovato: {cfg[chiave]}\nRilancia con --reconfigure.")
    if cfg["metodo"] == "servizio":
        creds, email = credenziali_servizio(cfg)
        return costruisci_api(creds), email
    from google.auth.exceptions import RefreshError
    creds, email = credenziali_oauth(cfg)
    api = costruisci_api(creds)
    try:
        esegui(api.events().list(calendarId=cfg["calendar_id"], maxResults=1))
    except RefreshError:
        creds, email = credenziali_oauth(cfg, nuova=True)
        api = costruisci_api(creds)
    except Exception as e:
        if stato_errore(e)[0] == 401:
            creds, email = credenziali_oauth(cfg, nuova=True)
            api = costruisci_api(creds)
    return api, email


# ==========================================================================
#  Main
# ==========================================================================

def main(argv=None):
    ap = argparse.ArgumentParser(description="Sincronizza calendario.json con il calendario "
                                             "Google condiviso.")
    ap.add_argument("--dry-run", action="store_true", help="mostra il riepilogo ed esce")
    ap.add_argument("--yes", "-y", action="store_true", help="applica senza chiedere conferma")
    ap.add_argument("--reconfigure", action="store_true", help="rifà le domande iniziali")
    args = ap.parse_args(argv)

    cfg = carica_config()
    if args.reconfigure or not cfg or "calendar_id" not in cfg:
        if not sys.stdin.isatty():
            sys.exit("Configurazione mancante: lancia lo script da un terminale.")
        cfg = chiedi_config(cfg)

    cal = load("calendario.json")
    if not cal:
        sys.exit("calendario.json non trovato.")
    desiderati = eventi_desiderati(cal, load("risultati.json", {}) or {})

    try:
        api, email = connetti(cfg)
    except ImportError:
        sys.exit("Mancano le librerie Google. Installale con:\n"
                 f"    python3 -m pip install -r {os.path.join(HERE, 'requirements.txt')}")
    cal_id = cfg["calendar_id"]
    print(f"Calendario: {cal_id}"
          + (f"\nAccount di servizio: {email}" if email else "\nAccount: il tuo account Google"))

    try:
        esistenti = leggi_esistenti(api, cal_id)
    except Exception as e:
        if stato_errore(e)[0] in (403, 404):
            sys.exit(f"Calendario non accessibile ({descrivi_errore(e)}).\n"
                     + messaggio_condivisione(cfg, email))
        raise
    piano = confronta(desiderati, esistenti)
    print(f"Eventi in calendario.json: {len(desiderati)}\n")
    stampa_piano(piano)

    if not piano.da_fare():
        print("\nNiente da fare: il calendario Google è già aggiornato.")
        return 0
    if args.dry_run:
        print("\n--dry-run: nessuna modifica eseguita.")
        return 0
    if not args.yes:
        if not sys.stdin.isatty():
            sys.exit("\nServe una conferma: rilancia da un terminale oppure con --yes.")
        if input("\nProcedo? [s/N] ").strip().lower() not in ("s", "si", "sì", "y", "yes"):
            print("Annullato: nessuna modifica eseguita.")
            return 0

    print("\nApplico le modifiche…")
    try:
        fatti, errori = applica(api, cal_id, piano)
    except AccessoNegato as e:
        sys.exit(f"Scrittura rifiutata ({e}).\n" + messaggio_condivisione(cfg, email))
    print(f"\nFatto: {fatti['creati']} creati, {fatti['aggiornati']} aggiornati, "
          f"{fatti['ripristinati']} ripristinati, {fatti['eliminati']} eliminati, "
          f"{len(piano.invariati)} invariati.")
    if errori:
        print(f"Errori: {len(errori)}")
        for op, msg in errori:
            print(f"  {op.tipo} {quando(op)}  {op.titolo} — {msg}")
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit("\nInterrotto.")
