# -*- coding: utf-8 -*-
"""Test delle pagine: stessa versione (?v=) per tutti i file CSS e JavaScript.

    python3 -m unittest test_pagine
"""

import unittest

import aggiorna_versione as av


class TestVersione(unittest.TestCase):
    def test_stessa_versione_ovunque(self):
        trovate = av.versioni()
        self.assertIn("index.html", trovate)
        self.assertIn("css/tema-rossoblu.css", trovate)
        for nome, vs in trovate.items():
            self.assertTrue(vs, f"{nome}: nessun riferimento a css/ o js/")
            self.assertNotIn(None, vs, f"{nome}: riferimento senza ?v=")
        tutte = {v for vs in trovate.values() for v in vs}
        self.assertEqual(len(tutte), 1, f"versioni diverse: {sorted(tutte)}")


if __name__ == "__main__":
    unittest.main()
