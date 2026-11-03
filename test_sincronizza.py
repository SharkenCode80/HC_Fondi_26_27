# -*- coding: utf-8 -*-
"""
Test della logica di sincronizzazione (sincronizza_google.py) con un'API
Google Calendar simulata: non servono le librerie Google ne' la rete.

Uso:  python3 -m unittest test_sincronizza -v
"""

import copy, json, os, re, unittest

import sincronizza_google as sg
from eventi_comuni import HERE


# --------------------------------------------------------------------------
#  API simulata: events().list / insert / update / delete + .execute()
# --------------------------------------------------------------------------

class Risposta:
    def __init__(self, status):
        self.status = status


class ErroreHttp(Exception):
    """Come googleapiclient.errors.HttpError: .resp.status e .content JSON."""
    def __init__(self, status, reason=""):
        super().__init__(f"{status} {reason}")
        self.resp = Risposta(status)
        self.content = json.dumps({"error": {"code": status,
                                             "errors": [{"reason": reason}]}}).encode()


class Richiesta:
    def __init__(self, fn):
        self.fn = fn

    def execute(self):
        return self.fn()


class FintoEvents:
    def __init__(self, calendario):
        self.c = calendario

    def list(self, calendarId, privateExtendedProperty=None, showDeleted=False,
             iCalUID=None, maxResults=250, pageToken=None):
        def fn():
            self.c.chiamate.append("list")
            sel = []
            for ev in self.c.eventi.values():
                if ev.get("status") == "cancelled" and not showDeleted:
                    continue
                if iCalUID and ev.get("iCalUID") != iCalUID:
                    continue
                if privateExtendedProperty:
                    k, v = privateExtendedProperty.split("=", 1)
                    if sg.privato(ev).get(k) != v:
                        continue
                sel.append(copy.deepcopy(ev))
            i = int(pageToken or 0)
            pagina = sel[i:i + self.c.pagina]
            res = {"items": pagina}
            if i + self.c.pagina < len(sel):
                res["nextPageToken"] = str(i + self.c.pagina)
            return res
        return Richiesta(fn)

    def insert(self, calendarId, body):
        def fn():
            self.c.chiamate.append("insert")
            self.c.errore_per(body)
            if any(e.get("iCalUID") == body.get("iCalUID") for e in self.c.eventi.values()):
                raise ErroreHttp(409, "duplicate")     # anche se l'esistente e' "cancelled"
            return self.c.aggiungi(body)
        return Richiesta(fn)

    def update(self, calendarId, eventId, body):
        def fn():
            self.c.chiamate.append("update")
            self.c.errore_per(body)
            ev = copy.deepcopy(body)
            ev["id"] = eventId
            ev["iCalUID"] = self.c.eventi[eventId]["iCalUID"]
            ev.setdefault("status", "confirmed")
            self.c.eventi[eventId] = ev
            return copy.deepcopy(ev)
        return Richiesta(fn)

    def delete(self, calendarId, eventId):
        def fn():
            self.c.chiamate.append("delete")
            self.c.eventi[eventId]["status"] = "cancelled"   # come Google: resta "cancelled"
            return ""
        return Richiesta(fn)


class FintoCalendario:
    def __init__(self, pagina=2):
        self.eventi, self.chiamate, self.pagina = {}, [], pagina
        self.errori = {}                # summary -> eccezione da sollevare
        self._n = 0

    def events(self):
        return FintoEvents(self)

    def aggiungi(self, body):
        self._n += 1
        ev = copy.deepcopy(body)
        ev["id"] = f"ev{self._n}"
        ev.setdefault("status", "confirmed")
        self.eventi[ev["id"]] = ev
        return copy.deepcopy(ev)

    def errore_per(self, body):
        e = self.errori.get(body.get("summary"))
        if e:
            raise e

    def attivi(self):
        return [e for e in self.eventi.values() if e.get("status") != "cancelled"]

    def per_uid(self, u):
        return next(e for e in self.eventi.values() if e.get("iCalUID") == u)


# --------------------------------------------------------------------------
#  Calendario di prova
# --------------------------------------------------------------------------

def mini_calendario():
    return {
        "start": "03/11/2026", "fondiTeam": "HC Fondi",
        "categories": {"serieb": "Serie B", "u14": "Under 14"},
        "venues": {"fondi": "PalaSport Fondi"},
        "mister": {"durate": {"serieb": {"tempo": 30, "pausa": 10}}},
        "matches": [
            {"date": "08/11", "time": "18.00", "cat": "serieb", "home": "HC Fondi",
             "away": "Roma", "venue": "fondi", "year": 2026},
            {"date": "15/11", "time": "20.30", "cat": "serieb", "home": "Latina",
             "away": "HC Fondi", "venue": "", "year": 2026},
            {"date": "13/12", "time": "", "cat": "u14", "home": "Concentramento",
             "away": "", "venue": "", "event": True, "year": 2026},
        ],
    }


def desiderati(cal=None):
    return sg.eventi_desiderati(cal or mini_calendario(), {})


