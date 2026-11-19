/* ==========================================================================
   Pannello dettagli di una partita, in comune tra index.html e mobile.html.
   --------------------------------------------------------------------------
   Toccando/cliccando una partita la pagina chiama Dettagli.apri({...}) e si
   apre un <dialog> con data, squadre, punteggio, orario con fine indicativa,
   impianto e due pulsanti: "Mappa" (Google Maps) e "Aggiungi al calendario"
   (file .ics della sola partita).
   Sul cellulare il pannello sale dal basso, sullo schermo largo è una finestra
   al centro (stili "dialog.sheet" in css/base.css).
   Si chiude con la ×, cliccando fuori o con Esc.
   Dettagli.punteggio(m, r, isOurs, sep) scrive il punteggio con i gol di HC Fondi
   evidenziati (usato anche dalle card di mobile.html).

   Dettagli.apri({
     m,          // la voce di calendario.json
     indice,     // posizione della voce (per l'UID del file .ics)
     data,       // Date della partita
     categoria,  // etichetta della categoria, es. "U16 F"
     impianto,   // nome completo dell'impianto ("" se manca)
     durata,     // minuti (2 tempi + pausa) per la fine indicativa
     isOurs,     // funzione nome -> true se è una squadra HC Fondi
     risultato,  // {hs, as, status} oppure null
     stato,      // {finale, label} (statoRisultato della pagina) oppure null
   })
   ========================================================================== */
