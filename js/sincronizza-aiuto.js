// ==========================================================================
//  Pulsante "?" accanto a "Sincronizza": apre una piccola guida (testo qui sotto,
//  uguale per la versione completa e quella cellulare). Si chiude con ×,
//  toccando fuori o con Esc.
// ==========================================================================
(function(){
  const TESTO = `
    <button type="button" class="help-close" aria-label="Chiudi">×</button>
    <p>Con <b>Sincronizza</b> le partite compaiono nell'app Calendario del tuo telefono o
      computer e <b>si aggiornano da sole</b>. È gratis e lo togli quando vuoi.</p>
    <ul>
      <li><b>Tutte le partite</b>: un solo calendario con tutti gli eventi.</li>
      <li>Oppure solo le <b>categorie</b> che ti interessano, un calendario per ognuna.</li>
    </ul>
    <p class="help-warn">Attenzione: se sincronizzi <b>Tutte le partite</b> e anche le singole
      categorie, ogni partita compare due volte.</p>`;

  const pops = () => document.querySelectorAll(".help-pop");
  pops().forEach(p=> p.innerHTML = TESTO);

  function chiudi(){
    pops().forEach(p=> p.hidden = true);
    document.querySelectorAll(".help-btn").forEach(b=> b.setAttribute("aria-expanded", "false"));
  }
  document.addEventListener("click", e=>{
    const b = e.target.closest(".help-btn");
    if(b){
      const p = document.getElementById(b.getAttribute("aria-controls"));
      const apri = p.hidden;
      chiudi();
      if(apri){ p.hidden = false; b.setAttribute("aria-expanded", "true"); }
      return;
    }
    if(e.target.closest(".help-close") || !e.target.closest(".help-pop")) chiudi();
  });
  document.addEventListener("keydown", e=>{ if(e.key==="Escape") chiudi(); });
})();
