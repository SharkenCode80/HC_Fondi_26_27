/* ==========================================================================
   Scelta automatica della versione: completa (index.html) o cellulare
   (mobile.html), in base alla larghezza dello schermo.
   --------------------------------------------------------------------------
   - schermo largo fino a SOGLIA px  -> mobile.html, altrimenti index.html
   - i link "Versione cellulare" / "Versione completa" aggiungono ?v=mobile
     o ?v=full: la scelta viene ricordata finché la scheda resta aperta
     (sessionStorage), così chi cambia versione a mano non viene rimandato
     indietro. Alla visita successiva torna la scelta automatica.
   - ?v=auto annulla la scelta manuale.
   Caricato nel <head> di entrambe le pagine, prima del CSS, per evitare
   di mostrare per un attimo la versione sbagliata.
   ========================================================================== */
(function(){
  var SOGLIA = 700;                 // px: sotto questa larghezza -> versione cellulare
  var KEY = "hcfondi_vista";

  var page = /mobile\.html$/.test(location.pathname) ? "mobile" : "full";
  var q = new URLSearchParams(location.search).get("v");
  try{
    if(q === "mobile" || q === "full") sessionStorage.setItem(KEY, q);
    else if(q === "auto") sessionStorage.removeItem(KEY);
  }catch(e){}

  var pref = null;
  try{ pref = sessionStorage.getItem(KEY); }catch(e){}
  var want = pref || (window.matchMedia("(max-width:" + SOGLIA + "px)").matches ? "mobile" : "full");

  if(want !== page) location.replace(want === "mobile" ? "mobile.html" : "index.html");
})();
