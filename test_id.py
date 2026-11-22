# -*- coding: utf-8 -*-
"""Test degli id delle partite e di risultati.json nel formato con "id".

    python3 -m unittest test_id
"""

import builtins, io, json, os, shutil, tempfile, unittest
from contextlib import redirect_stdout
from unittest import mock

import eventi_comuni as ec
import aggiorna_id
import test_verifica_figh as tvf
import verifica_figh as vf

CAL = {
    "start": "01/09/2026",
    "sigle": {"HC Fondi": "HCF", "ASD Handball Flavioni U18F": "FLA",
              "HC Fondi U18F": "HCF18", "HC Fondi U16F": "HCF16"},
    "matches": [
        {"date": "20/11", "time": "15.30", "cat": "u16f", "gir": "Trasferta",
         "home": "ASD Handball Flavioni U18F", "away": "HC Fondi", "venue": "x"},
        {"date": "06/12", "time": "12.00", "cat": "interna", "gir": "Casa",
         "home": "HC Fondi U18F", "away": "HC Fondi U16F", "venue": "x"},
        {"date": "13/12", "cat": "u14", "gir": "Evento", "event": True, "home": "UNDER 14", "away": ""},
        {"date": "10/01", "time": "10.00", "cat": "u16f", "gir": "Casa",
         "home": "HC Fondi", "away": "Squadra Nuova", "venue": "x"},
    ],
}


def cal():
    return json.loads(json.dumps(CAL))


class TestId(unittest.TestCase):
    def test_formato(self):
        c = cal()
        self.assertEqual(ec.assegna_id(c), 4)
        self.assertEqual([m["id"] for m in c["matches"]], [
            "20261120-1530-u16f-fla-hcf",
            "20261206-1200-interna-hcf18-hcf16",
            "20261213-u14-under-14",                  # evento senza orario: nome intero
            "20270110-1000-u16f-hcf-squadra-nuova",   # anno successivo; senza sigla: nome
        ])
        self.assertEqual(list(c["matches"][0])[0], "id")   # id come primo campo
        self.assertEqual(ec.squadre_senza_sigla(c), ["Squadra Nuova"])

    def test_sigla_ignora_maiuscole_e_spazi(self):
        self.assertEqual(ec.sigla(CAL, "  asd handball  FLAVIONI u18f "), "fla")

    def test_id_esistenti_non_cambiano_e_doppioni(self):
        c = cal()
        c["matches"][0]["id"] = "scelto-a-mano"
        c["matches"].append(dict(CAL["matches"][1]))          # stessa partita due volte
        ec.assegna_id(c)
        ids = [m["id"] for m in c["matches"]]
        self.assertEqual(ids[0], "scelto-a-mano")
        self.assertEqual(ids[4], "20261206-1200-interna-hcf18-hcf16-2")
        self.assertEqual(ec.assegna_id(c), 0)