def sincronizza(api, cal=None):
    piano = sg.confronta(desiderati(cal), sg.leggi_esistenti(api, "id"))
    fatti, errori = sg.applica(api, "id", piano, log=lambda *_: None)
    return piano, fatti, errori


class TestEventi(unittest.TestCase):
    def test_orari_e_giornata_intera(self):
        ev = list(desiderati().values())
        self.assertEqual(ev[0]["start"], {"dateTime": "2026-11-08T18:00:00", "timeZone": "Europe/Rome"})
        self.assertEqual(ev[0]["end"], {"dateTime": "2026-11-08T19:10:00", "timeZone": "Europe/Rome"})
        self.assertEqual(ev[2]["start"], {"date": "2026-12-13"})
        self.assertEqual(ev[2]["end"], {"date": "2026-12-14"})      # fine esclusa
        self.assertEqual(ev[2]["transparency"], "transparent")
        p = sg.privato(ev[0])
        self.assertEqual(p["source"], sg.MARCATORE)
        self.assertEqual(p["uid"], ev[0]["iCalUID"])
        self.assertEqual(p["uid"], "serieb-hc-fondi-roma-tutte@hcfondi2627")

    def test_uid_uguali_a_calendario_ics(self):
        """Gli UID del calendario Google sono quelli di calendario.ics."""
        with open(os.path.join(HERE, "calendario.ics"), encoding="utf-8") as f:
            testo = re.sub(r"\r\n ", "", f.read())
        uid_ics = re.findall(r"^UID:(.+?)\r?$", testo, re.M)
        with open(os.path.join(HERE, "calendario.json"), encoding="utf-8") as f:
            cal = json.load(f)
        with open(os.path.join(HERE, "risultati.json"), encoding="utf-8") as f:
            ris = json.load(f)
        self.assertEqual(list(sg.eventi_desiderati(cal, ris)), uid_ics)


class TestConfronto(unittest.TestCase):
    def test_crea_poi_invariato(self):
        api = FintoCalendario()
        piano, fatti, errori = sincronizza(api)
        self.assertEqual((len(piano.crea), fatti["creati"], errori), (3, 3, []))
        self.assertEqual(len(api.attivi()), 3)

        api.chiamate.clear()
        piano, fatti, errori = sincronizza(api)
        self.assertEqual(len(piano.invariati), 3)
        self.assertEqual(piano.da_fare(), [])
        self.assertEqual([c for c in api.chiamate if c != "list"], [])

    def test_aggiorna_se_cambia(self):
        api = FintoCalendario()
        sincronizza(api)
        cal = mini_calendario()
        cal["matches"][0]["time"] = "19.30"
        piano, fatti, _ = sincronizza(api, cal)
        self.assertEqual([op.tipo for op in piano.aggiorna], ["aggiorna"])
        self.assertEqual(len(piano.invariati), 2)
        self.assertEqual(fatti["aggiornati"], 1)
        ev = api.per_uid("serieb-hc-fondi-roma-tutte@hcfondi2627")
        self.assertEqual(ev["start"]["dateTime"], "2026-11-08T19:30:00")
        self.assertEqual(len(api.attivi()), 3)

    def test_elimina_solo_eventi_dello_script(self):
        api = FintoCalendario()
        sincronizza(api)
        manuale = api.aggiungi({"summary": "Cena di squadra", "iCalUID": "a-mano@x",
                                "start": {"date": "2026-12-20"}})
        manuale_con_altro_marcatore = api.aggiungi({
            "summary": "Altro", "iCalUID": "altro@x", "start": {"date": "2026-12-21"},
            "extendedProperties": {"private": {"source": "altro-script"}}})
        prima = copy.deepcopy(api.eventi)

        cal = mini_calendario()
        del cal["matches"][1]
        piano, fatti, _ = sincronizza(api, cal)
        self.assertEqual([op.uid for op in piano.elimina],
                         ["serieb-latina-hc-fondi-tutte@hcfondi2627"])
        self.assertEqual(fatti["eliminati"], 1)
        # gli eventi aggiunti a mano non sono stati toccati
        self.assertEqual(api.eventi[manuale["id"]], prima[manuale["id"]])
        mid = manuale_con_altro_marcatore["id"]
        self.assertEqual(api.eventi[mid], prima[mid])

    def test_ripristina_evento_cancelled(self):
        api = FintoCalendario()
        sincronizza(api)
        u = "serieb-hc-fondi-roma-tutte@hcfondi2627"
        ev_id = api.per_uid(u)["id"]
        api.eventi[ev_id]["status"] = "cancelled"          # cancellato a mano su Google

        api.chiamate.clear()
        piano, fatti, errori = sincronizza(api)
        self.assertEqual([(op.tipo, op.uid) for op in piano.aggiorna], [("ripristina", u)])
        self.assertEqual(piano.crea, [])
        self.assertEqual((fatti["ripristinati"], errori), (1, []))
        self.assertNotIn("insert", api.chiamate)            # ripristinato, non ricreato
        self.assertEqual(api.eventi[ev_id]["status"], "confirmed")
        self.assertEqual(len(api.attivi()), 3)

    def test_cancelled_senza_marcatore_trovato_con_409(self):
        """iCalUID gia' presente ma "cancelled" e senza marcatore (es. importato a mano)."""
        api = FintoCalendario()
        u = "serieb-hc-fondi-roma-tutte@hcfondi2627"
        vecchio = api.aggiungi({"summary": "vecchio", "iCalUID": u, "status": "cancelled",
                                "start": {"date": "2026-11-08"}})
        piano, fatti, errori = sincronizza(api)
        self.assertEqual(len(piano.crea), 3)
        self.assertEqual((fatti["creati"], fatti["ripristinati"], errori), (2, 1, []))
        ev = api.eventi[vecchio["id"]]
        self.assertEqual(ev["status"], "confirmed")
        self.assertEqual(sg.privato(ev)["source"], sg.MARCATORE)

    def test_uid_occupato_da_evento_manuale_attivo(self):
        api = FintoCalendario()
        u = "serieb-hc-fondi-roma-tutte@hcfondi2627"
        manuale = api.aggiungi({"summary": "a mano", "iCalUID": u, "start": {"date": "2026-11-08"}})
        prima = copy.deepcopy(manuale)
        _, fatti, errori = sincronizza(api)
        self.assertEqual(fatti["creati"], 2)
        self.assertEqual([op.uid for op, _ in errori], [u])
        self.assertEqual(api.eventi[manuale["id"]], prima)

    def test_errore_su_un_evento_non_blocca_gli_altri(self):
        api = FintoCalendario()
        api.errori["Serie B · Latina – HC Fondi"] = ErroreHttp(500, "backendError")
        _, fatti, errori = sincronizza(api)
        self.assertEqual(fatti["creati"], 2)
        self.assertEqual(len(errori), 1)
        self.assertIn("HTTP 500", errori[0][1])

    def test_accesso_negato_interrompe(self):
        api = FintoCalendario()
        api.errori["Serie B · HC Fondi – Roma"] = ErroreHttp(403, "requiredAccessLevel")
        with self.assertRaises(sg.AccessoNegato):
            sincronizza(api)

    def test_paginazione(self):
        api = FintoCalendario(pagina=2)
        cal = mini_calendario()
        for g in range(20, 25):
            cal["matches"].append({"date": f"{g}/11", "time": "10.00", "cat": "serieb",
                                   "home": "HC Fondi", "away": f"Squadra {g}", "venue": "",
                                   "year": 2026})
        sincronizza(api, cal)
        self.assertEqual(len(sg.leggi_esistenti(api, "id")), 8)
        piano, _, _ = sincronizza(api, cal)
        self.assertEqual(len(piano.invariati), 8)