(function(){
  var MESI = ["","gennaio","febbraio","marzo","aprile","maggio","giugno","luglio","agosto",
              "settembre","ottobre","novembre","dicembre"];
  var GIORNI = ["domenica","lunedì","martedì","mercoledì","giovedì","venerdì","sabato"];
  var ESITO = { w:"Vinta", l:"Persa", d:"Pareggio" };
  var corrente = null;

  function esc(s){
    return String(s == null ? "" : s).replace(/[&<>"]/g, function(c){
      return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c];
    });
  }
  var p2 = function(n){ return String(n).padStart(2,"0"); };

  // esito dal punto di vista di HC Fondi (solo risultato finale, non per le gare interne)
  function esito(p){
    var r = p.risultato, m = p.m;
    if(!r || !Number.isFinite(r.hs) || !Number.isFinite(r.as)) return null;
    if(p.stato && !p.stato.finale) return null;
    var casa = p.isOurs(m.home), ospite = p.isOurs(m.away);
    if(casa === ospite) return null;
    var noi = casa ? r.hs : r.as, loro = casa ? r.as : r.hs;
    return noi > loro ? "w" : noi < loro ? "l" : "d";
  }

  // punteggio "casa – ospite" con i gol di HC Fondi in rosso e in grassetto (classe "gf")
  function punteggio(m, r, isOurs, sep){
    var g = function(n, nostro){ return '<span class="' + (nostro ? "gf" : "ga") + '">' + n + "</span>"; };
    return g(r.hs, isOurs(m.home)) + (sep == null ? " – " : sep) + g(r.as, isOurs(m.away));
  }

  function fine(p){
    if(!p.m.time) return "";
    var hm = p.m.time.split(".").map(Number), t = hm[0]*60 + hm[1] + (p.durata || 60);
    return Math.floor(t/60)%24 + ":" + p2(t%60);
  }

  function dialog(){
    var d = document.getElementById("sheet");     // già nella pagina, oppure creato qui
    if(!d){
      d = document.createElement("dialog");
      d.id = "sheet"; d.className = "sheet";
      d.setAttribute("aria-labelledby", "sh-teams");
      document.body.appendChild(d);
    }
    if(!d.dataset.pronto){
      d.dataset.pronto = "1";
      d.addEventListener("click", function(e){
        if(e.target === d || e.target.closest("[data-close]")) d.close();   // sfondo o ×
        if(e.target.closest("[data-ics]") && corrente) scaricaICS(corrente);
      });
    }
    return d;
  }

  function apri(p){
    corrente = p;
    var m = p.m, d = p.data, sh = dialog(), r = p.risultato, o = esito(p);
    var when = GIORNI[d.getDay()] + " " + d.getDate() + " " + MESI[d.getMonth()+1] + " " + d.getFullYear() +
               (m.time ? " · ore " + m.time.replace(".",":") : "");
    var team = function(n){ return '<span class="' + (p.isOurs(n) ? "fp" : "") + '">' + esc(n) + "</span>"; };
    var teams = m.event ? esc(m.home) : team(m.home) + ' <span class="vs">–</span> ' + team(m.away);
    var score = "";
    if(r && Number.isFinite(r.hs)){
      var parziale = p.stato && !p.stato.finale;
      var cls = o || (parziale ? "live" : "");
      var label = o ? ESITO[o] : (parziale ? p.stato.label : "");
      score = '<p class="score res ' + cls + '">' + punteggio(m, r, p.isOurs) +
              (label ? "<small>" + esc(label) + "</small>" : "") + "</p>";
    }
    var end = fine(p), venue = p.impianto || "";

    sh.className = "sheet " + m.cat;
    sh.innerHTML = '<div class="grip"></div>' +
      '<button type="button" class="x" data-close aria-label="Chiudi">×</button>' +
      '<div class="sh">' +
        '<p class="when">' + when + "</p>" +
        '<h3 class="teams" id="sh-teams">' + teams + "</h3>" + score +
        '<div class="tags"><span>' + esc(p.categoria) + "</span>" + (m.event ? "" :
          '<span class="' + (p.isOurs(m.home) ? "casa" : "") + '">' + esc(m.gir) + "</span>") + "</div>" +
      "</div>" +
      "<dl>" +
        (m.time ? "<dt>Orario</dt><dd>" + m.time.replace(".",":") + (end ? " – fine indicativa " + end : "") + "</dd>" : "") +
        (venue ? "<dt>Impianto</dt><dd>" + esc(venue) + "</dd>" : "") +
        (r && r.status && p.stato ? "<dt>Stato</dt><dd>" + esc(p.stato.label) + "</dd>" : "") +
      "</dl>" +
      '<div class="acts">' +
        (venue ? '<a href="https://www.google.com/maps/search/?api=1&query=' + encodeURIComponent(venue) +
                 '" target="_blank" rel="noopener">Mappa</a>' : "") +
        '<button type="button" class="alt" data-ics>Aggiungi al calendario</button>' +
      "</div>";
    if(!sh.open) sh.showModal();
  }

  // file .ics con la sola partita, da aprire con l'app calendario
  function scaricaICS(p){
    var m = p.m, d = p.data;
    var ymd = "" + d.getFullYear() + p2(d.getMonth()+1) + p2(d.getDate());
    var when;
    if(m.time){
      var hm = m.time.split(".").map(Number), e = hm[0]*60 + hm[1] + (p.durata || 60);
      when = "DTSTART:" + ymd + "T" + p2(hm[0]) + p2(hm[1]) + "00\r\nDTEND:" + ymd + "T" +
             p2(Math.floor(e/60)%24) + p2(e%60) + "00";
    } else {
      var n = new Date(d); n.setDate(n.getDate()+1);
      when = "DTSTART;VALUE=DATE:" + ymd + "\r\nDTEND;VALUE=DATE:" +
             n.getFullYear() + p2(n.getMonth()+1) + p2(n.getDate());
    }
    var txt = function(s){ return String(s).replace(/([,;\\])/g, "\\$1"); };
    var title = m.event ? p.categoria + ": " + m.home : p.categoria + " · " + m.home + " – " + m.away;
    var ics = ["BEGIN:VCALENDAR","VERSION:2.0","PRODID:-//HC Fondi//Campionati 26-27//IT","BEGIN:VEVENT",
      "UID:hcfondi-" + ymd + "-" + m.cat + "-" + p.indice + "@hcfondi",
      "DTSTAMP:" + new Date().toISOString().replace(/[-:]/g,"").slice(0,15) + "Z",
      when, "SUMMARY:" + txt(title),
      p.impianto ? "LOCATION:" + txt(p.impianto) : "",
      "END:VEVENT","END:VCALENDAR"].filter(Boolean).join("\r\n");
    var a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([ics], {type:"text/calendar"}));
    a.download = "HCFondi_" + ymd + "_" + m.cat + ".ics";
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(function(){ URL.revokeObjectURL(a.href); }, 2000);
  }

  window.Dettagli = { apri: apri, punteggio: punteggio };
})();