class TestRisultati(unittest.TestCase):
    def setUp(self):
        self.c = cal()
        ec.assegna_id(self.c)

    def test_cerca_per_id_e_formato_precedente(self):
        ris = {"results": [
            {"id": "20261120-1530-u16f-fla-hcf", "hs": 20, "as": 25, "status": "FINE"},
            # formato precedente, squadre invertite: gol girati
            {"date": "06/12", "cat": "interna", "home": "HC Fondi U16F", "away": "HC Fondi U18F",
             "hs": 10, "as": 12, "status": "1T"},
            {"id": "20270110-1000-u16f-hcf-squadra-nuova", "hs": 0, "as": 0, "status": "DA_INIZIARE"},
        ]}
        trova = ec.cerca_risultato(ris)
        m = self.c["matches"]
        self.assertEqual(trova(m[0]), (20, 25, "FINE"))
        self.assertEqual(trova(m[1]), (12, 10, "1T"))
        self.assertIsNone(trova(m[3]))

    def test_converti(self):
        ris = {"updated": "x", "results": [
            {"date": "20/11", "cat": "u16f", "home": "HC Fondi", "away": "ASD Handball Flavioni U18F",
             "hs": 25, "as": 20, "status": "FINE"},
            {"date": "01/01", "cat": "u16f", "home": "A", "away": "B", "hs": 1, "as": 0, "status": "FINE"},
        ]}
        nuovo, non_trovate = ec.converti_risultati(self.c, ris)
        self.assertEqual(nuovo["results"][0],
                         {"id": "20261120-1530-u16f-fla-hcf", "hs": 20, "as": 25, "status": "FINE"})
        self.assertEqual(nuovo["results"][1], ris["results"][1])        # resta com'era
        self.assertEqual(non_trovate, [ris["results"][1]])
        self.assertEqual(nuovo["updated"], "x")
        testo = ec.testo_risultati(nuovo)
        self.assertIn('    { "id": "20261120-1530-u16f-fla-hcf", "hs": 20, "as": 25, "status": "FINE" }', testo)
        self.assertEqual(json.loads(testo), nuovo)

    def test_id_sconosciuti(self):
        ris = {"results": [{"id": "20261120-1530-u16f-fla-hcf"}, {"id": "non-esiste"}, {"date": "01/01"}]}
        self.assertEqual(ec.id_sconosciuti(self.c, ris), ["non-esiste"])


class TestPreparaRisultati(unittest.TestCase):
    def setUp(self):
        self.c = cal()
        ec.assegna_id(self.c)

    def test_una_voce_per_partita_in_ordine(self):
        ris = {"updated": "x", "results": [
            {"id": "20270110-1000-u16f-hcf-squadra-nuova", "hs": 3, "as": 1, "status": "1T"},
            {"date": "01/01", "cat": "u16f", "home": "A", "away": "B", "hs": 1, "as": 0},  # formato vecchio
            {"id": "spostata", "hs": 0, "as": 0, "status": "DA_INIZIARE"},              # da togliere
            {"id": "sparita", "hs": 5, "as": 4, "status": "FINE"},                      # resta (ha un risultato)
        ]}
        nuovo, aggiunte, tolte = ec.prepara_risultati(self.c, ris)
        self.assertEqual((aggiunte, tolte), (2, 1))
        self.assertEqual([r.get("id") for r in nuovo["results"]], [
            "20261120-1530-u16f-fla-hcf", "20261206-1200-interna-hcf18-hcf16",
            "20270110-1000-u16f-hcf-squadra-nuova",          # l'evento 13/12 non ha voce
            None, "sparita"])
        self.assertEqual(nuovo["results"][0], {"id": "20261120-1530-u16f-fla-hcf",
                                               "hs": 0, "as": 0, "status": "DA_INIZIARE"})
        self.assertEqual(nuovo["results"][2]["status"], "1T")                # non toccata
        self.assertEqual(nuovo["updated"], "x")
        self.assertEqual(ec.prepara_risultati(self.c, nuovo)[1:], (0, 0))    # seconda volta: niente
        self.assertEqual(ec.id_sconosciuti(self.c, nuovo), ["sparita"])

    def test_da_iniziare_non_mostrato(self):
        ris, _, _ = ec.prepara_risultati(self.c, {"results": []})
        trova = ec.cerca_risultato(ris)
        self.assertTrue(all(trova(m) is None for m in self.c["matches"]))


