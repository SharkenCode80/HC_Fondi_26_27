/* ==========================================================================
   Aggiornamento automatico dei risultati, in comune tra index.html e mobile.html.
   --------------------------------------------------------------------------
   La pagina riscarica risultati.json e, se è cambiato, ridisegna le partite
   senza ricaricarsi (filtri, posizione e pannello aperto restano come sono).

   Quanto spesso:
   - durante una partita (dall'orario d'inizio fino alla fine indicativa
     + 20 minuti) ogni minuto;
   - altrimenti ogni 10 minuti, e comunque all'inizio della prossima partita;
   - con la pagina non visibile (app in secondo piano, schermo spento, altra
     scheda) niente: appena torna visibile, o quando il browser la ripristina
     tornando indietro da un'altra pagina, controlla subito i risultati
     (se l'ultimo controllo è di almeno 30 secondi prima).
   calendario.json si controlla fuori dalle partite e comunque se l'ultimo
   controllo è di almeno 10 minuti prima: se è cambiato, o se è cambiato il
   giorno (OGGI / Prossima), la pagina si ricarica.

   Aggiornamento.avvia({
     risultati,    // testo di risultati.json già caricato dalla pagina (o null)
     calendario,   // testo di calendario.json già caricato dalla pagina
     finestre,     // funzione -> [[inizio, fine], ...] in millisecondi (partite con orario)
     aggiorna,     // funzione(datiRisultati): la pagina applica i risultati e ridisegna
   })
   I file si scaricano con "?t=..." e senza cache, così arriva sempre l'ultima
   versione pubblicata anche se GitHub Pages ne tiene una copia per 10 minuti.
   ========================================================================== */
(function(){
  var MINUTO = 60 * 1000;
  var VELOCE = MINUTO;            // durante le partite
  var LENTO = 10 * MINUTO;        // il resto del tempo
  var DOPO = 20 * MINUTO;         // margine dopo la fine indicativa
  var DI_NUOVO = 30 * 1000;       // al ritorno sulla pagina: niente controllo se l'ultimo è più recente
  var opt = null, timer = null, occupato = false, giorno = null;
  var ultimoRis = 0, ultimoCal = 0;   // ora degli ultimi controlli (ms)

  function oggi(){ var n = new Date(); return n.getFullYear()*10000 + (n.getMonth()+1)*100 + n.getDate(); }

  function inPartita(ora){
    return opt.finestre().some(function(w){ return ora >= w[0] && ora <= w[1] + DOPO; });
  }
  function prossimoInizio(ora){
    var p = null;
    opt.finestre().forEach(function(w){ if(w[0] > ora && (p === null || w[0] < p)) p = w[0]; });
    return p;
  }

  function pianifica(){
    clearTimeout(timer);
    if(document.hidden) return;                       // si riprende con "visibilitychange"
    var ora = Date.now(), attesa = inPartita(ora) ? VELOCE : LENTO;
    var p = prossimoInizio(ora);
    if(p !== null && p - ora < attesa) attesa = Math.max(p - ora, 1000);
    timer = setTimeout(controlla, attesa);
  }

  function scarica(nome){
    return fetch(nome + "?t=" + Date.now(), {cache:"no-store"})
      .then(function(r){ return r.ok ? r.text() : null; });
  }

  function controlla(){
    if(occupato || !opt) return;
    occupato = true;
    var ora = Date.now();
    var conCalendario = !inPartita(ora) || ora - ultimoCal >= LENTO;
    // cambio di giorno: "OGGI" / "Prossima" e mese iniziale vanno ricalcolati
    if(giorno !== oggi()){ location.reload(); return; }
    scarica("risultati.json").then(function(testo){
      ultimoRis = Date.now();
      if(testo !== null && testo !== opt.risultati){
        var dati = JSON.parse(testo);                 // JSON non valido: si riprova al giro dopo
        opt.risultati = testo;
        opt.aggiorna(dati);
      }
      if(!conCalendario) return null;
      ultimoCal = Date.now();
      return scarica("calendario.json");
    }).then(function(cal){
      if(cal !== null && opt.calendario !== null && cal !== opt.calendario) location.reload();
    }).catch(function(){ /* rete assente o file non valido: si riprova al giro dopo */ })
      .then(function(){ occupato = false; pianifica(); });
  }

  // la pagina torna visibile (o viene ripristinata tornando indietro): controllo subito,
  // a meno che l'ultimo sia di pochi secondi fa (in quel caso si riprende il ritmo normale)
  function ripresa(){
    if(Date.now() - ultimoRis >= DI_NUOVO) controlla();
    else pianifica();
  }

  function avvia(o){
    opt = o;
    giorno = oggi();
    ultimoRis = ultimoCal = Date.now();              // la pagina ha appena caricato i due file
    document.addEventListener("visibilitychange", function(){
      if(document.hidden) clearTimeout(timer);
      else ripresa();
    });
    window.addEventListener("pageshow", function(e){ if(e.persisted) ripresa(); });
    pianifica();
  }

  window.Aggiornamento = { avvia: avvia, controlla: controlla };
})();
