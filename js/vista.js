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
   Una coppia di pagine diversa (es. la versione precedente) si indica sul tag:
     <script src="js/vista.js" data-full="index-old.html"
             data-mobile="mobile-old.html"></script>
   Senza attributi la coppia è index.html / mobile.html.
   ========================================================================== */
(function(){
  var SOGLIA = 700;                 // px: sotto questa larghezza -> versione cellulare
  var KEY = "hcfondi_vista";

  var tag = document.currentScript;
  var FULL = (tag && tag.getAttribute("data-full")) || "index.html";
  var MOBILE = (tag && tag.getAttribute("data-mobile")) || "mobile.html";

  var file = location.pathname.split("/").pop() || "index.html";
  var page = file === MOBILE ? "mobile" : "full";
  var q = new URLSearchParams(location.search).get("v");
  try{
    if(q === "mobile" || q === "full") sessionStorage.setItem(KEY, q);
    else if(q === "auto") sessionStorage.removeItem(KEY);
  }catch(e){}

  var pref = null;
  try{ pref = sessionStorage.getItem(KEY); }catch(e){}
  var want = pref || (window.matchMedia("(max-width:" + SOGLIA + "px)").matches ? "mobile" : "full");

  if(want !== page) location.replace(want === "mobile" ? MOBILE : FULL);
})();
