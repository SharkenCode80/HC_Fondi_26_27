#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Test di verifica_figh.py con pagine FIGH finte (nessun accesso alla rete).

Uso:  python3 -m unittest test_verifica_figh -v
"""

import builtins, io, json, os, shutil, tempfile, unittest
from contextlib import redirect_stdout
from unittest import mock

import eventi_comuni
import verifica_figh as vf


def squadra(nome, fondi=False):
    return {"title": nome, "cod_aff_societa": vf.COD_FONDI if fondi else "9999"}


def gara(id_, data, ora, t1, t2, campo="FONDI PALASPORT", loc="FONDI PALASPORT", punti=None, ufficiale=False):
    return {"id": id_, "date": data, "time": ora, "day": "Giornata 1", "team1": t1, "team2": t2,
            "deno_campo": " " + campo, "localita": loc, "played": punti is not None,
            "team1-setwin": (punti or [0, 0])[0], "team2-setwin": (punti or [0, 0])[1],
            "ris_ufficiale": "1" if ufficiale else "0"}


def pagina(titolo, gare):
    cal = {"title": titolo, "giornate": {"Giornata 1": gare}}
    return f"<html><script>const calendario = {json.dumps(cal)};\nconst altro = 1;</script></html>"


FONDI, FONDI16, FONDI18 = squadra("BANCAPOPOLARE DI FONDI", True), \
    squadra("HC  BANCAPOPOLARE DI FONDI U16F", True), squadra("HC  BANCAPOPOLARE DI FONDI U18F", True)

PAGINE = {
    "serie-b-maschile-area-7-girone-unico": pagina("Serie B", [
        gara("1", "07/11/2026", "18.00", FONDI, squadra("BENEVENTO 23")),
        gara("2", "17/01/2027", "19.00", squadra("BENEVENTO 23"), FONDI, "PALA VALENTINO FERRARA", "BENEVENTO",
             punti=[30, 31], ufficiale=True),
        gara("3", "07/11/2026", "20.00", squadra("THEO GAETA"), squadra("HC ROMA")),      # non nostra
    ]),
    "under-16-maschile-area-7": pagina("Under 16 M", [
        gara("4", "01/05/2027", "11.00", squadra("ASD HELIOS SPORTING CLUB"), FONDI, "PALCASORIA", "CASORIA"),
    ]),
    "under-18-16-femminile-area-7-girone-unic": pagina("U18-16 F", [
        gara("5", "03/11/2026", "18.00", FONDI16, squadra("PDO HANDBALL SALERNO 1985 U16F"), punti=[28, 20]),
        gara("6", "14/02/2027", "11.00", squadra("CUS CASSINO GAETA U16F"), FONDI18, "IMPIANTO PALASPORT", "GAETA"),
        gara("7", "06/12/2026", "12.00", FONDI16, FONDI18),
    ]),
}

CAL = {
    "fondiTeam": "HC Fondi",
    "venues": {"fondi": "Fondi Palasport - Fondi", "bn": "Pala Valentino Ferrara ex Paladua - Benevento",
               "gaeta": "Impianto Sportivo Polivalente Palasport - Gaeta",
               "cerreto": "Palazzetto dello Sport Comunale - Cerreto Sannita"},
    "matches": [
        {"date": "07/11", "year": 2026, "time": "18.00", "cat": "serieb", "gir": "Casa",
         "home": "HC Fondi", "away": "BENEVENTO 23", "venue": "fondi"},
        {"date": "17/01", "year": 2027, "time": "19.00", "cat": "serieb", "gir": "Trasferta",
         "home": "BENEVENTO 23", "away": "HC Fondi", "venue": "bn"},
        {"date": "01/05", "year": 2027, "time": "11.00", "cat": "u16m", "gir": "Trasferta",
         "home": "ASD HELIOS SPORTING CLUB", "away": "HC Fondi", "venue": "cerreto"},
        {"date": "03/11", "year": 2026, "time": "18.00", "cat": "u16f", "gir": "Casa",
         "home": "HC Fondi", "away": "PDO Handball Salerno U16F", "venue": "fondi"},
        {"date": "14/02", "year": 2027, "time": "11.00", "cat": "u16f", "gir": "Trasferta",
         "home": "CUS Cassino Gaeta U16F", "away": "HC Fondi", "venue": "gaeta"},
        {"date": "06/12", "year": 2026, "time": "12.00", "cat": "interna", "gir": "Casa",
         "home": "HC Fondi U18F", "away": "HC Fondi U16F", "venue": "fondi"},
        {"date": "10/12", "year": 2026, "time": "18.00", "cat": "u16m", "gir": "Casa",
         "home": "HC Fondi", "away": "CUS CASSINO GAETA BLU", "venue": "fondi"},
        {"date": "13/12", "year": 2026, "cat": "u14", "gir": "Evento", "event": True,
         "home": "UNDER 14", "away": ""},
    ],
}
RIS = {"updated": "03/11/2026 20:00", "source": "inserimento manuale", "results": [
    {"date": "03/11", "cat": "u16f", "home": "HC Fondi", "away": "PDO Handball Salerno U16F",
     "hs": 28, "as": 20, "status": "FINE"}]}


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        for mod in (eventi_comuni, vf):
            p = mock.patch.object(mod, "HERE", self.dir)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.object(vf, "scarica", side_effect=lambda slug: PAGINE[slug])
        p.start()
        self.addCleanup(p.stop)
        self.scrivi("calendario.json", CAL)
        self.scrivi("risultati.json", RIS)

    def scrivi(self, nome, dati):
        with open(os.path.join(self.dir, nome), "w", encoding="utf-8") as f:
            json.dump(dati, f)

    def leggi(self, nome):
        with open(os.path.join(self.dir, nome), encoding="utf-8") as f:
            return f.read()

    def figh(self):
        with redirect_stdout(io.StringIO()):
            return vf.leggi_online()


class TestLettura(Base):
    def test_solo_partite_fondi_e_categorie(self):
        figh = {f["id"]: f for f in self.figh()}
        self.assertNotIn("3", figh)
        self.assertEqual(figh["1"]["cat"], "serieb")
        self.assertEqual(figh["4"]["cat"], "u16m")
        self.assertEqual(figh["5"]["cat"], "u16f")
        self.assertEqual(figh["6"]["cat"], "u18f")
        self.assertEqual(figh["7"]["cat"], "interna")
        self.assertTrue(figh["5"]["giocata"])
        self.assertFalse(figh["1"]["giocata"])

    def test_pagina_senza_dati(self):
        with mock.patch.object(vf, "scarica", return_value="<html></html>"):
            with self.assertRaises(vf.ErroreFIGH):
                vf.leggi_online(stampa=lambda *_: None)

    def test_scarica_e_rilegge_offline(self):
        figh = self.figh()
        self.assertEqual(vf.salva_figh(figh), (6, 2))
        dal_file = vf.leggi_offline(stampa=lambda *_: None)
        self.assertEqual([(f["id"], f["giocata"], list(f["punti"])) for f in dal_file if f["giocata"]],
                         [(f["id"], True, list(f["punti"])) for f in figh if f["giocata"]])

    def test_offline_senza_file(self):
        with self.assertRaises(vf.ErroreFIGH):
            vf.leggi_offline(stampa=lambda *_: None)


class TestConfronto(Base):
    def test_differenze(self):
        ok, problemi = vf.confronta(CAL, RIS, self.figh())
        testo = "\n".join(f"{t} {c} {d}" for t, c, d in problemi)
        self.assertIn("categoria: noi u16f, FIGH u18f", testo)
        self.assertIn("casa/ospite invertite: noi in casa U18F, FIGH in casa U16F", testo)
        self.assertIn("impianto: noi Palazzetto dello Sport Comunale - Cerreto Sannita", testo)
        self.assertIn("risultato mancante in risultati.json: FIGH 30-31", testo)
        self.assertIn("SOLO DA NOI 10/12/2026", testo)
        self.assertNotIn("u14", testo)
        self.assertEqual(ok, 2)            # 07/11 serie B e 03/11 U16 F (risultato uguale)

    def test_ora_e_risultato_diversi_e_partita_mancante(self):
        cal = json.loads(json.dumps(CAL))
        cal["matches"][0]["time"] = "17.00"
        del cal["matches"][2]
        ris = json.loads(json.dumps(RIS))
        ris["results"][0]["hs"] = 27
        _, problemi = vf.confronta(cal, ris, self.figh())
        testo = "\n".join(f"{t} {c} {d}" for t, c, d in problemi)
        self.assertIn("ora: noi 17.00, FIGH 18.00", testo)
        self.assertIn("risultato: noi 27-20, FIGH 28-20 (non ancora ufficiale)", testo)
        self.assertIn("MANCA DA NOI 01/05/2027", testo)

    def test_confronto_non_modifica_file(self):
        prima = self.leggi("risultati.json"), self.leggi("calendario.json")
        with redirect_stdout(io.StringIO()):
            self.assertEqual(vf.main(["online"]), 1)
        self.assertEqual((self.leggi("risultati.json"), self.leggi("calendario.json")), prima)


class TestCaricaRisultati(Base):
    def test_trasferta_girata_nel_nostro_verso(self):
        nuovi, cambiati, non_abbinati = vf.risultati_da_caricare(CAL, RIS, self.figh())
        self.assertEqual([v for _, v, *_ in nuovi], [
            {"date": "17/01", "cat": "serieb", "home": "BENEVENTO 23", "away": "HC Fondi",
             "hs": 30, "as": 31, "status": "FINE"}])
        self.assertEqual((cambiati, non_abbinati), ([], []))

    def test_risultato_cambiato(self):
        ris = json.loads(json.dumps(RIS))
        ris["results"][0]["hs"] = 27
        _, cambiati, _ = vf.risultati_da_caricare(CAL, ris, self.figh())
        self.assertEqual([(v["hs"], v["as"], att) for _, v, _, att, _ in cambiati], [(28, 20, (27, 20))])

    def carica(self, risposte):
        with mock.patch.object(builtins, "input", side_effect=risposte), redirect_stdout(io.StringIO()) as out:
            vf.main(["carica"])
        return out.getvalue()

    def test_rifiuto_non_modifica(self):
        prima = self.leggi("risultati.json")
        out = self.carica(["1", "n"])
        self.assertIn("+ 17/01/2027 serieb  BENEVENTO 23 - HC Fondi  30-31", out)
        self.assertEqual(self.leggi("risultati.json"), prima)

    def test_conferma_aggiorna_e_resta_leggibile(self):
        self.carica(["1", "s"])
        ris = json.loads(self.leggi("risultati.json"))
        self.assertEqual(len(ris["results"]), 2)
        self.assertEqual(ris["source"], "sito FIGH")
        trova = eventi_comuni.cerca_risultato(ris)
        self.assertEqual(trova(CAL["matches"][1]), (30, 31, "FINE"))
        self.assertEqual(trova(CAL["matches"][3]), (28, 20, "FINE"))
        self.assertIn('    { "date": "17/01", "cat": "serieb", "home": "BENEVENTO 23", "away": "HC Fondi",\n'
                      '      "hs": 30, "as": 31, "status": "FINE" }', self.leggi("risultati.json"))
        out = self.carica(["1"])
        self.assertIn("Nessun risultato da caricare", out)

    def test_da_file_offline(self):
        with redirect_stdout(io.StringIO()):
            vf.main(["scarica"])
        self.carica(["2", "s"])
        self.assertEqual(json.loads(self.leggi("risultati.json"))["source"], "sito FIGH (risultati-FIGH.json)")


class TestErrori(Base):
    def test_sito_non_raggiungibile(self):
        with mock.patch.object(vf, "scarica", side_effect=OSError("rete")), redirect_stdout(io.StringIO()):
            self.assertEqual(vf.main(["online"]), 2)

    def test_comando_sconosciuto(self):
        with redirect_stdout(io.StringIO()):
            self.assertEqual(vf.main(["boh"]), 2)


if __name__ == "__main__":
    unittest.main()