class TestAggiornaId(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        p = mock.patch.object(ec, "HERE", self.dir)
        p.start()
        self.addCleanup(p.stop)
        self.scrivi("calendario.json", CAL)
        self.scrivi("risultati.json", {"results": [
            {"date": "20/11", "cat": "u16f", "home": "ASD Handball Flavioni U18F", "away": "HC Fondi",
             "hs": 20, "as": 25, "status": "FINE"}]})

    def scrivi(self, nome, dati):
        with open(os.path.join(self.dir, nome), "w", encoding="utf-8") as f:
            json.dump(dati, f)

    def leggi(self, nome):
        with open(os.path.join(self.dir, nome), encoding="utf-8") as f:
            return f.read()

    def esegui(self, argv, risposte=()):
        with mock.patch.object(builtins, "input", side_effect=list(risposte)), \
                redirect_stdout(io.StringIO()) as out:
            codice = aggiorna_id.main(argv)
        return codice, out.getvalue()

    def test_rifiuto_non_modifica(self):
        prima = self.leggi("calendario.json"), self.leggi("risultati.json")
        codice, out = self.esegui([], ["n"])
        self.assertEqual(codice, 1)
        self.assertIn("squadra senza sigla", out)
        self.assertEqual((self.leggi("calendario.json"), self.leggi("risultati.json")), prima)

    def test_applica_e_seconda_volta_niente(self):
        self.assertEqual(self.esegui(["--si"])[0], 0)
        c = json.loads(self.leggi("calendario.json"))
        self.assertEqual(c["matches"][0]["id"], "20261120-1530-u16f-fla-hcf")
        self.assertEqual(json.loads(self.leggi("risultati.json"))["results"], [
            {"id": "20261120-1530-u16f-fla-hcf", "hs": 20, "as": 25, "status": "FINE"},
            {"id": "20261206-1200-interna-hcf18-hcf16", "hs": 0, "as": 0, "status": "DA_INIZIARE"},
            {"id": "20270110-1000-u16f-hcf-squadra-nuova", "hs": 0, "as": 0, "status": "DA_INIZIARE"},
        ])
        codice, out = self.esegui([])
        self.assertEqual(codice, 0)
        self.assertIn("Niente da cambiare", out)


class TestVerificaFighConId(tvf.Base):
    """verifica_figh.py con calendario.json e risultati.json nel formato con id."""

    def setUp(self):
        super().setUp()
        c = json.loads(json.dumps(tvf.CAL))
        c["sigle"] = {}
        ec.assegna_id(c)
        self.cal = c
        self.ris, _ = ec.converti_risultati(c, tvf.RIS)
        self.scrivi("calendario.json", self.cal)
        self.scrivi("risultati.json", self.ris)

    def test_carica_scrive_voci_con_id(self):
        with mock.patch.object(builtins, "input", side_effect=["1", "s"]), redirect_stdout(io.StringIO()):
            vf.main(["carica"])
        ris = json.loads(self.leggi("risultati.json"))
        self.assertTrue(all("id" in r and "home" not in r for r in ris["results"]))
        trova = ec.cerca_risultato(ris)
        self.assertEqual(trova(self.cal["matches"][1]), (30, 31, "FINE"))
        self.assertEqual(trova(self.cal["matches"][3]), (28, 20, "FINE"))

    def test_voci_da_iniziare(self):
        """Partite preparate (DA_INIZIARE): il confronto le tratta come senza risultato
        e il caricamento scrive il risultato nella voce esistente, senza duplicarla."""
        ris, _, _ = ec.prepara_risultati(self.cal, {"results": []})
        self.scrivi("risultati.json", ris)
        ok, problemi = vf.confronta(self.cal, ris, self.figh())
        testo = json.dumps(problemi)
        self.assertNotIn("non è giocata", testo)
        self.assertIn("risultato mancante", testo)
        with mock.patch.object(builtins, "input", side_effect=["1", "s"]), redirect_stdout(io.StringIO()):
            vf.main(["carica"])
        dopo = json.loads(self.leggi("risultati.json"))["results"]
        self.assertEqual(len(dopo), len(ris["results"]))                     # nessuna voce in più
        trova = ec.cerca_risultato({"results": dopo})
        self.assertEqual(trova(self.cal["matches"][1]), (30, 31, "FINE"))
        self.assertEqual(trova(self.cal["matches"][3]), (28, 20, "FINE"))

    def test_risultato_cambiato_per_id(self):
        ris = json.loads(json.dumps(self.ris))
        ris["results"][0]["hs"] = 27
        _, cambiati, _ = vf.risultati_da_caricare(self.cal, ris, self.figh())
        self.assertEqual([(v["id"], v["hs"], att) for _, v, _, att, _ in cambiati],
                         [(self.cal["matches"][3]["id"], 28, (27, 20))])


if __name__ == "__main__":
    unittest.main()