class TestRetry(unittest.TestCase):
    def setUp(self):
        self.attese = []
        self._dormi = sg._dormi
        sg._dormi = self.attese.append

    def tearDown(self):
        sg._dormi = self._dormi

    def richiesta(self, errori):
        errori = list(errori)
        def fn():
            if errori:
                raise errori.pop(0)
            return "ok"
        return Richiesta(fn)

    def test_429_e_rate_limit_ritentati(self):
        r = self.richiesta([ErroreHttp(429), ErroreHttp(403, "rateLimitExceeded"),
                            ErroreHttp(403, "userRateLimitExceeded")])
        self.assertEqual(sg.esegui(r), "ok")
        self.assertEqual(len(self.attese), 3)
        self.assertTrue(1 <= self.attese[0] < 2 and 2 <= self.attese[1] < 3
                        and 4 <= self.attese[2] < 5)          # backoff esponenziale

    def test_altri_errori_non_ritentati(self):
        with self.assertRaises(ErroreHttp):
            sg.esegui(self.richiesta([ErroreHttp(403, "forbidden")]))
        self.assertEqual(self.attese, [])

    def test_si_arrende_dopo_troppi_tentativi(self):
        with self.assertRaises(ErroreHttp):
            sg.esegui(self.richiesta([ErroreHttp(429)] * sg.TENTATIVI))
        self.assertEqual(len(self.attese), sg.TENTATIVI - 1)


class TestConfigurazione(unittest.TestCase):
    def test_id_da_link_pubblico(self):
        link = ("https://calendar.google.com/calendar/embed?src=abc123%40group.calendar."
                "google.com&ctz=Europe%2FRome")
        self.assertEqual(sg.pulisci_id(link), "abc123@group.calendar.google.com")
        self.assertEqual(sg.pulisci_id(f'<iframe src="{link}" style="border: 0"></iframe>'),
                         "abc123@group.calendar.google.com")
        self.assertEqual(sg.pulisci_id(" abc@group.calendar.google.com "),
                         "abc@group.calendar.google.com")

    def test_percorso_trascinato_nel_terminale(self):
        self.assertEqual(sg.pulisci_percorso("/tmp/la\\ mia\\ chiave.json"),
                         "/tmp/la mia chiave.json")
        self.assertEqual(sg.pulisci_percorso("'/tmp/a b.json'"), "/tmp/a b.json")


if __name__ == "__main__":
    unittest.main()
