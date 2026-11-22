# -*- coding: utf-8 -*-
"""
HC Fondi - Campionati 2026/2027 - id delle partite
--------------------------------------------------
1. Aggiunge "id" alle voci di calendario.json che non ce l'hanno
   (data con anno + ora + categoria + sigle delle squadre, es.
   20261120-1530-u16f-fla-hcf; le sigle sono nella tabella "sigle").
   Gli id gia' presenti non vengono cambiati.
2. Converte le voci di risultati.json ancora nel formato precedente
   (data, categoria, squadre) nel formato con "id":
       { "id": "20261120-1530-u16f-fla-hcf", "hs": 0, "as": 0, "status": "FINE" }
3. Prepara risultati.json con una voce per ogni partita che non ce l'ha:
       { "id": "...", "hs": 0, "as": 0, "status": "DA_INIZIARE" }
   (poi basta scrivere gol e stato); toglie le voci DA_INIZIARE di partite
   che non esistono piu'.
4. Segnala squadre senza sigla e id di risultati.json che non esistono.

Uso:  python3 aggiorna_id.py           (mostra cosa cambierebbe e chiede conferma)
      python3 aggiorna_id.py --si      (applica senza chiedere)
Poi:  python3 genera_ics.py
Nessuna libreria esterna.
"""

import json, sys

from eventi_comuni import (load, assegna_id, squadre_senza_sigla, converti_risultati,
                           prepara_risultati, id_sconosciuti, testo_calendario,
                           testo_risultati, scrivi)


def main(argv):
    cal = load("calendario.json")
    ris = load("risultati.json", {"results": []}) or {"results": []}
    if not cal:
        print("calendario.json non trovato.")
        return 2

    cal2 = json.loads(json.dumps(cal))
    n_id = assegna_id(cal2)
    ris2, non_trovate = converti_risultati(cal2, ris)
    n_ris = sum(1 for a, b in zip(ris.get("results", []), ris2["results"]) if a != b)
    ris2, aggiunte, tolte = prepara_risultati(cal2, ris2)
    cambia_ris = ris2 != ris

    print(f"calendario.json: {n_id} id da aggiungere su {len(cal2['matches'])} voci")
    print(f"risultati.json:  {n_ris} voci da convertire al formato con id, "
          f"{aggiunte} partite da aggiungere (DA_INIZIARE), {tolte} da togliere")
    for n in squadre_senza_sigla(cal2):
        print(f"  ! squadra senza sigla (nell'id va il nome intero): {n}")
    for r in non_trovate:
        print(f"  ! risultato senza partita in calendario.json: {r.get('date')} {r.get('cat')} "
              f"{r.get('home')} - {r.get('away')}")
    for i in id_sconosciuti(cal2, ris2):
        print(f"  ! id in risultati.json che non esiste in calendario.json: {i}")

    if not n_id and not cambia_ris:
        print("Niente da cambiare.")
        return 0
    if "--si" not in argv and input("Applico le modifiche? [s/N] ").strip().lower() != "s":
        print("Nessun file modificato.")
        return 1
    if n_id:
        scrivi("calendario.json", testo_calendario(cal2))
    if cambia_ris:
        scrivi("risultati.json", testo_risultati(ris2))
    print("Fatto. Ora: python3 genera_ics.py")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
