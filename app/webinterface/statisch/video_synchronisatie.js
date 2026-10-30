"use strict";

/*
  Eén gedempte videospeler per LIVE-afspeelbeurt.

  Waarom deze module bestaat:
  De audiomixer in Python is de klok waar de gebruiker uiteindelijk op
  vertrouwt. De browser toont alleen het beeld. Bij iedere statusupdate de
  videopositie verplaatsen veroorzaakt zichtbare schokken en opnieuw decoderen.
  Daarom zoeken we één keer naar het echte startpunt. Alleen bij langdurige,
  duidelijke afwijkingen grijpen we opnieuw in.

  De module doet geen HTTP-aanvragen en weet niets van VB-CABLE, favorieten of
  databases. Het dashboard geeft uitsluitend de mediasource en de actuele
  audio-afspeelpositie door. Zo is dit apart te testen en later te vervangen.
*/
(function (venster) {
  const VIDEO_KLEINE_AFWIJKING = 0.25;
  const VIDEO_GROTE_AFWIJKING = 1.6;
  const MINIMALE_TIJD_TUSSEN_HERZOEKEN_MS = 4000;
  const MINIMALE_TIJD_VOOR_CORRECTIE_MS = 1800;
  const SNELLERE_VIDEO = 1.03;
  const LANGZAMERE_VIDEO = 0.97;

  function veiligeSeconden(waarde, standaard = 0) {
    const tijd = Number(waarde);
    return Number.isFinite(tijd) ? Math.max(0, tijd) : standaard;
  }

  function maakLiveVideospeler({ bron, stilstaandBeeld = null, beginpositie = 0, bijFout = () => {} }) {
    if (typeof bron !== "string" || !bron.startsWith("/media/")) {
      throw new TypeError("VIDEO-001: live video moet een bekende, lokale mediabron gebruiken.");
    }

    const omhulsel = document.createElement("div");
    omhulsel.className = "live-video-omhulsel";

    if (stilstaandBeeld) {
      const voorbeeldfoto = document.createElement("img");
      voorbeeldfoto.src = stilstaandBeeld;
      voorbeeldfoto.alt = "";
      voorbeeldfoto.decoding = "async";
      omhulsel.appendChild(voorbeeldfoto);
    }

    const video = document.createElement("video");
    video.className = "live-video video-wacht-op-beeld";
    video.dataset.soort = "video";
    video.preload = "auto";
    video.autoplay = false;
    video.loop = false;
    video.muted = true; // Stem/geluid komt al uit de Python-mixer. Geen dubbele audio!
    video.playsInline = true;
    video.controls = false;
    if (stilstaandBeeld) video.poster = stilstaandBeeld;
    omhulsel.appendChild(video);

    let laatsteAudiotijd = 0;
    let laatsteBeginpositie = veiligeSeconden(beginpositie);
    let ladenGestart = false;
    let isGestopt = false;
    let videoSpeelt = false;
    let buitenSyncSinds = null;
    let laatsteGroteCorrectie = 0;
    let eersteVideoframe = null;
    let laatstePositieWijzigingsnummer = null;

    function gewenstPositie() {
      const positie = laatsteBeginpositie + laatsteAudiotijd;
      const einde = Number.isFinite(video.duration) ? Math.max(0, video.duration - 0.025) : positie;
      return Math.max(0, Math.min(positie, einde));
    }

    function laatEersteVideoframeZien() {
      if (isGestopt) return;
      const zichtbaar = () => {
        if (isGestopt) return;
        video.classList.remove("video-wacht-op-beeld");
        video.classList.add("video-zichtbaar");
      };
      if (typeof video.requestVideoFrameCallback === "function") {
        // Een 'playing'-event is niet hetzelfde als een gedecodeerd videoframe.
        // Zo blijft de beginfoto zichtbaar tot het juiste beeld echt klaar is.
        eersteVideoframe = video.requestVideoFrameCallback(zichtbaar);
      } else {
        // Oudere browsers kennen deze callback niet. Alleen daar gebruiken we
        // het eerste animation frame na 'playing' als terugvalmogelijkheid.
        requestAnimationFrame(zichtbaar);
      }
    }

    async function startZodraDeBeginpositieKlaarIs() {
      if (isGestopt || ladenGestart) return;
      ladenGestart = true;

      // Spring vóór de eerste play() naar de actuele audiopositie. Tijdens
      // voorbereiden heeft Python mogelijk al nieuwe audioblokken gemengd.
      const begin = gewenstPositie();
      if (Math.abs(video.currentTime - begin) > 0.025) {
        await new Promise((klaar, mislukt) => {
          let afgelopen = false;
          let wachttijd = null;
          function rondAf(fout) {
            if (afgelopen) return;
            afgelopen = true;
            video.removeEventListener("seeked", bijZoekenKlaar);
            video.removeEventListener("error", bijZoekfout);
            clearTimeout(wachttijd);
            if (fout) mislukt(fout);
            else klaar();
          }
          const bijZoekenKlaar = () => rondAf();
          const bijZoekfout = () => rondAf(new Error("VIDEO-002: zoeken naar startpunt is mislukt."));
          video.addEventListener("seeked", bijZoekenKlaar);
          video.addEventListener("error", bijZoekfout);
          // Zoekevent kan ontbreken bij beschadigde bronnen; nooit eindeloos wachten.
          wachttijd = setTimeout(() => rondAf(new Error("VIDEO-003: startpunt niet op tijd beschikbaar.")), 5000);
          try { video.currentTime = begin; }
          catch (fout) { rondAf(fout); }
        });
      }
      if (isGestopt) return;
      await video.play();
      if (isGestopt) { video.pause(); return; }
      videoSpeelt = true;
      laatEersteVideoframeZien();
    }

    function meldingBijVideoFout(fout) {
      if (isGestopt) return;
      bijFout(fout instanceof Error ? fout : new Error(String(fout)));
    }

    video.addEventListener("loadedmetadata", () => {
      startZodraDeBeginpositieKlaarIs().catch(meldingBijVideoFout);
    }, { once: true });
    video.addEventListener("error", () => {
      meldingBijVideoFout(new Error("VIDEO-004: browser kon de MP4 niet decoderen."));
    });
    // Bron pas zetten nadat de events zijn geregistreerd, ook bij korte clips.
    video.src = bron;

    function synchroniseerMetAudio(status) {
      if (isGestopt) return;
      laatsteAudiotijd = veiligeSeconden(status.afgespeelde_seconden);
      laatsteBeginpositie = veiligeSeconden(status.beginpositie_seconden, laatsteBeginpositie);
      const wijzigingsnummer = Number(status.positie_wijzigingsnummer || 0);
      const explicieteSprong = laatstePositieWijzigingsnummer !== null &&
        wijzigingsnummer !== laatstePositieWijzigingsnummer;
      laatstePositieWijzigingsnummer = wijzigingsnummer;
      if (explicieteSprong && video.readyState >= 1) {
        // Opzettelijk zoeken of een lusgrens moet direct meebewegen.
        video.currentTime = gewenstPositie();
        video.playbackRate = 1;
        buitenSyncSinds = null;
        return;
      }
      if (!videoSpeelt || video.paused || video.seeking || video.readyState < 3) return;

      const afwijking = gewenstPositie() - video.currentTime;
      if (Math.abs(afwijking) <= VIDEO_KLEINE_AFWIJKING) {
        video.playbackRate = 1;
        buitenSyncSinds = null;
        return;
      }
      if (Math.abs(afwijking) <= VIDEO_GROTE_AFWIJKING) {
        // Kleine verschillen rustig corrigeren, zonder een zichtbaar sprongetje.
        video.playbackRate = afwijking > 0 ? SNELLERE_VIDEO : LANGZAMERE_VIDEO;
        buitenSyncSinds = null;
        return;
      }
      const nu = Date.now();
      if (buitenSyncSinds === null) buitenSyncSinds = nu;
      if (nu - buitenSyncSinds < MINIMALE_TIJD_VOOR_CORRECTIE_MS ||
          nu - laatsteGroteCorrectie < MINIMALE_TIJD_TUSSEN_HERZOEKEN_MS) return;
      // Alleen een langdurige grote afwijking rechtvaardigt een echte seek.
      // Vooral bij MP4 kan seeken tijdens normaal afspelen zichtbare hapering geven.
      video.currentTime = gewenstPositie();
      video.playbackRate = 1;
      laatsteGroteCorrectie = nu;
      buitenSyncSinds = null;
    }

    function stop() {
      if (isGestopt) return;
      isGestopt = true;
      video.pause();
      video.playbackRate = 1;
      if (eersteVideoframe !== null && typeof video.cancelVideoFrameCallback === "function") {
        video.cancelVideoFrameCallback(eersteVideoframe);
      }
      video.removeAttribute("src");
      // Het element verdwijnt uit de DOM; de oude videobuffer hoeft geen
      // extra netwerkverzoeken meer te doen. De audioverbinding blijft intact.
      video.load();
    }

    return { element: omhulsel, video, synchroniseerMetAudio, stop };
  }

  function toonPreviewNaEersteFrame(video) {
    if (typeof video.requestVideoFrameCallback === "function") {
      video.requestVideoFrameCallback(() => video.classList.remove("video-preview-wacht"));
    } else {
      // Alleen voor browsers zonder gedecodeerde-frame-callback.
      requestAnimationFrame(() => video.classList.remove("video-preview-wacht"));
    }
  }

  venster.DrostVideoSynchronisatie = Object.freeze({
    maakLiveVideospeler,
    toonPreviewNaEersteFrame
  });
})(window);
