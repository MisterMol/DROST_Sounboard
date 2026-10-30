"use strict";

/*
  Dit bestand regelt alleen de webinterface. Python doet de echte audiomix.
  Een preview blijft in de browser; uitsturen via de virtuele microfoon gaat via Python.
  We tonen video en GIF alleen zolang de bijbehorende audio actief is.
*/
const beveiligingscode = document.querySelector('meta[name="drost-token"]').content;
const element = (id) => document.getElementById(id);
const toestand = {
  natuurlijkeStem: null, natuurlijkeStemBezig: false, stembeheerBezig: false, stemkeuzeBezig: false, stemkeuzeGeneratie: 0, stemkeuzeOpdracht: null,
  geluiden: [], favorieten: Array(15).fill(null), status: null,
  gekozenGeluid: null, gekozenPlek: null, bezetteStatusaanvraag: false,
  bezigMetImport: false, laatsteAudiofout: null, vbCable: null, normalisatiestand: "uit", effectvolumePercentage: 75, limiterAan: true, laatsteLimiterFouten: 0, verbindingInBehandeling: false,
  preview: null, previewHerhalen: false, live: null, verwachtGeluid: null, gewensteSpelmodus: null, previewGereedVoorExtern: false, afspeelVolgnummer: 0, stemprofiel: "normaal", stemactief: false, stemvoorbeeldActief: false, stemvoorbeeldBezig: false, stemprofielen: [], stemintensiteiten: {}, stemparameters: {}, stemparametersCatalogus: {}, voorbeeldspreker: "bob",
  laatstGekozenMonitor: null, microfoonHandmatigGekozen: false, automatischeVerbindingGeprobeerd: false, automatischEenMicrofoon: null, eigenStemMonitorAan: false, eigenStemMonitorVolume: 25,
  groepen: [], actieveGroep: "alle",
  audiopackBestand: null, audiopackGeluiden: [], audiopackSelectie: new Set(),
  editorVoorbeeld: null, editorGolfvormWachttijd: null, golfvormVolgnummer: 0,
  editorAfspeelpositie: 0, editorIsAanHetSlepen: false,
  editorAfspeelAnimatie: null, editorGolfvormData: null,
  editorGroepenKeuze: new Set(), editorUitzendGeluidId: null, editorVolumeVolgnummer: 0,
  laatstGemetenPieken: [null, null],
  editorVensterBegin: 0, editorVensterDuur: 120,
  editorKniprand: null, editorLangVasthouden: null,
  editorLaatstePointerX: 0,
  beheerGeselecteerd: new Set(), beheerZichtbaarAantal: 60,
  laatsteAfspeelkeuze: null, herhaalVerzoek: null, herhaalVolgnummer: 0,
  bibliotheekZichtbaarAantal: 60
};

// Een klik is een verzoek, niet direct een bevestigde audiostand.
const effectenBediening = { bezig: false, generatie: 0, bevestigd: null, fout: '' };

function toonLaadindicator(node, bezig) {
  if (!node) return;
  node.classList.toggle('is-laden', Boolean(bezig));
  node.setAttribute('aria-busy', String(Boolean(bezig)));
}

function werkEffectenBedieningBij() {
  const knop = element('knop-effecten');
  if (!knop) return;
  const aan = effectenBediening.bevestigd ?? Boolean(toestand.status?.effecten_aan);
  knop.disabled = effectenBediening.bezig || toestand.status?.toestand !== 'verbonden';
  knop.setAttribute('aria-checked', String(aan));
  toonLaadindicator(knop, effectenBediening.bezig);
  const tekst = element('effecten-schakelstatus');
  if (tekst) {
    tekst.textContent = effectenBediening.bezig
      ? (aan ? 'Effecten uitschakelen…' : 'Effecten inschakelen…')
      : effectenBediening.fout || (toestand.status?.toestand !== 'verbonden'
        ? 'Verbind eerst de microfoon.' : aan ? 'Effecten aan' : 'Effecten uit');
    tekst.dataset.fout = String(Boolean(effectenBediening.fout));
  }
}

async function schakelGeluidseffecten() {
  if (effectenBediening.bezig || toestand.status?.toestand !== 'verbonden') return;
  const aan = !(effectenBediening.bevestigd ?? Boolean(toestand.status.effecten_aan));
  effectenBediening.bezig = true; effectenBediening.fout = ''; ++effectenBediening.generatie;
  werkEffectenBedieningBij();
  try {
    let antwoord = await vraagAanPython('POST', '/api/effecten', {aan});
    const uitersteTijd = performance.now() + 5000;
    while (antwoord.in_behandeling && antwoord.effecten_aan !== aan) {
      if (antwoord.toestand !== 'verbonden') throw new Error('De microfoonverbinding is verbroken. Verbind opnieuw.');
      if (performance.now() >= uitersteTijd) throw new Error('De effectenstand is nog niet bevestigd. Controleer de verbinding.');
      await new Promise(resolve => setTimeout(resolve, 100));
      const status = await vraagAanPython('GET', '/api/status');
      antwoord = {...status, in_behandeling: status.effecten_aan !== aan};
    }
    if (typeof antwoord.effecten_aan !== 'boolean') throw new Error('De app heeft de nieuwe effectenstand niet bevestigd.');
    effectenBediening.bevestigd = antwoord.effecten_aan;
    toestand.status = {...toestand.status, effecten_aan: antwoord.effecten_aan,
      toestand: typeof antwoord.toestand === 'string' ? antwoord.toestand : toestand.status.toestand};
  } catch (fout) {
    // Een verloren antwoord kan een geslaagde wijziging verbergen. Alleen lezen,
    // nooit de schakelopdracht automatisch opnieuw versturen.
    try {
      const status = await vraagAanPython('GET', '/api/status');
      if (typeof status.effecten_aan === 'boolean') {
        effectenBediening.bevestigd = status.effecten_aan;
        toestand.status = {...toestand.status, effecten_aan: status.effecten_aan, toestand: status.toestand};
      }
    } catch { /* Laatst bevestigde stand blijft zichtbaar. */ }
    effectenBediening.fout = 'Schakelen niet bevestigd. Controleer de stand en probeer opnieuw.';
    throw fout;
  } finally {
    effectenBediening.bezig = false; ++effectenBediening.generatie;
    werkEffectenBedieningBij();
  }
}

// Een Web Audio GainNode is noodzakelijk voor previewvolume boven 100%.
// De browser houdt het originele mediabestand (en MP4-video) intact.
let previewAudioContext = null;
const previewAudioBussen = new WeakMap();

function maakPreviewAudioBus(speler) {
  const AudioContextKlasse = window.AudioContext || window.webkitAudioContext;
  if (!AudioContextKlasse) throw new Error("Deze browser ondersteunt geen geluidsnormalisatie tijdens Preview.");
  if (!previewAudioContext) previewAudioContext = new AudioContextKlasse();
  let bus = previewAudioBussen.get(speler);
  if (!bus) {
    const bron = previewAudioContext.createMediaElementSource(speler);
    const versterker = previewAudioContext.createGain();
    versterker.gain.value = 0; // Geen origineel geluid vóór de juiste gain bekend is.
    bron.connect(versterker);
    const begrenzer = previewAudioContext.createDynamicsCompressor();
    begrenzer.threshold.value = -1;
    begrenzer.knee.value = 0;
    begrenzer.ratio.value = 20;
    begrenzer.attack.value = 0.001;
    begrenzer.release.value = 0.08;
    versterker.connect(begrenzer);
    begrenzer.connect(previewAudioContext.destination);
    bus = { versterker, begrenzer };
    previewAudioBussen.set(speler, bus);
  }
  // Belangrijk: direct bij de klik activeren, vóór een eventuele HTTP-await.
  const activering = previewAudioContext.resume();
  return { bus, activering };
}

function gebruikPreviewNormalisatie(voorbeeld, schrijfUitleg = false) {
  if (!voorbeeld?.normalisatieData || !voorbeeld.audioBus) return;
  const stand = toestand.normalisatiestand;
  if (voorbeeld.audioBus.begrenzer) {
    voorbeeld.audioBus.begrenzer.ratio.setTargetAtTime(toestand.limiterAan ? 20 : 1,
      previewAudioContext.currentTime, 0.012);
  }
  const waarde = Number(voorbeeld.normalisatieData.versterkingen?.[stand]);
  const correctie = Number(voorbeeld.normalisatieData.correcties_db?.[stand]);
  if (!Number.isFinite(waarde) || waarde < 0 || !Number.isFinite(correctie)) {
    throw new Error("De normalisatie voor deze preview is ongeldig. Probeer opnieuw.");
  }
  // Zelfde berekening als de audiomixer, zonder een tweede mediaspeler.
  const previewvolume = toestand.preview === voorbeeld && Number.isFinite(voorbeeld.tijdelijkVolume)
    ? voorbeeld.tijdelijkVolume : (toestand.effectvolumePercentage ?? 100);
  const effectvolumeFactor = previewvolume / 100;
  const basisvolume = voorbeeld.basisvolume ?? voorbeeld.normalisatieData.basisvolume ?? 1;
  voorbeeld.audioBus.versterker.gain.setTargetAtTime(
    waarde * basisvolume * effectvolumeFactor, previewAudioContext.currentTime, 0.012);
  const verschil = (correctie > 0 ? "+" : "") + correctie.toFixed(1) + " dB";
  const standnaam = stand === "uit" ? "Uit" : stand[0].toUpperCase() + stand.slice(1);
  element("normalisatie-preview-resultaat").textContent =
    `Preview: ${standnaam}, ${verschil}. Volume ${previewvolume}%.`;
  if (schrijfUitleg && toestand.preview === voorbeeld) {
    // Slechts één korte zin. De berekende waarden staan in eigen, rustige labels.
    element("huidige-uitleg").textContent = "Preview, alleen lokaal.";
  }
  if (toestand.preview === voorbeeld) {
    element("speler-meta").hidden = false;
    element("speler-volume-info").hidden = true;
    element("speler-volume-regelaar").hidden = false;
    const slider = element("speler-volume-schuif");
    slider.value = String(previewvolume);
    element("speler-volume-waarde").textContent = `${previewvolume}%`;
    const label = element("speler-correctie-info");
    label.hidden = Math.abs(correctie) < 0.05;
    label.textContent = `Normalisatie ${verschil}`;
  }
  if (toestand.editorVoorbeeld === voorbeeld && voorbeeld.speelt) {
    element("editor-speelstatus").textContent = 'Preview speelt lokaal.';
  }
  werkVolumeSamenhangBij();
}

async function leesPreviewNormalisatie(geluidId, begin = null, duur = null, volume = null) {
  let pad = `/api/geluiden/${geluidId}/preview-normalisatie`;
  const parameters = new URLSearchParams();
  if (begin !== null && duur !== null) {
    parameters.set('begin', String(begin));
    parameters.set('duur', String(duur));
  }
  parameters.set('volume', '1'); // Analyse zonder ingebakken basisvolume.
  if (parameters.size) pad += `?${parameters}`;
  const gegevens = await vraagAanPython("GET", pad);
  return {...gegevens, basisvolume:volume ?? vindGeluid(geluidId)?.volume ?? 1};
}

function maakElement(soort, klasse = "", tekst = undefined) {
  const gemaakt = document.createElement(soort);
  if (klasse) gemaakt.className = klasse;
  if (tekst !== undefined) gemaakt.textContent = String(tekst);
  return gemaakt;
}

// Bereikbaarheid van de app is iets anders dan de microfoonverbinding.
const applicatieVerbinding = { bereikbaar: null, nieuweSessie: false };
let appAfsluitingAangevraagd = false;
let appAfsluitenBezig = false;
let statusTimer = null;
let recentTimer = null;
const APP_NIET_BEREIKBAAR = 'DrostSoundboard is niet bereikbaar. Staat de applicatie aan? Start de app en probeer het opnieuw.';
const PAGINA_VERNIEUWEN = 'Deze pagina hoort bij een eerdere sessie. Vernieuw de pagina en probeer het opnieuw.';

function toonApplicatieverbinding(bereikbaar, nieuweSessie = false) {
  const veranderd = applicatieVerbinding.bereikbaar !== bereikbaar;
  if (appAfsluitingAangevraagd) return;
  applicatieVerbinding.bereikbaar = bereikbaar;
  applicatieVerbinding.nieuweSessie = applicatieVerbinding.nieuweSessie || nieuweSessie;
  const balk = element('app-verbinding-melding');
  if (!balk) return;
  balk.hidden = bereikbaar && !applicatieVerbinding.nieuweSessie;
  const tekst = !bereikbaar ? APP_NIET_BEREIKBAAR : PAGINA_VERNIEUWEN;
  if (element('app-verbinding-tekst').textContent !== tekst) element('app-verbinding-tekst').textContent = tekst;
  if (!bereikbaar) {
    element('kleine-status')?.classList.remove('actief');
    const chip = element('kleine-status')?.querySelector('span');
    if (chip) chip.textContent = ' App niet bereikbaar';
  }
  if (veranderd && element('stem-laadstatus')) werkStemLaadstatusBij();
}

async function haalBijApplicatie(pad, opties = {}) {
  if (appAfsluitingAangevraagd && pad !== '/api/app/afsluiten') {
    throw new Error('DrostSoundboard wordt afgesloten. Start de app opnieuw om verder te gaan.');
  }
  const controller = new AbortController();
  const bronSignaal = opties.signal;
  const afbreken = () => controller.abort();
  if (bronSignaal?.aborted) controller.abort();
  else bronSignaal?.addEventListener('abort', afbreken, {once:true});
  // Voor import en decoderen geldt een ruimere grens dan voor een statuslezing.
  const wachttijd = pad === '/api/status' ? 5000
    : ['/api/effecten', '/api/stemkeuze', '/api/stemkeuze/actief'].includes(pad) ? 15000 : 180000;
  let verlopen = false;
  const timer = setTimeout(() => { verlopen = true; controller.abort(); }, wachttijd);
  try {
    const antwoord = await fetch(pad, {...opties, signal:controller.signal});
    toonApplicatieverbinding(true);
    return antwoord;
  } catch (oorzaak) {
    if (bronSignaal?.aborted) throw oorzaak;
    const fout = new Error(verlopen
      ? 'DrostSoundboard reageert niet op tijd. Controleer of de app nog draait. De actie is mogelijk al uitgevoerd.'
      : APP_NIET_BEREIKBAAR);
    fout.foutcode = verlopen ? 'APP-TIMEOUT' : 'APP-OFFLINE';
    fout.cause = oorzaak;
    toonApplicatieverbinding(false);
    // Geen automatische herhaling van schrijfverzoeken: dat kan dubbel afspelen.
    throw fout;
  } finally {
    clearTimeout(timer);
    bronSignaal?.removeEventListener('abort', afbreken);
  }
}

function maakAntwoordfout(inhoud, httpstatus) {
  const code = inhoud?.oorzaakcode || inhoud?.foutcode || null;
  let tekst = inhoud?.fout;
  if (code === 'WEB-022') {
    tekst = PAGINA_VERNIEUWEN;
    toonApplicatieverbinding(true, true);
  } else if (httpstatus === 404) {
    tekst = tekst || 'Dit onderdeel is niet meer beschikbaar. Vernieuw de pagina.';
  } else if (httpstatus === 429) {
    tekst = 'Er lopen te veel aanvragen tegelijk. Probeer het zo opnieuw.';
  } else if (httpstatus >= 500 && (!tekst || /traceback|software\.jsonl|Python/i.test(tekst))) {
    tekst = 'Deze actie is niet gelukt. Probeer het opnieuw. Blijft dit gebeuren, bekijk dan het logboek.';
  }
  tekst = (tekst || 'Deze actie is niet gelukt. Controleer je invoer en probeer het opnieuw.')
    .replace(/^[A-Z][A-Z0-9_-]*-\d{3}:\s*/, '');
  const referentie = httpstatus >= 500 && /^[a-f0-9]{8,32}$/i.test(inhoud?.referentie || '')
    ? ` Referentie: ${inhoud.referentie}.` : '';
  const fout = new Error(tekst + referentie);
  fout.foutcode = code;
  fout.logreferentie = inhoud?.referentie || null;
  return fout;
}


// Afsluiten hoort bij de app, niet bij het sluiten van een browsertab.
async function laadAppAfsluitmogelijkheid() {
  const knop = element('knop-app-afsluiten');
  if (!knop) return;
  try {
    const gegevens = await vraagAanPython('GET', '/api/app');
    knop.hidden = !gegevens.afsluiten_ondersteund;
    if (gegevens.wordt_afgesloten) rondBrowserAfsluitingAf();
  } catch (_) {
    // Een oude of afwezige server heeft geen bevestigde afsluitroute.
    knop.hidden = true;
  }
}

function rondBrowserAfsluitingAf() {
  if (appAfsluitingAangevraagd) return;
  appAfsluitingAangevraagd = true;
  toestand.afspeelVolgnummer++;
  toestand.golfvormVolgnummer++;
  clearInterval(statusTimer);
  clearInterval(recentTimer);
  stopDeDirecteNiveaustroom();
  stopPreview('app_afsluiten');
  stopEditorPreview('app_afsluiten');
  document.querySelectorAll('audio, video').forEach((media) => media.pause());
  previewAudioContext?.suspend().catch(() => {});
  const knop = element('knop-app-afsluiten');
  if (knop) { knop.disabled = true; knop.textContent = 'Afsluiten aangevraagd'; }
  const balk = element('app-verbinding-melding');
  if (balk) balk.hidden = false;
  const tekst = element('app-verbinding-tekst');
  if (tekst) tekst.textContent = 'Afsluiten is aangevraagd. DrostSoundboard stopt de audio en achtergrondtaken. Je kunt deze pagina sluiten.';
  const chip = element('kleine-status')?.querySelector('span');
  if (chip) chip.textContent = ' App wordt afgesloten';
  element('kleine-status')?.classList.remove('actief');
}

async function sluitApplicatieVanuitDashboard() {
  if (appAfsluitenBezig || appAfsluitingAangevraagd) return;
  if (!window.confirm('DrostSoundboard helemaal afsluiten? De microfoon en alle geluiden stoppen. Niet-opgeslagen editorwijzigingen gaan verloren.')) return;
  appAfsluitenBezig = true;
  const knop = element('knop-app-afsluiten');
  if (knop) knop.disabled = true;
  try {
    await vraagAanPython('POST', '/api/app/afsluiten', {bevestiging:'AFSLUITEN'});
    rondBrowserAfsluitingAf();
  } catch (fout) {
    // Een weggevallen antwoord is geen bewijs dat alle onderdelen zijn gestopt.
    toonMelding('Afsluiten kon niet worden bevestigd. Controleer het systeemvak en sluit de app daar af.', true);
    if (knop) knop.disabled = false;
  } finally { appAfsluitenBezig = false; }
}

function koppelAppAfsluiten() {
  element('knop-app-afsluiten')?.addEventListener('click', sluitApplicatieVanuitDashboard);
}

function toonStemverwerkingsfout(status) {
  let melding = element('stemverwerking-fout');
  if (!melding) {
    melding = maakElement('p', 'status-uitleg');
    melding.id = 'stemverwerking-fout';
    melding.setAttribute('role', 'alert');
    element('extra-status')?.insertAdjacentElement('afterend', melding);
  }
  melding.hidden = !status.stemvervorming_geblokkeerd;
  melding.textContent = status.stemvervorming_geblokkeerd
    ? 'De stemverwerking werkt niet. Je microfoon is gedempt; soundboardgeluiden blijven werken. Kies een ander stemprofiel of verbind opnieuw.' : '';
}

function leesbareBrowsermelding(tekst) {
  const melding = String(tekst || 'Deze actie is niet gelukt. Probeer het opnieuw.');
  if (/Failed to fetch|NetworkError when attempting to fetch resource|Load failed/i.test(melding)) return APP_NIET_BEREIKBAAR;
  if (/NotAllowedError|play\(\) failed because the user|user didn't interact/i.test(melding))
    return 'De browser heeft afspelen geblokkeerd. Klik opnieuw op Preview en controleer de geluidsrechten van deze pagina.';
  if (/NotSupportedError|no supported source|unsupported source/i.test(melding))
    return 'De browser kan dit bestand niet afspelen. Probeer Uitzenden of importeer een MP3 of WAV.';
  return melding;
}

async function vraagAanPython(methode, pad, gegevens = undefined, bestand = undefined) {
  const koppen = {};
  const opties = { method: methode, headers: koppen, cache: "no-store" };
  if (methode !== "GET" || pad.includes("/preview-normalisatie")) koppen["X-Drost-Token"] = beveiligingscode;
  if (bestand) {
    koppen["X-Bestandsnaam"] = encodeURIComponent(bestand.name);
    koppen["Content-Type"] = "application/octet-stream";
    opties.body = bestand;
  } else if (methode === "POST") {
    koppen["Content-Type"] = "application/json";
    opties.body = JSON.stringify(gegevens ?? {});
  }
  const antwoord = await haalBijApplicatie(pad, opties);
  let inhoud;
  try { inhoud = await antwoord.json(); }
  catch { throw maakAntwoordfout({}, antwoord.status >= 400 ? antwoord.status : 500); }
  if (!antwoord.ok) throw maakAntwoordfout(inhoud, antwoord.status);
  return inhoud;
}

function toonMelding(tekst, fout = false) {
  tekst = leesbareBrowsermelding(tekst);
  // Niet elke sleepstap of statuscontrole een nieuwe identieke foutmelding.
  const bestaand = [...element('meldingen').children].some(vak => vak.textContent === tekst);
  if (bestaand) return;
  while (element('meldingen').children.length >= 3) element('meldingen').firstElementChild.remove();
  const melding = maakElement("div", `melding${fout ? " fout" : ""}`, tekst);
  element("meldingen").appendChild(melding);
  setTimeout(() => melding.remove(), 6500);
}

// 5.9.2: Een instelling aanwijzen zonder de gebruiker uit zijn context te trekken.
// De foutmelding blijft leesbaar; een korte rode rand wijst naar de oplossing.
const timersVoorInstellingen = new WeakMap();
function wijsBenodigdeInstellingAan(knopId) {
  const knop = element(knopId);
  if (!knop) return;
  const doel = knopId === "knop-effecten"
    ? knop.closest(".effectenbediening") || knop
    : knop;
  clearTimeout(timersVoorInstellingen.get(doel));
  doel.classList.remove("instelling-nodig");
  // CSS herstart de zachte highlight ook bij een tweede foutmelding.
  void doel.offsetWidth;
  doel.classList.add("instelling-nodig");
  const rustigBewegen = !window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  doel.scrollIntoView({ behavior: rustigBewegen ? "smooth" : "instant", block: "center", inline: "nearest" });
  // De knop krijgt toetsenbordfocus maar scrollt niet nóg een keer.
  if (!knop.disabled) knop.focus({ preventScroll: true });
  timersVoorInstellingen.set(doel, setTimeout(() => {
    doel.classList.remove("instelling-nodig");
  }, 3400));
}

function wijsBijInstelfoutDeOplossingAan(bericht) {
  const tekst = String(bericht || "").toLowerCase();
  if (tekst.includes("soundboard eerst aan") || tekst.includes("geluidseffecten eerst aan")) {
    wijsBenodigdeInstellingAan("knop-effecten");
  } else if (tekst.includes("eerst op verbinden") || tekst.includes("niet verbonden")) {
    wijsBenodigdeInstellingAan("knop-verbinden");
  } else if (tekst.includes("geen microfoon") || tekst.includes("kies een microfoon")) {
    wijsBenodigdeInstellingAan("microfoonkeuze");
  }
}

// 6.0 Beta 5.1: een aparte instellingenpagina, zonder de audioverbinding te herstarten.
// De hash maakt browser Terug/Vooruit mogelijk, zonder tweede server of audiomixer.
function toonGekozenPagina() {
  sluitFavorietActiemenu();
  const pagina = window.location.hash;
  const instellingen = pagina === '#instellingen' || pagina === '#instellingen-stem';
  const bibliotheek = pagina === '#bibliotheek';
  if (!instellingen && toestand.stemvoorbeeldActief) {
    stopLokaleStempreview({ stil: true }).catch((fout) =>
      registreerBrowserfout(`Stempreview stoppen: ${fout.message}`, fout.stack || ''));
  }
  element('dashboard').hidden = instellingen || bibliotheek;
  element('instellingen-pagina').hidden = !instellingen;
  element('bibliotheek-pagina').hidden = !bibliotheek;
  // De navigatie blijft op iedere pagina op dezelfde plek staan.
  for (const [id, actief] of [
    ['knop-dashboard-pagina', !instellingen && !bibliotheek],
    ['knop-bibliotheek-pagina', bibliotheek],
    ['knop-instellingen', instellingen]
  ]) {
    const knop = element(id);
    knop.classList.toggle('huidige-pagina', actief);
    if (actief) knop.setAttribute('aria-current', 'page');
    else knop.removeAttribute('aria-current');
  }
  if (bibliotheek) {
    maakGroteBibliotheekZichtbaar();
    // Focus pas na het renderen, geen modal/top-layer meer.
    element('beheer-bibliotheek-titel').focus({preventScroll:true});
  }
  document.title = instellingen ? 'Instellingen | DrostSoundboard'
    : bibliotheek ? 'Bibliotheek | DrostSoundboard' : 'DrostSoundboard';
  if (pagina === '#instellingen-stem') {
    element('stemprofiel-titel').scrollIntoView({block:'start', behavior:'smooth'});
  }
}

function koppelPaginanavigatie() {
  window.addEventListener("hashchange", toonGekozenPagina);
  toonGekozenPagina();
}

// Eén verbindingsknop, waarvan de actie en de tekst de werkelijke audiostatus volgen.
function werkVerbindingsknopBij(status) {
  const knop = element("knop-verbinden");
  const toestandnaam = status?.toestand || "verbroken";
  const verbonden = toestandnaam === "verbonden";
  const bezig = ["wordt_verbonden", "wordt_verbroken"].includes(toestandnaam);
  const tekst = toestandnaam === "wordt_verbonden" ? "Verbinden..."
    : toestandnaam === "wordt_verbroken" ? "Verbreken..."
    : verbonden ? "Verbreken" : "Verbinden";
  element("verbindingsknop-tekst").textContent = tekst;
  knop.setAttribute("aria-label", verbonden ? "Microfoonverbinding verbreken" : "Microfoon verbinden");
  knop.classList.toggle("knop-primair", !verbonden);
  knop.classList.toggle("knop-ghost", verbonden);
  knop.classList.toggle("verbinding-actief", verbonden);
  knop.disabled = toestand.verbindingInBehandeling || bezig || (!verbonden && !element("microfoonkeuze").value);
}

function registreerBrowserfout(melding, stapel = "") {
  if (applicatieVerbinding.bereikbaar === false || applicatieVerbinding.nieuweSessie) return;
  // JS heeft geen Python traceback. Schrijf de browserstack naar dezelfde
  // softwarelogging zodat een fout later alsnog terug te vinden is.
  vraagAanPython("POST", "/api/frontendfout", {
    melding: String(melding).slice(0, 1000), stapel: String(stapel).slice(0, 8000)
  }).catch(() => {});
}
// Alleen dubbele, gelijktijdige verzoeken voor dezelfde schakelaar
// negeren. Andere acties, vooral Stop, mogen direct blijven werken.
const actiesZonderDubbeleAanvraag = new Set([
  "Verbinden", "Verbreken", "Microfoonverbinding wijzigen", "Soundboard schakelen", "Meeluisteren instellen",
  "Luisterapparaat aanpassen", "Geluid stoppen", "Bibliotheek-ZIP importeren",
  "Los bestand exporteren"
]);
const actiesDieNogBezigZijn = new Set();
async function voerGebruikersactieUit(naam, actie) {
  const voorkomDubbel = actiesZonderDubbeleAanvraag.has(naam);
  if (voorkomDubbel && actiesDieNogBezigZijn.has(naam)) return;
  if (voorkomDubbel) actiesDieNogBezigZijn.add(naam);
  try { await actie(); }
  catch (fout) {
    console.error(naam, fout);
    registreerBrowserfout(`${naam}: ${fout.message}`, fout.stack || "");
    toonMelding(`${naam}: ${fout.message}`, true);
    wijsBijInstelfoutDeOplossingAan(fout.message);
  } finally {
    if (voorkomDubbel) actiesDieNogBezigZijn.delete(naam);
  }
}
window.addEventListener("error", (gebeurtenis) => {
  registreerBrowserfout(gebeurtenis.message || "Onbekende JavaScript-fout", gebeurtenis.error?.stack || "");
});
window.addEventListener("unhandledrejection", (gebeurtenis) => {
  registreerBrowserfout(`Afgewezen belofte: ${gebeurtenis.reason?.message || String(gebeurtenis.reason)}`, gebeurtenis.reason?.stack || "");
});

function vindGeluid(id) {
  return toestand.geluiden.find((geluid) => geluid.id === id);
}

function netteTijd(seconden) {
  if (seconden === null || seconden === undefined || !Number.isFinite(Number(seconden))) return "—:—";
  const n = Math.max(0, Math.floor(Number(seconden) || 0));
  return `${Math.floor(n / 60)}:${String(n % 60).padStart(2, "0")}`;
}

function speelicoon() {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  const pad = document.createElementNS("http://www.w3.org/2000/svg", "path");
  pad.setAttribute("d", "M10 5 5 9H2v6h3l5 4V5Zm4 4a4 4 0 0 1 0 6m3-9a8 8 0 0 1 0 12");
  pad.setAttribute("stroke-linecap", "round");
  pad.setAttribute("stroke-linejoin", "round");
  svg.appendChild(pad);
  return svg;
}

function geefStatischeAfbeelding(geluid) {
  // Een GIF tonen we bewust niet in rust. Die hoort pas te bewegen tijdens audio.
  return geluid?.miniatuur ||
    (geluid?.afbeelding && !geluid.afbeelding.toLowerCase().includes(".gif")
      ? geluid.afbeelding : null);
}

function maakAfbeelding(bron, klasse = "") {
  const plaatje = maakElement("img", klasse);
  plaatje.src = bron;
  plaatje.loading = "lazy";
  plaatje.alt = "";
  return plaatje;
}

async function laadBibliotheekOpnieuw() {
  const gegevens = await vraagAanPython("GET", "/api/bibliotheek");
  toestand.geluiden = gegevens.geluiden || [];
  toestand.favorieten = gegevens.favorieten || Array(15).fill(null);
  toestand.groepen = gegevens.groepen || [];
  if (toestand.actieveGroep !== "alle" && toestand.actieveGroep !== "zonder" &&
      !toestand.groepen.some((groep) => groep.id === toestand.actieveGroep)) toestand.actieveGroep = "alle";
  maakGroepenZichtbaar();
  maakFavorietenZichtbaar();
  maakBibliotheekZichtbaar();
  tekenRecenteOverzicht();
  element("bibliotheek-aantal").textContent = String(toestand.geluiden.length);
  element("aantal-favorieten").textContent =
    `${toestand.favorieten.filter(Boolean).length} van 15 ingevuld`;
  if (!element("bibliotheek-pagina").hidden) maakGroteBibliotheekZichtbaar();
}

function maakFavorietenZichtbaar() {
  const raster = element("favorieten-raster");
  raster.replaceChildren();
  for (let plek = 1; plek <= 15; plek++) {
    const id = toestand.favorieten[plek - 1];
    const geluid = id ? vindGeluid(id) : null;
    const kaart = maakElement("div", `favoriet ${geluid ? `favoriet-kleur-${(plek % 5) + 1}` : "ongevuld"}`);
    if (geluid) kaart.dataset.geluidId = geluid.id;
    kaart.setAttribute("role", "button");
    kaart.tabIndex = 0;
    kaart.ariaLabel = geluid ? `Speel ${geluid.naam}` : `Vul favoriet ${plek} in`;
    kaart.draggable = Boolean(geluid);
    kaart.addEventListener("click", () => geluid ? beginGeluidAfspelen(geluid.id) : openFavorietKiezer(plek));
    kaart.addEventListener("keydown", (gebeurtenis) => {
      if (gebeurtenis.target === kaart && ["Enter", " "].includes(gebeurtenis.key)) {
        gebeurtenis.preventDefault(); kaart.click();
      }
    });
    if (geluid) kaart.addEventListener("dragstart", (gebeurtenis) => {
      gebeurtenis.dataTransfer.effectAllowed = "move";
      gebeurtenis.dataTransfer.setData("text/plain", JSON.stringify({ soort: "favoriet", plek }));
    });
    kaart.addEventListener("dragover", (gebeurtenis) => { gebeurtenis.preventDefault(); kaart.classList.add("drag-over"); });
    kaart.addEventListener("dragleave", () => kaart.classList.remove("drag-over"));
    kaart.addEventListener("drop", (gebeurtenis) => {
      gebeurtenis.preventDefault(); kaart.classList.remove("drag-over");
      voerGebruikersactieUit("Favoriet verplaatsen", async () => {
        const bron = JSON.parse(gebeurtenis.dataTransfer.getData("text/plain"));
        if (bron.soort === "favoriet") {
          await vraagAanPython("POST", "/api/favorieten/wissel", { eerste: bron.plek, tweede: plek });
        } else if (bron.soort === "bibliotheek") {
          await vraagAanPython("POST", `/api/favorieten/${plek}`, { geluid_id: bron.id });
        } else return;
        await laadBibliotheekOpnieuw();
      });
    });
    const plaatje = geefStatischeAfbeelding(geluid);
    if (plaatje) kaart.appendChild(maakAfbeelding(plaatje, "favoriet-afbeelding"));
    const boven = maakElement("div", "favoriet-boven");
    boven.appendChild(maakElement("span", "vaknummer", String(plek).padStart(2, "0")));
    if (geluid) {
      const aanpassen = maakElement("button", "bewerk-vak", "…");
      aanpassen.type = "button";
      aanpassen.title = `Acties voor favoriet ${plek}`;
      aanpassen.setAttribute("aria-haspopup", "menu");
      aanpassen.addEventListener("click", (e) => { e.stopPropagation(); toonFavorietActiemenu(plek, geluid, aanpassen); });
      boven.appendChild(aanpassen);
    }
    kaart.appendChild(boven);
    const icoon = maakElement("div", "favoriet-icoon");
    if (geluid) icoon.appendChild(speelicoon());
    else icoon.appendChild(maakElement("span", "", "+"));
    kaart.appendChild(icoon);
    const voet = maakElement("div", "favoriet-voet");
    voet.appendChild(maakElement("div", "favoriet-naam", geluid?.naam || "Geluid toevoegen"));
    voet.appendChild(maakElement("div", "favoriet-type", geluid
      ? `${geluid.formaat.toUpperCase()}, duur ${netteTijd(geluid.fragmentduur)} ` : "Klik om te kiezen"));
    if (geluid) {
      const acties = maakElement("div", "favoriet-acties");
      const preview = maakElement("button", "favoriet-luister", "◉  Preview");
      preview.type = "button";
      preview.title = "Alleen zelf luisteren, niet naar VB-CABLE";
      preview.addEventListener("click", (e) => { e.stopPropagation(); beginPreview(geluid.id); });
      acties.appendChild(preview);
      voet.appendChild(acties);
    }
    kaart.appendChild(voet);
    raster.appendChild(kaart);
  }
  werkActieveKaartenBij();
}

function werkActieveKaartenBij() {
  document.querySelectorAll(".favoriet[data-geluid-id]").forEach((kaart) => {
    kaart.classList.toggle("actief", toestand.live?.geluidId === kaart.dataset.geluidId);
    kaart.classList.toggle("preview-bezig", toestand.preview?.geluidId === kaart.dataset.geluidId);
  });
  werkPreviewEnStopknoppenBij();
}

function wordtGeluidMomenteelAfgespeeld(geluidId) {
  return toestand.preview?.geluidId === geluidId ||
    toestand.live?.geluidId === geluidId ||
    toestand.verwachtGeluid?.id === geluidId;
}

/*
  Eén en dezelfde knop toont Preview of een rode Stop-knop. We veranderen
  alleen de knop, niet de hele bibliotheeklijst, om scrollen en slepen
  tijdens een preview soepel te houden.
*/
function werkPreviewEnStopknoppenBij() {
  if (element('dialoog-bewerken')?.open && toestand.gekozenGeluid) {
    const actief = toestand.editorUitzendGeluidId === toestand.gekozenGeluid &&
      (toestand.live?.geluidId === toestand.gekozenGeluid ||
       toestand.verwachtGeluid?.id === toestand.gekozenGeluid ||
       toestand.status?.huidig_geluid_id === toestand.gekozenGeluid);
    if (toestand.editorUitzendGeluidId && !actief && !toestand.editorVoorbeeld) {
      toestand.editorUitzendGeluidId = null;
    }
    const knop = element('knop-editor-uitzenden');
    knop.setAttribute('aria-pressed', String(Boolean(actief)));
    element('knop-editor-stop').disabled = !actief && !toestand.editorVoorbeeld;
  }
  document.querySelectorAll(".lijst-previewknop[data-geluid-id]").forEach((knop) => {
    const bezig = toestand.preview?.geluidId === knop.dataset.geluidId;
    knop.textContent = bezig ? "Stop" : "Preview";
    knop.classList.toggle("preview-stop-actief", bezig);
    knop.setAttribute("aria-label", bezig
      ? "Lokale preview stoppen" : "Dit volledige ingestelde fragment lokaal beluisteren");
    knop.setAttribute("aria-pressed", String(bezig));
  });
  document.querySelectorAll('.lijst-uitzendknop[data-geluid-id]').forEach((knop) => {
    const id = knop.dataset.geluidId;
    const bezig = toestand.live?.geluidId === id || toestand.verwachtGeluid?.id === id;
    knop.textContent = bezig ? 'Stop' : 'Uitzenden';
    knop.classList.toggle('uitzend-stop-actief', bezig);
    knop.setAttribute('aria-pressed', String(bezig));
    knop.setAttribute('aria-label', bezig ? 'Uitzending stoppen' : 'Geluid naar virtuele microfoon sturen');
  });
}

function schakelPreviewOfStopVanGeluid(geluidId) {
  if (toestand.preview?.geluidId === geluidId) {
    stopPreview("stop_vanuit_bibliotheek");
  } else {
    // Een preview vervangt ook een lopende uitzending, nooit beide tegelijk.
    beginPreview(geluidId);
  }
}


// Uitzenden en Preview zijn even gemakkelijk bereikbaar, in zowel de
// compacte zijbalk als de volledige bibliotheek. De bestaande spelerwachtrij
// voorkomt dat een oudere aanvraag een nieuw geluid weer overschrijft.
function maakUitzendknopVoorGeluid(geluid) {
  const knop = maakElement('button', 'lijst-uitzendknop', 'Uitzenden');
  knop.type = 'button';
  knop.dataset.geluidId = geluid.id;
  knop.title = `Speel ${geluid.naam} af via de virtuele microfoon`;
  knop.setAttribute('aria-label', `${geluid.naam} uitzenden via de virtuele microfoon`);
  knop.addEventListener('click', () => {
    const id = geluid.id;
    if (toestand.live?.geluidId === id || toestand.verwachtGeluid?.id === id) {
      element('knop-stop').click();
    } else {
      beginGeluidAfspelen(id);
    }
  });
  return knop;
}

function maakBibliotheekZichtbaar({ behoudPositie = false } = {}) {
  sluitGeluidActiemenu();
  const lijst = element("bibliotheek-lijst");
  // Een automatische geschiedenisupdate mag de bibliotheek niet naar boven zetten.
  // Handmatig zoeken, filteren en sorteren begint wel bewust bovenaan de lijst.
  const vorigeScrollpositie = behoudPositie ? lijst.scrollTop : 0;
  lijst.replaceChildren();
  const zoeken = element("zoeken").value.trim().toLocaleLowerCase("nl-NL");
  const recenteIds = new Set((recenteGegevens.geluiden || []).filter(g => g.bestaat_nog).map(g => g.id));
  const gevonden = toestand.geluiden.filter((geluid) => {
    if (dashboardAfspeelFilter === "recent" && !recenteIds.has(geluid.id)) return false;
    const kloptGroep = (zoeken && element("bibliotheek-zoek-alle").checked) || toestand.actieveGroep === "alle" ||
      (toestand.actieveGroep === "zonder" ? !(geluid.groep_ids || []).length :
        hoortBijGroep(geluid,toestand.actieveGroep));
    return kloptGroep && pastBijZoekopdracht(geluid, zoeken);
  });
  sorteerGeluiden(gevonden,element('bibliotheek-sortering').value);
  const groepsnaam = toestand.actieveGroep === 'alle' ? 'alle mappen'
    : toestand.actieveGroep === 'zonder' ? 'zonder map'
    : (toestand.groepen.find(groep => groep.id === toestand.actieveGroep)?.naam || 'gekozen map');
  const bereik = dashboardAfspeelFilter === 'recent' ? 'recent gebruikt'
    : zoeken && element('bibliotheek-zoek-alle').checked ? 'alle mappen' : groepsnaam;
  element('bibliotheek-resultaten').textContent = `${gevonden.length} gevonden in ${bereik}.`;
  element('knop-zoek-wissen').disabled = !zoeken;
  tekenDashboardSnelFilters();
  if (!gevonden.length) {
    lijst.appendChild(maakElement("p", "lege-lijst", toestand.geluiden.length
      ? "Geen geluiden gevonden." : "Nog geen geluiden. Voeg je eerste MP3, WAV of MP4 toe."));
    lijst.scrollTop = 0;
    return;
  }
  for (const geluid of gevonden.slice(0, toestand.bibliotheekZichtbaarAantal)) {
    const kaart = maakElement("div", "bibliotheek-item");
    kaart.dataset.geluidId = geluid.id;
    kaart.draggable = true;
    kaart.addEventListener("dragstart", (gebeurtenis) => {
      sluitGeluidActiemenu();
      gebeurtenis.dataTransfer.effectAllowed = "copyMove";
      gebeurtenis.dataTransfer.setData("text/plain", JSON.stringify({ soort: "bibliotheek", id: geluid.id }));
    });
    const kunst = maakElement("div", "bibliotheek-kunst");
    const plaatje = geefStatischeAfbeelding(geluid);
    if (plaatje) kunst.appendChild(maakAfbeelding(plaatje));
    else kunst.appendChild(speelicoon());
    const tekst = maakElement("div", "bibliotheek-naam");
    tekst.appendChild(maakElement("strong", "", geluid.naam));
    tekst.appendChild(maakElement("small", "", `${geluid.formaat.toUpperCase()}, ${geluid.fragmentduur === null ? "duur onbekend" : `duur ${netteTijd(geluid.fragmentduur)}`}${geluid.bestand_gevonden ? "" : ", bestand ontbreekt"}`));
    const luisteren = maakPreviewknopVoorGeluid(geluid);
    const uitzenden = maakUitzendknopVoorGeluid(geluid);
    const meer = maakElement("button", "icoonknop bibliotheek-acties-knop", "…");
    meer.type = "button";
    meer.setAttribute("aria-label", `Meer acties voor ${geluid.naam}`);
    meer.setAttribute("aria-haspopup", "menu");
    meer.setAttribute("aria-expanded", "false");
    meer.addEventListener("click", (gebeurtenis) => {
      gebeurtenis.stopPropagation();
      toonGeluidActiemenu(geluid.id, meer);
    });
    const acties = maakElement('div', 'bibliotheek-speelacties');
    acties.append(luisteren, uitzenden);
    tekst.title = geluid.naam;
    kaart.append(kunst, tekst, acties, meer);
    kaart.addEventListener("dblclick", (gebeurtenis) => {
      // Dubbelklikken op een actieknop mag niet alsnog audio naar een call sturen.
      if (!gebeurtenis.target.closest("button")) beginGeluidAfspelen(geluid.id);
    });
    lijst.appendChild(kaart);
  }
  if (gevonden.length > toestand.bibliotheekZichtbaarAantal) {
    const verder = maakElement("button", "knop knop-ghost bibliotheek-meer", `Meer geluiden (${gevonden.length - toestand.bibliotheekZichtbaarAantal})`);
    verder.type = "button";
    verder.addEventListener("click", () => {
      toestand.bibliotheekZichtbaarAantal += 60;
      maakBibliotheekZichtbaar({ behoudPositie: true });
    });
    lijst.appendChild(verder);
  }
  werkPreviewEnStopknoppenBij();
  lijst.scrollTop = behoudPositie ? vorigeScrollpositie : 0;
}

function maakPreviewknopVoorGeluid(geluid) {
  const knop = maakElement("button", "lijst-previewknop", "Preview");
  knop.type = "button";
  knop.dataset.geluidId = geluid.id;
  knop.title = `Beluister ${geluid.naam} lokaal; klik tijdens afspelen op Stop`;
  knop.addEventListener("click", () => schakelPreviewOfStopVanGeluid(geluid.id));
  return knop;
}

/*
  Er bestaat maar één actiemenu in de hele app. Zo blijven de drie puntjes
  snel, ook met honderden geluiden. Het menu staat buiten het scrollpaneel
  zodat de laatste rij niet door overflow wordt afgesneden.
*/
let geopendeActieknop = null;
function sluitGeluidActiemenu() {
  const menu = element("geluid-actiemenu");
  if (!menu) return;
  menu.hidden = true;
  menu.replaceChildren();
  if (geopendeActieknop) geopendeActieknop.setAttribute("aria-expanded", "false");
  geopendeActieknop = null;
}

function voegActieToeAanMenu(menu, tekst, actie, extraKlasse = "") {
  const knop = maakElement("button", `geluid-menu-actie ${extraKlasse}`, tekst);
  knop.type = "button";
  knop.setAttribute("role", "menuitem");
  knop.addEventListener("click", (gebeurtenis) => {
    gebeurtenis.stopPropagation();
    sluitGeluidActiemenu();
    actie();
  });
  menu.appendChild(knop);
  return knop;
}

function plaatsGeluidActiemenuBijKnop(menu, knop) {
  // Geen dialog-toplaag meer: plaats één actiemenu relatief aan het venster.
  document.body.appendChild(menu);
  menu.hidden = false;
  const positie = knop.getBoundingClientRect();
  const breedte = menu.offsetWidth || 220;
  const hoogte = menu.offsetHeight || 260;
  const links = Math.max(10, Math.min(window.innerWidth - breedte - 10, positie.right - breedte));
  const boven = positie.bottom + hoogte > window.innerHeight - 12
    ? Math.max(8, positie.top - hoogte - 8) : positie.bottom + 8;
  menu.style.left = `${links}px`;
  menu.style.top = `${boven}px`;
}

function toonGeluidActiemenu(geluidId, knop) {
  const geluid = vindGeluid(geluidId);
  if (!geluid) return;
  if (geopendeActieknop === knop) { sluitGeluidActiemenu(); return; }
  sluitGeluidActiemenu();
  geopendeActieknop = knop;
  knop.setAttribute("aria-expanded", "true");
  const menu = element("geluid-actiemenu");
  menu.appendChild(maakElement("div", "geluid-menu-titel", geluid.naam));
  voegActieToeAanMenu(menu, "Bewerken", () => {
    if (!element("bibliotheek-pagina").hidden) openEditorVanuitBeheer(geluidId);
    else openBewerkvenster(geluidId);
  }, "menu-bewerken");
  voegActieToeAanMenu(menu, "Uitzenden via microfoon", () => beginGeluidAfspelen(geluidId));
  voegActieToeAanMenu(menu, "Preview", () => schakelPreviewOfStopVanGeluid(geluidId));
  const formaten = Array.isArray(geluid.exportformaten) ? geluid.exportformaten : [];
  if (formaten.length) {
    menu.appendChild(maakElement("div", "geluid-menu-tussenkop", "Download"));
    for (const formaat of ["mp3", "mp4", "afbeelding", "gif"]) {
      if (!formaten.includes(formaat)) continue;
      const label = { mp3: "MP3-audio", mp4: "MP4-video met audio",
        afbeelding: "Afbeelding", gif: "GIF-animatie" }[formaat];
      voegActieToeAanMenu(menu, label, () => {
        // Geen modal nodig bij één rechtstreekse export. De server controleert
        // het formaat opnieuw en registreert iedere download in het auditlog.
        openLosseExport(geluidId, false, false);
        voerGebruikersactieUit("Geluid downloaden", async () => {
          await downloadLosBestand(formaat);
          if (element("dialoog-losse-export").open) element("dialoog-losse-export").close();
        });
      });
    }
  }
  plaatsGeluidActiemenuBijKnop(menu, knop);
  menu.querySelector(".menu-bewerken")?.focus();
}

/*
  Het mediavlak wordt gedeeld door de browserpreview en de live-mixer.
  Alleen de browserpreview mag audio maken. Live-video wordt altijd gedempt,
  omdat de echte audio al naar VB-CABLE en de headsetmonitor gaat.
*/
function maakGolfIcoon() {
  const icoon = maakElement("span", "grote-golf");
  for (let i = 0; i < 5; i++) icoon.appendChild(maakElement("i"));
  return icoon;
}

function toonMediascherm(geluid, voorbeeld, beginpositie = 0, bestaandPreviewmedium = null) {
  const scherm = element("actieve-media");
  scherm.replaceChildren();
  if (geluid.is_video && geluid.mediabron && (geluid.beeldvoorkeur !== "afbeelding" || !geluid.afbeelding)) {
    if (voorbeeld) {
      // Geen tweede video aanmaken: de previewspeler IS het schermmedium.
      // Een dubbele bron zou twee netwerkstreams en een korte beginflits geven.
      if (!bestaandPreviewmedium) throw new Error("VIDEO-005: previewmedium ontbreekt.");
      // Het oude bestandsposter blijft zichtbaar zolang de browser zoekt.
      // Zo verschijnt niet eerst frame 0 wanneer de selectie later begint.
      const stilstaandBeeld = geefStatischeAfbeelding(geluid);
      if (stilstaandBeeld) scherm.appendChild(maakAfbeelding(stilstaandBeeld));
      bestaandPreviewmedium.style.display = "block";
      bestaandPreviewmedium.style.objectFit = 'cover';
      bestaandPreviewmedium.style.objectPosition = 'center';
      bestaandPreviewmedium.classList.add("video-preview-wacht");
      scherm.appendChild(bestaandPreviewmedium);
      return null;
    }
    const controller = window.DrostVideoSynchronisatie.maakLiveVideospeler({
      bron: geluid.mediabron,
      stilstaandBeeld: geefStatischeAfbeelding(geluid),
      beginpositie,
      bijFout: (fout) => {
        registreerBrowserfout(`Video van ${geluid.naam}: ${fout.message}`, fout.stack || "");
        element("huidige-uitleg").textContent = "Het videobeeld kon niet worden getoond. De audio blijft actief.";
      }
    });
    scherm.appendChild(controller.element);
    return controller;
  }
  if (geluid.afbeelding) {
    // Opnieuw een nieuw img-element maken herstart de gekoppelde GIF.
    const afbeelding = maakAfbeelding(geluid.afbeelding);
    afbeelding.loading = "eager";
    scherm.appendChild(afbeelding);
    return null;
  }
  const fallback = maakElement("div", "player-placeholder");
  fallback.appendChild(maakGolfIcoon());
  fallback.appendChild(maakElement("small", "", "GELUID WORDT AFGESPEELD"));
  scherm.appendChild(fallback);
  return null;
}

/*
  Tijdens het decoderen alleen een stilstaand voorbeeld tonen.
  Het LIVE-video-element verschijnt pas zodra Python écht audio afspeelt.
  Anders zou hetzelfde MP4 tweemaal starten en terugschieten naar het begin.
*/
function toonVoorbereidingZonderVideo(geluid) {
  const scherm = element("actieve-media");
  scherm.replaceChildren();
  const foto = geefStatischeAfbeelding(geluid);
  if (foto) scherm.appendChild(maakAfbeelding(foto));
  else {
    const wachtbeeld = maakElement("div", "player-placeholder");
    wachtbeeld.appendChild(maakGolfIcoon());
    scherm.appendChild(wachtbeeld);
  }
}

function stelSpelerActiefIn(actief) {
  // De knoppen zijn pas bruikbaar als er echt iets afspeelt of wordt voorbereid.
  // Dit geldt voor zowel lokale previews als geluid naar het gesprek.
  element("speler-paneel").classList.toggle("speler-inactief", !actief);
  element("knop-stop").disabled = !actief;
  werkOpnieuwKnopBij();
}

function toonStilMediascherm() {
  const scherm = element("actieve-media");
  scherm.replaceChildren();
  const basis = maakElement("div", "player-placeholder");
  basis.appendChild(maakGolfIcoon());
  basis.appendChild(maakElement("small", "", "GEEN FRAGMENT ACTIEF"));
  scherm.appendChild(basis);
  const laatst = toestand.laatsteAfspeelkeuze;
  const geluid = laatst ? vindGeluid(laatst.geluidId) : null;
  element("nu-actief-titel").textContent = geluid ? geluid.naam : "Nog niets actief";
  element("huidige-uitleg").textContent = geluid
    ? `Gestopt. Opnieuw afspelen start dit fragment ${laatst.modus === 'live' ? 'via de virtuele microfoon' : 'alleen lokaal'}.`
    : "Kies een geluid om af te spelen.";
  element("huidige-afspeelstand").textContent = "SPELER";
  element("speler-meta").hidden = false;
  element("speler-volume-regelaar").hidden = false;
  element("knop-preview-herhaal").hidden = false;
  element("knop-preview-herhaal").setAttribute('aria-pressed', String(toestand.previewHerhalen));
  element("knop-preview-herhaal").classList.toggle('gekozen', toestand.previewHerhalen);
  element("tijdlijn-schuif").disabled = true;
  werkSpelerTijdBij(0, 0);
  element("knop-preview-stop").disabled = true;
  stelSpelerActiefIn(false);
}

function werkSpelerTijdBij(verstreken, totaal) {
  const fractie = totaal > 0 ? Math.min(1, Math.max(0, verstreken / totaal)) : 0;
  element("tijdlijn-vulling").style.width = `${fractie * 100}%`;
  element("tijdlijn-tijd").textContent = netteTijd(verstreken);
  element("tijdlijn-totaal").textContent = netteTijd(totaal);
  const zoeken = element("tijdlijn-schuif");
  if (!toestand.preview?.bezigMetZoeken) zoeken.value = String(Math.round(fractie * 1000));
  zoeken.setAttribute("aria-valuetext", `${netteTijd(verstreken)} van ${netteTijd(totaal)}`);
}

// De browserpreview volgt de audioklok van het HTMLMediaElement.
// Hetzelfde element is bij MP4 ook het videobeeld, dus zoeken blijft synchroon.
function zoekInPreview(preview, fractie) {
  if (toestand.preview !== preview || !preview.gestart) return;
  const veiligeFractie = Math.min(1, Math.max(0, Number(fractie) || 0));
  const einde = Number.isFinite(preview.media.duration)
    ? Math.max(preview.start, preview.media.duration - 0.025)
    : preview.start + preview.duur;
  const positie = Math.max(preview.start,
    Math.min(einde, preview.start + veiligeFractie * preview.duur));
  preview.media.currentTime = positie;
  werkSpelerTijdBij(positie - preview.start, preview.duur);
  // GIF-frames zijn niet seekbaar. Alleen bij teruggaan naar het begin herstarten.
  if (positie - preview.start < 0.05 && preview.geluid.afbeelding?.toLowerCase().endsWith(".gif") && !preview.geluid.is_video) {
    toonMediascherm(preview.geluid, true, preview.start);
  }
}

function eindigPreviewFragment(preview) {
  if (toestand.preview !== preview || preview.eindeBezig || !preview.gestart) return;
  if (!toestand.previewHerhalen) {
    stopPreview("klaar");
    return;
  }
  preview.eindeBezig = true;
  zoekInPreview(preview, 0);
  // De seek van hetzelfde audio/video-element voorkomt dubbele audiostreams.
  Promise.resolve(preview.media.play()).then(() => {
    preview.eindeBezig = false;
  }, (fout) => {
    preview.eindeBezig = false;
    stopPreview("browserfout");
    toonMelding(`Herhalen kon niet starten: ${fout.message}`, true);
  });
}

function werkPreviewTijdBij(preview) {
  if (toestand.preview !== preview || !preview.gestart) return;
  const verstreken = Math.max(0, preview.media.currentTime - preview.start);
  if (verstreken >= preview.duur - 0.025 || preview.media.ended) {
    eindigPreviewFragment(preview);
    return;
  }
  if (!preview.bezigMetZoeken) werkSpelerTijdBij(Math.min(verstreken, preview.duur), preview.duur);
}

function animeerPreviewTijd(preview) {
  if (toestand.preview !== preview) return;
  werkPreviewTijdBij(preview);
  if (toestand.preview === preview) {
    preview.animatie = window.requestAnimationFrame(() => animeerPreviewTijd(preview));
  }
}

// Beta 4.10: herstarten is een losse actie, niet de automatische herhaalstand.
function werkOpnieuwKnopBij() {
  const keuze = toestand.laatsteAfspeelkeuze;
  const knop = element('knop-speler-opnieuw');
  knop.disabled = !keuze || !vindGeluid(keuze.geluidId)?.bestand_gevonden ||
    Boolean(toestand.verwachtGeluid || (toestand.preview && !toestand.preview.gestart));
  knop.title = !keuze ? 'Speel eerst een geluid af' :
    `Start het laatste fragment opnieuw ${keuze.modus === 'live' ? 'via de virtuele microfoon' : 'alleen lokaal'}`;
}

function speelOpnieuwAf() {
  const preview = toestand.preview;
  if (preview?.gestart) {
    return voerGebruikersactieUit('Preview opnieuw afspelen', async () => {
      zoekInPreview(preview, 0);
      await preview.media.play();
    });
  }
  const live = toestand.live;
  if (live) {
    return voerGebruikersactieUit('Uitzending opnieuw afspelen', async () => {
      await vraagAanPython('POST', '/api/speler/live', {afspeelbeurt_id: live.afspeelbeurt, positie: 0});
      if (toestand.live !== live) return;
      live.verstreken = 0;
      live.laatstOntvangen = performance.now();
      live.zoekTot = performance.now() + 260;
      werkSpelerTijdBij(0, live.duurt);
    });
  }
  const keuze = toestand.laatsteAfspeelkeuze;
  if (!keuze || !vindGeluid(keuze.geluidId)?.bestand_gevonden) return;
  return keuze.modus === 'live'
    ? beginGeluidAfspelen(keuze.geluidId, keuze.tijdelijkeSelectie)
    : beginPreview(keuze.geluidId);
}

let herhaalWachtrij = Promise.resolve();
function toonHerhaalstand(aan) {
  const knop = element('knop-preview-herhaal');
  knop.hidden = false;
  knop.setAttribute('aria-pressed', String(aan));
  knop.classList.toggle('gekozen', aan);
}

function stelHerhalenIn(aan) {
  toestand.previewHerhalen = Boolean(aan);
  toonHerhaalstand(toestand.previewHerhalen);
  const live = toestand.live;
  if (!live) { toestand.herhaalVerzoek = null; return Promise.resolve(); }
  const opdracht = {afspeelbeurt: live.afspeelbeurt, waarde: Boolean(aan),
    volgnummer: ++toestand.herhaalVolgnummer, ontvangen: false, geldigTot: Infinity};
  toestand.herhaalVerzoek = opdracht;
  herhaalWachtrij = herhaalWachtrij.catch(() => {}).then(async () => {
    if (toestand.herhaalVerzoek !== opdracht || toestand.live !== live) return;
    try {
      await vraagAanPython('POST', '/api/speler/live',
        {afspeelbeurt_id: live.afspeelbeurt, herhalen: opdracht.waarde});
      opdracht.ontvangen = true;
      opdracht.geldigTot = performance.now() + 1800;
    } catch (fout) {
      if (toestand.herhaalVerzoek === opdracht) {
        toestand.herhaalVerzoek = null;
        toestand.previewHerhalen = Boolean(live.bevestigdHerhalen);
        toonHerhaalstand(toestand.previewHerhalen);
      }
      toonMelding(`Herhalen niet aangepast: ${fout.message}`, true);
    }
  });
  return herhaalWachtrij;
}

function werkHerhalenUitStatusBij(status) {
  const live = toestand.live;
  if (!live || live.afspeelbeurt !== status.afspeelbeurt_id) return;
  const werkelijk = Boolean(status.live_herhalen);
  live.bevestigdHerhalen = werkelijk;
  const opdracht = toestand.herhaalVerzoek;
  if (opdracht && opdracht.afspeelbeurt === live.afspeelbeurt) {
    const bevestigd = opdracht.ontvangen && werkelijk === opdracht.waarde;
    if (!bevestigd && performance.now() < opdracht.geldigTot) return;
    if (!bevestigd) toonMelding('De audiomotor heeft Herhalen niet bevestigd. De werkelijke stand wordt getoond.', true);
  }
  toestand.herhaalVerzoek = null;
  toestand.previewHerhalen = werkelijk;
  toonHerhaalstand(werkelijk);
}

// Eén wachtrij voor beide schuiven. Er is maximaal één HTTP-verzoek tegelijk.
// Tussenliggende sleepwaarden worden samengevoegd; de laatste waarde gaat nooit verloren.
const volumeBediening = {
  gewenst: null, bewaren: false, bezig: false, timer: null,
  volgnummer: 0, bevestigd: 75, slepen: false, laatstVerzonden: 0
};
function toonSoundboardvolume(percentage) {
  toestand.effectvolumePercentage = percentage;
  for (const id of ['speler-volume-schuif', 'algemeen-effectvolume']) {
    element(id).value = String(percentage);
  }
  element('speler-volume-waarde').textContent = `${percentage}%`;
  werkEffectvolumeWeergaveBij(percentage);
  if (toestand.preview) toestand.preview.tijdelijkVolume = null;
  gebruikPreviewNormalisatie(toestand.preview);
  gebruikPreviewNormalisatie(toestand.editorVoorbeeld);
  werkVolumeSamenhangBij();
}

function planSoundboardvolume(percentage, bewaren = false) {
  if (!Number.isInteger(percentage) || percentage < 0 || percentage > 200) return;
  volumeBediening.gewenst = percentage;
  volumeBediening.bewaren = volumeBediening.bewaren || bewaren;
  volumeBediening.volgnummer++;
  toonSoundboardvolume(percentage);
  if (!volumeBediening.bezig) {
    clearTimeout(volumeBediening.timer);
    const wachten = bewaren ? 0 : Math.max(0, 70 - (performance.now() - volumeBediening.laatstVerzonden));
    volumeBediening.timer = setTimeout(verzendSoundboardvolume, wachten);
  }
}

async function verzendSoundboardvolume() {
  volumeBediening.timer = null;
  if (volumeBediening.bezig || volumeBediening.gewenst === null) return;
  const percentage = volumeBediening.gewenst;
  const volgnummer = volumeBediening.volgnummer;
  const bewaren = volumeBediening.bewaren;
  volumeBediening.bewaren = false;
  volumeBediening.bezig = true;
  volumeBediening.laatstVerzonden = performance.now();
  try {
    const pad = bewaren ? '/api/instellingen/effectvolume' : '/api/speler/volume';
    const antwoord = await vraagAanPython('POST', pad, {percentage});
    if (antwoord.percentage !== percentage) throw new Error('De audiomotor bevestigde een ander volume.');
    volumeBediening.bevestigd = percentage;
    if (volgnummer === volumeBediening.volgnummer) {
      volumeBediening.gewenst = null;
      toonSoundboardvolume(percentage);
    }
  } catch (fout) {
    // Een fout van een oudere waarde mag de nieuwere sleepwaarde niet terugzetten.
    if (volgnummer === volumeBediening.volgnummer) {
      volumeBediening.gewenst = null;
      toonSoundboardvolume(volumeBediening.bevestigd);
    }
    toonMelding(`Totaalvolume ${bewaren ? 'niet opgeslagen' : 'niet aangepast'}: ${fout.message}`, true);
  } finally {
    volumeBediening.bezig = false;
    if (volumeBediening.gewenst !== null) {
      const wachten = volumeBediening.bewaren ? 0 : Math.max(0, 70 - (performance.now() - volumeBediening.laatstVerzonden));
      volumeBediening.timer = setTimeout(verzendSoundboardvolume, wachten);
    }
  }
}

function koppelVolumeSchuif(schuif) {
  schuif.addEventListener('pointerdown', () => { volumeBediening.slepen = true; });
  schuif.addEventListener('input', () => planSoundboardvolume(Number(schuif.value)));
  const afronden = () => {
    volumeBediening.slepen = false;
    planSoundboardvolume(Number(schuif.value), true);
  };
  schuif.addEventListener('change', afronden);
  schuif.addEventListener('pointercancel', afronden);
  schuif.addEventListener('pointerup', () => {
    if (volumeBediening.slepen) afronden();
  });
  schuif.addEventListener('blur', () => {
    if (volumeBediening.slepen || volumeBediening.gewenst !== null) afronden();
  });
}

// Geen databasewerk tijdens slepen. Alleen de huidige afspeelbeurt verandert.
const basisvolumeBediening = { gewenst:null, bezig:false, timer:null, laatste:0, volgnummer:0 };

function werkVolumeSamenhangBij() {
  const totaal = toestand.effectvolumePercentage ?? 100;
  const preview = toestand.preview;
  const live = toestand.live;
  const actief = preview?.gestart ? preview : live;
  const id = actief?.geluidId;
  const basis = preview?.gestart
    ? (preview.basisvolume ?? preview.normalisatieData?.basisvolume ?? vindGeluid(id)?.volume ?? 1)
    : (toestand.status?.huidig_geluid_id === id && Number.isFinite(toestand.status?.live_basisvolume)
      ? toestand.status.live_basisvolume : vindGeluid(id)?.volume ?? 1);
  const uitleg = element('speler-volume-samenhang');
  if (uitleg) uitleg.textContent = id
    ? `Basis van dit geluid: ${Math.round(basis * 100)}%. Samen met totaalvolume: ${Math.round(basis * totaal)}% vóór normalisatie en piekbeveiliging.`
    : 'Voor alle geluiden. Het basisvolume stel je per geluid in via Bewerken.';
  const editor = element('editor-volume-samenhang');
  if (editor) {
    const waarde = Number(element('bewerken-volume').value);
    editor.textContent = `Totaalvolume: ${totaal}%. Samen: ${Math.round(waarde * totaal / 100)}% vóór normalisatie en piekbeveiliging.`;
  }
}

function pasEditorBasisvolumeAan() {
  const geluidId = toestand.gekozenGeluid;
  const percentage = Number(element('bewerken-volume').value);
  if (!geluidId || !Number.isInteger(percentage) || percentage < 0 || percentage > 200) return;
  element('volume-uitleg').textContent = `${percentage}%`;
  // Een lokale GainNode reageert meteen. Ook 0% naar 150% vraagt geen nieuwe decode.
  for (const voorbeeld of [toestand.preview, toestand.editorVoorbeeld]) {
    if (voorbeeld?.geluidId !== geluidId) continue;
    voorbeeld.basisvolume = percentage / 100;
    gebruikPreviewNormalisatie(voorbeeld);
  }
  const status = toestand.status;
  if (toestand.verwachtGeluid?.id === geluidId) {
    toestand.wachtendBasisvolume = {geluidId, percentage, afspeelnummer:toestand.afspeelVolgnummer};
  } else if (status?.huidig_geluid_id === geluidId && status.afspeelbeurt_id &&
      toestand.gewensteSpelmodus !== 'preview') {
    planBasisvolume({afspeelbeurt_id:status.afspeelbeurt_id, geluid_id:geluidId, percentage});
  }
  werkVolumeSamenhangBij();
}

function pasWachtendBasisvolumeToe(status) {
  const wachtend = toestand.wachtendBasisvolume;
  if (!wachtend) return;
  if (wachtend.afspeelnummer !== toestand.afspeelVolgnummer) {
    toestand.wachtendBasisvolume = null;
    return;
  }
  if (!status.geluid_voorbereiden && status.huidig_geluid_id === wachtend.geluidId && status.afspeelbeurt_id) {
    toestand.wachtendBasisvolume = null;
    planBasisvolume({afspeelbeurt_id:status.afspeelbeurt_id, geluid_id:wachtend.geluidId, percentage:wachtend.percentage});
  }
}

function planBasisvolume(opdracht) {
  basisvolumeBediening.gewenst = opdracht;
  basisvolumeBediening.volgnummer++;
  if (!basisvolumeBediening.bezig) {
    clearTimeout(basisvolumeBediening.timer);
    basisvolumeBediening.timer = setTimeout(verzendBasisvolume,
      Math.max(0, 70 - (performance.now() - basisvolumeBediening.laatste)));
  }
}

async function verzendBasisvolume() {
  basisvolumeBediening.timer = null;
  if (basisvolumeBediening.bezig || !basisvolumeBediening.gewenst) return;
  const opdracht = basisvolumeBediening.gewenst;
  const nummer = basisvolumeBediening.volgnummer;
  basisvolumeBediening.gewenst = null;
  basisvolumeBediening.bezig = true;
  basisvolumeBediening.laatste = performance.now();
  try {
    await vraagAanPython('POST', '/api/speler/basisvolume', opdracht);
    // Een late reactie mag niet de stand van een nieuw fragment overschrijven.
    if (nummer === basisvolumeBediening.volgnummer &&
        toestand.status?.afspeelbeurt_id === opdracht.afspeelbeurt_id) {
      toestand.status.live_basisvolume = opdracht.percentage / 100;
      werkVolumeSamenhangBij();
    }
  } catch (fout) {
    if (fout.foutcode !== 'SPELER-001') toonMelding(`Basisvolume niet aangepast: ${fout.message}`, true);
  } finally {
    basisvolumeBediening.bezig = false;
    if (basisvolumeBediening.gewenst) {
      basisvolumeBediening.timer = setTimeout(verzendBasisvolume,
        Math.max(0, 70 - (performance.now() - basisvolumeBediening.laatste)));
    }
  }
}

function normaliseerZoektekst(tekst) {
  return String(tekst ?? '').normalize('NFD').replace(/\p{Diacritic}/gu, '').toLocaleLowerCase('nl-NL');
}
function pastBijZoekopdracht(geluid, zoekterm) {
  const woorden = normaliseerZoektekst(zoekterm).trim().split(/\s+/).filter(Boolean);
  const tekst = normaliseerZoektekst(geefDoorzoekbareTekstVanGeluid(geluid));
  return woorden.every(woord => tekst.includes(woord));
}

function koppelPreviewSpelerbediening() {
  const zoeken = element("tijdlijn-schuif");
  const herhalen = element("knop-preview-herhaal");
  zoeken.addEventListener("pointerdown", () => {
    if (toestand.preview) toestand.preview.bezigMetZoeken = true;
    if (toestand.live) toestand.live.bezigMetZoeken = true;
  });
  zoeken.addEventListener("input", () => {
    const preview = toestand.preview;
    const live = toestand.live;
    const actief = preview?.gestart ? preview : live;
    if (!actief) return;
    const positie = Number(zoeken.value) / 1000 * (actief.duur ?? actief.duurt);
    element("tijdlijn-tijd").textContent = netteTijd(positie);
    zoeken.setAttribute("aria-valuetext", `${netteTijd(positie)} van ${netteTijd(actief.duur ?? actief.duurt)}`);
    element("tijdlijn-vulling").style.width = `${Number(zoeken.value) / 10}%`;
    if (preview && !preview.bezigMetZoeken) zoekInPreview(preview, Number(zoeken.value) / 1000);
  });
  zoeken.addEventListener("change", () => {
    const preview = toestand.preview;
    if (preview) {
      preview.bezigMetZoeken = false;
      zoekInPreview(preview, Number(zoeken.value) / 1000);
      return;
    }
    const live = toestand.live;
    if (!live) return;
    live.bezigMetZoeken = false;
    const fractie = Number(zoeken.value) / 1000;
    live.verstreken = fractie * live.duurt;
    live.laatstOntvangen = performance.now();
    live.zoekTot = performance.now() + 260;
    voerGebruikersactieUit('Positie veranderen', async () => {
      await vraagAanPython('POST', '/api/speler/live', {afspeelbeurt_id: live.afspeelbeurt, positie: fractie});
    });
  });
  zoeken.addEventListener("pointercancel", () => {
    if (toestand.preview) toestand.preview.bezigMetZoeken = false;
    if (toestand.live) toestand.live.bezigMetZoeken = false;
  });
  herhalen.addEventListener("click", () => stelHerhalenIn(!toestand.previewHerhalen));
  element('knop-speler-opnieuw').addEventListener('click', speelOpnieuwAf);
  koppelVolumeSchuif(element('speler-volume-schuif'));
}

function registreerPreviewBijPython(geluidId, actie, verstrekenSeconden = 0, reden = "niet_opgegeven", afspeelbeurt = null) {
  // De logging mislukt niet stilzwijgend: bij een fout blijft de reden
  // zichtbaar in de browserconsole. De preview zelf stopt niet door een logfout.
  vraagAanPython("POST", "/api/preview", {
    geluid_id: geluidId, actie, reden, afspeelbeurt, verstreken_seconden: Math.max(0, Math.min(120, verstrekenSeconden))
  }).then(() => { if (actie === "gestart") laadRecentGebruikt().catch(() => {}); })
    .catch((fout) => console.error("Previewlogging mislukt", fout));
}

function stopPreview(reden = "handmatig") {
  const lopend = toestand.preview;
  if (!lopend) return;
  toestand.preview = null;
  if (lopend.interval) clearInterval(lopend.interval);
  if (lopend.animatie) window.cancelAnimationFrame(lopend.animatie);
  const afspeeltijd = Math.max(0, (lopend.media.currentTime || lopend.start) - lopend.start);
  lopend.media.pause();
  if (lopend.audioBus) lopend.audioBus.versterker.gain.value = 0;
  lopend.media.removeAttribute("src");
  lopend.media.load();
  registreerPreviewBijPython(lopend.geluidId, "gestopt", Math.min(afspeeltijd, lopend.duur), reden, lopend.afspeelbeurt);
  werkActieveKaartenBij();
  if (!toestand.live) toonStilMediascherm();
}

// Eén browser stuurt steeds maar één start-/stopopdracht tegelijk.
// De laatst gekozen actie wint, ook als een eerdere HTTP-aanvraag vertraagt.
let wachtrijVanSpeleracties = Promise.resolve();
function planExclusieveSpeleractie(naam, modus, actie) {
  const volgnummer = ++toestand.afspeelVolgnummer;
  toestand.gewensteSpelmodus = modus;
  toestand.previewGereedVoorExtern = false;
  const verzoek = wachtrijVanSpeleracties.catch(() => {}).then(async () => {
    if (volgnummer !== toestand.afspeelVolgnummer) return;
    await actie();
  });
  wachtrijVanSpeleracties = verzoek.catch(() => {});
  return voerGebruikersactieUit(naam, () => verzoek);
}

function beginPreview(geluidId) {
  // Web Audio alvast tijdens het echte klikmoment ontgrendelen. Anders kan een
  // browser de preview na het asynchroon stoppen van de uitzending weigeren.
  const AudioContextKlasse = window.AudioContext || window.webkitAudioContext;
  if (AudioContextKlasse) {
    try {
      if (!previewAudioContext) previewAudioContext = new AudioContextKlasse();
      previewAudioContext.resume().catch(() => {});
    } catch (fout) {
      // De reguliere Preview-foutmelding volgt pas als daadwerkelijk spelen faalt.
    }
  }
  return planExclusieveSpeleractie("Preview starten", "preview", async () => {
    const geluid = vindGeluid(geluidId);
    if (!geluid?.mediabron || !geluid.bestand_gevonden) {
      throw new Error("Het bronbestand ontbreekt. Importeer het geluid via de webpagina.");
    }
    stopPreview("vervangen");
    // STOP annuléért óók een nog decodeerend fragment. Eerst bevestiging
    // van de server ontvangen, pas daarna lokaal audio starten.
    await vraagAanPython("POST", "/api/stop", {});
    // De callback stopt asynchroon. Start lokaal geluid pas als de
    // virtuele microfoon niet langer hetzelfde fragment uitzendt.
    let liveStil = false;
    for (let poging = 0; poging < 40; poging++) {
      if (toestand.gewensteSpelmodus !== 'preview') return;
      const status = await vraagAanPython('GET', '/api/status');
      if (!status.huidig_geluid_id && !status.geluid_voorbereiden) {
        liveStil = true;
        break;
      }
      await new Promise((klaar) => setTimeout(klaar, 35));
    }
    if (!liveStil) throw new Error('De uitzending stopt nog niet. Probeer opnieuw.');
    if (toestand.gewensteSpelmodus !== 'preview') return;
    // Een latere globale sneltoets mag weer live audio starten; alleen de
    // oude afspeelbeurt tijdens het STOP-verzoek moet worden genegeerd.
    toestand.previewGereedVoorExtern = true;
    toestand.live?.videobediening?.stop();
    toestand.live = null;
    toestand.verwachtGeluid = null;
    // Lokaal luisteren werkt zonder verbinding met de virtuele microfoon.
    const start = Number(geluid.beginpositie) || 0;
    const duur = Number(geluid.fragmentduur ?? geluid.maximale_duur) || 0.1;
    const speler = geluid.is_video ? document.createElement("video") : new Audio();
    const { bus: audioBus, activering } = maakPreviewAudioBus(speler);
    speler.preload = "metadata";
    speler.playsInline = true;
    speler.autoplay = false;
    speler.controls = false;
    speler.src = geluid.mediabron;
    speler.muted = true;
    // GainNode ontvangt de effectieve mixerversterking, ook boven 100%.
    speler.volume = 1;
    toestand.laatsteAfspeelkeuze = {geluidId, modus: 'preview', tijdelijkeSelectie: null};
    const preview = { geluidId, geluid, media: speler, start, duur, audioBus, activering,
      normalisatieData: null, interval: null, animatie: null, gestart: false,
      bezigMetZoeken: false, eindeBezig: false, afspeelbeurt: crypto.randomUUID() };
    // Alle standen in één aanvraag: wisselen kan daarna tijdens de preview.
    preview.normalisatieVerzoek = leesPreviewNormalisatie(geluidId)
      .then((gegevens) => ({ gegevens }), (fout) => ({ fout }));
    toestand.preview = preview;
    toestand.live = null;
    toonMediascherm(geluid, true, start, speler);
    element("huidige-afspeelstand").textContent = "PREVIEW";
    element("nu-actief-titel").textContent = geluid.naam;
    element("huidige-uitleg").textContent = "Preview voorbereiden, alleen lokaal.";
    element("speler-meta").hidden = false;
    element("knop-preview-herhaal").hidden = false;
    element("knop-preview-herhaal").setAttribute("aria-pressed", String(toestand.previewHerhalen));
    element("knop-preview-herhaal").classList.toggle("gekozen", toestand.previewHerhalen);
    element("knop-preview-stop").disabled = false;
    stelSpelerActiefIn(true);
    werkSpelerTijdBij(0, duur);
    werkActieveKaartenBij();
    const beginMetAfspelen = async () => {
      if (toestand.preview !== preview) return;
      // Voorkom dat een kort geluid al gedempt eindigt terwijl Python
      // nog de luidheid meet. De eerste play() activeert alleen de browser.
      speler.pause();
      if (Number.isFinite(speler.duration) && start >= speler.duration) {
        stopPreview("ongeldig_startpunt");
        toonMelding("Het startpunt ligt na het einde van het bestand.", true);
        return;
      }
      try {
        speler.currentTime = start;
        await new Promise((resolve, reject) => {
          if (Math.abs(speler.currentTime - start) < .12) { resolve(); return; }
          speler.addEventListener("seeked", resolve, { once: true });
          setTimeout(resolve, 1300);
        });
        if (toestand.preview !== preview) return;
        const analyse = await preview.normalisatieVerzoek;
        if (analyse.fout) throw analyse.fout;
        if (toestand.preview !== preview) return;
        preview.normalisatieData = analyse.gegevens;
        await preview.activering;
        if (toestand.preview !== preview) return;
        gebruikPreviewNormalisatie(preview, true);
        speler.muted = false;
        await speler.play();
        if (toestand.preview !== preview) return;
        if (geluid.is_video) {
          // Pas tonen als werkelijk een frame van de geselecteerde positie klaar is.
          window.DrostVideoSynchronisatie.toonPreviewNaEersteFrame(speler);
        }
        preview.gestart = true;
        werkOpnieuwKnopBij();
        element("tijdlijn-schuif").disabled = false;
        preview.animatie = window.requestAnimationFrame(() => animeerPreviewTijd(preview));
        registreerPreviewBijPython(geluidId, "gestart", 0, "start", preview.afspeelbeurt);
      } catch (fout) {
        stopPreview("browserfout");
        toonMelding(`Preview kon niet afspelen: ${fout.message}`, true);
      }
    };
    speler.addEventListener("loadedmetadata", beginMetAfspelen, { once: true });
    speler.addEventListener("ended", () => eindigPreviewFragment(preview));
    speler.addEventListener("timeupdate", () => werkPreviewTijdBij(preview));
    // Een browser kan afspelen pas na interactie toestaan. Start daarom al
    // tijdens de klik gedempt. Na het zoeken schakelen we het geluid in.
    speler.play().catch(() => {});
    // Extra eindcontrole voor inactieve browsertabbladen (rAF wordt daar vertraagd).
    preview.interval = setInterval(() => werkPreviewTijdBij(preview), 160);
  });
}

/*
  De live-speler volgt de werkelijk gemengde frames uit Python.
  Een MP4 wordt hier muted afgespeeld om dubbele audio te voorkomen.
*/
function animeerLiveSpeler(live) {
  if (toestand.live !== live) return;
  const maximaal = streamingIsBeschikbaar ? .16 : 1.8;
  const extra = Math.max(0, Math.min(maximaal, (performance.now() - live.laatstOntvangen) / 1000));
  const sec = Math.min(live.duurt, live.verstreken + extra);
  if (!live.bezigMetZoeken) werkSpelerTijdBij(sec, live.duurt);
  live.animatie = requestAnimationFrame(() => animeerLiveSpeler(live));
}

function updateLiveTijdVanPython(status) {
  const live = toestand.live;
  if (!live || live.afspeelbeurt !== status.afspeelbeurt_id) return;
  const nu = performance.now();
  werkHerhalenUitStatusBij(status);
  if (nu < live.zoekTot) return;
  live.verstreken = Math.max(0, Number(status.afgespeelde_seconden) || 0);
  live.laatstOntvangen = nu;
  if (!live.bezigMetZoeken) werkSpelerTijdBij(live.verstreken, live.duurt);
  live.videobediening?.synchroniseerMetAudio(status);
  if (live.animatie === null) live.animatie = requestAnimationFrame(() => animeerLiveSpeler(live));
}

function werkLiveGeluidBij(status) {
  // Tijdens een expliciet gekozen preview mogen vertraagde statusberichten
  // niet het livevideobeeld of dezelfde oude uitzending terugzetten.
  if (toestand.gewensteSpelmodus === "preview") return;
  const id = status.huidig_geluid_id;
  if (id) {
    if (toestand.preview) stopPreview("live_gestart");
    const geluid = vindGeluid(id);
    if (!geluid) return;
    if (!toestand.live || toestand.live.afspeelbeurt !== status.afspeelbeurt_id) {
      // Nieuwe afspeelbeurt: de oude controller ruimt zijn videobuffer op.
      toestand.live?.videobediening?.stop();
      if (toestand.live?.animatie) cancelAnimationFrame(toestand.live.animatie);
      toestand.live = { geluidId: id, afspeelbeurt: status.afspeelbeurt_id, videobediening: null,
        verstreken: 0, laatstOntvangen: performance.now(), duurt: Number(geluid.fragmentduur ?? geluid.maximale_duur) || 0.1,
        bezigMetZoeken: false, zoekTot: 0, animatie: null, laatsteWijzigingsnummer: null };
      if (toestand.laatsteAfspeelkeuze?.modus !== 'live' ||
          toestand.laatsteAfspeelkeuze?.geluidId !== id || !toestand.verwachtGeluid) {
        toestand.laatsteAfspeelkeuze = {geluidId: id, modus: 'live', tijdelijkeSelectie: null};
      }
      laadRecentGebruikt().catch(() => {});
      toestand.verwachtGeluid = null;
      toestand.live.videobediening = toonMediascherm(
        geluid, false, Number(status.beginpositie_seconden) || 0
      );
      element("nu-actief-titel").textContent = geluid.naam;
      element("huidige-afspeelstand").textContent = "UITZENDEN";
      element("huidige-uitleg").textContent = status.meeluisteren_aan
        ? "Het geluid gaat naar de virtuele microfoon. Je hoort het ook via je luisterapparaat."
        : "Het geluid gaat naar de virtuele microfoon. Meeluisteren staat uit.";
      element("knop-preview-stop").disabled = true;
      element("knop-preview-herhaal").hidden = false;
      element("knop-preview-herhaal").title = "Herhaal dit geluid via de virtuele microfoon";
      element("knop-preview-herhaal").setAttribute("aria-pressed", String(toestand.previewHerhalen));
      element("tijdlijn-schuif").disabled = false;
      element("speler-meta").hidden = false;
      element("speler-volume-regelaar").hidden = false;
      element("speler-volume-info").hidden = true;
      element("speler-volume-schuif").value = String(toestand.effectvolumePercentage ?? 100);
      element("speler-volume-waarde").textContent = `${toestand.effectvolumePercentage ?? 100}%`;
      element("speler-correctie-info").hidden = true;
      stelSpelerActiefIn(true);
      werkActieveKaartenBij();
    }
    if (!streamingIsBeschikbaar || performance.now() - laatsteOntvangstVanNiveaus > 250) {
      updateLiveTijdVanPython(status);
    }
  } else if (toestand.live) {
    if (toestand.live.animatie) cancelAnimationFrame(toestand.live.animatie);
    toestand.live.videobediening?.stop();
    toestand.live = null;
    werkActieveKaartenBij();
    if (!toestand.preview) toonStilMediascherm();
  } else if (toestand.verwachtGeluid && !status.geluid_voorbereiden) {
    // Een heel kort geluid kan tussen twee statusmetingen vallen. Toon het
    // voorbereidingsvlak dan nog kort, maar houd het niet oneindig open.
    if (Date.now() - toestand.verwachtGeluid.gestart > 900) {
      toestand.verwachtGeluid = null;
      if (!toestand.preview) toonStilMediascherm();
    }
  }
}

async function beginGeluidAfspelen(geluidId, tijdelijkeSelectie = null) {
  return planExclusieveSpeleractie('Geluid uitzenden', 'live', async () => {
    if (applicatieVerbinding.bereikbaar === false) throw new Error(APP_NIET_BEREIKBAAR);
    if (applicatieVerbinding.nieuweSessie) throw new Error(PAGINA_VERNIEUWEN);
    const status = toestand.status;
    if (status?.toestand !== "verbonden") throw new Error("Klik eerst op Verbinden.");
    if (!status.effecten_aan) throw new Error("Zet Soundboard eerst aan.");
    const geluid = vindGeluid(geluidId);
    if (!geluid?.bestand_gevonden) throw new Error("Het bronbestand ontbreekt. Importeer het opnieuw.");
    stopPreview('live_aangevraagd');
    stopEditorPreview('live_aangevraagd');
    // Herhalen wordt met de startopdracht meegestuurd. Bij fragmenten van
    // minder dan een seconde zou een latere HTTP-aanvraag te laat komen.
    await vraagAanPython('POST', `/api/geluiden/${geluidId}/afspelen`, {
      ...(tijdelijkeSelectie || {}), herhalen: toestand.previewHerhalen
    });
    toestand.laatsteAfspeelkeuze = {geluidId, modus: 'live',
      tijdelijkeSelectie: tijdelijkeSelectie ? {...tijdelijkeSelectie} : null};
    toestand.editorUitzendGeluidId = tijdelijkeSelectie ? geluidId : null;
    toestand.verwachtGeluid = { id: geluidId, gestart: Date.now() };
    werkActieveKaartenBij();
    stelSpelerActiefIn(true);
    element("nu-actief-titel").textContent = geluid.naam;
    element("huidige-afspeelstand").textContent = "UITZENDEN WORDT VOORBEREID";
    element('knop-preview-herhaal').hidden = false;
    element('knop-preview-herhaal').setAttribute('aria-pressed', String(toestand.previewHerhalen));
    element('knop-preview-herhaal').classList.toggle('gekozen', toestand.previewHerhalen);
    element("huidige-uitleg").textContent = "Het fragment wordt klaargemaakt voor afspelen via de virtuele microfoon.";
    toonVoorbereidingZonderVideo(geluid);
    if (tijdelijkeSelectie) werkEditorKnoppenBij('Selectie wordt uitgezonden.');
    toonMelding(`${geluid.naam} wordt naar de virtuele microfoon gestuurd.`);
  });
}

function toonVBCableStatus(status) {
  const vak = element('vb-cable-waarschuwing');
  toestand.vbCable = status;
  if (status?.status === 'gereed' && status.bruikbaar === true) {
    vak.hidden = true;
    return;
  }
  // Onduidelijke resultaten worden niet als ontbrekende installatie getoond.
  const teksten = {
    ontbreekt: 'VB-CABLE niet beschikbaar',
    onvolledig: 'VB-CABLE is niet volledig beschikbaar',
    meerdere: 'Meerdere VB-CABLE-apparaten gevonden',
    controle_mislukt: 'VB-CABLE kon niet worden gecontroleerd'
  };
  element('vb-cable-titel').textContent = teksten[status?.status] || 'VB-CABLE controleren';
  element('vb-cable-omschrijving').textContent =
    status?.melding || 'Controleer de audioapparaten via Windows.';
  // Bij een mislukte detectie weten we niet of de driver ontbreekt.
  element('vb-cable-hulp').hidden = status?.status === 'controle_mislukt';
  element('vb-cable-stappen').hidden = !['ontbreekt', 'onvolledig'].includes(status?.status);
  vak.hidden = false;
}

async function controleerVBCable({ toonBevestiging = false } = {}) {
  const knop = element('vb-cable-opnieuw');
  knop.disabled = true;
  try {
    const status = await vraagAanPython('GET', '/api/vereisten/vb-cable');
    toonVBCableStatus(status);
    if (toonBevestiging && status.status === 'gereed') {
      toonMelding('VB-CABLE is beschikbaar. Je kunt je microfoon verbinden.');
    }
  } catch (fout) {
    // De audiolibrary of lokale server kan onbereikbaar zijn. Dat is geen
    // bewijs dat de VB-CABLE-driver ontbreekt. De rest van de UI blijft open.
    toonVBCableStatus({ status: 'controle_mislukt', bruikbaar: false,
      melding: 'De audioapparaten konden niet gecontroleerd worden. Probeer het opnieuw.' });
    registreerBrowserfout(`VB-CABLE controleren: ${fout.message}`, fout.stack || '');
  } finally { knop.disabled = false; }
}

async function laadApparaten() {
  const antwoord = await vraagAanPython("GET", "/api/apparaten");
  const menu = element("microfoonkeuze");
  const eerder = menu.value;
  const standaard = antwoord.standaard_microfoonnummer;
  toestand.automatischEenMicrofoon = (antwoord.microfoons || []).length === 1
    ? String(antwoord.microfoons[0].nummer) : null;
  menu.replaceChildren(new Option("Kies een microfoon", ""));
  for (const apparaat of antwoord.microfoons || []) {
    const isStandaard = apparaat.nummer === standaard;
    const naam = isStandaard ? `${apparaat.naam} (${(antwoord.microfoons || []).length === 1 ? 'Automatisch gekozen' : 'Windows-standaard'})` : apparaat.naam;
    menu.appendChild(new Option(naam, String(apparaat.nummer)));
  }
  const keuzes = [...menu.options].map((keuze) => keuze.value);
  if (toestand.microfoonHandmatigGekozen && !keuzes.includes(eerder)) {
    toestand.microfoonHandmatigGekozen = false;
  }
  const geldig = (antwoord.microfoons || []).map((apparaat) => String(apparaat.nummer));
  const automatisch = Number.isInteger(standaard) && geldig.includes(String(standaard))
    ? String(standaard) : (geldig.length === 1 ? geldig[0] : "");
  // Ontbreekt de Windows-standaard en bestaan er meerdere microfoons, dan
  // nooit zelf raden. Een handmatige keuze blijft behouden zolang hij bestaat.
  menu.value = toestand.microfoonHandmatigGekozen ? eerder : automatisch;
  // Als de server al verbonden is, moet de keuzelijst het werkelijke
  // opnameapparaat tonen, ook na een herlaadbeurt van het dashboard.
  if (toestand.status?.toestand === 'verbonden') {
    const inGebruik = (antwoord.microfoons || []).find((apparaat) =>
      apparaat.naam === toestand.status.microfoon);
    if (inGebruik) menu.value = String(inGebruik.nummer);
  }
  werkVerbindingsknopBij(toestand.status);
  const luistermenu = element("monitor-uitvoer");
  const gekozen = toestand.laatstGekozenMonitor ?? luistermenu.value;
  luistermenu.replaceChildren(new Option("Automatisch (Windows-standaard)", ""));
  for (const apparaat of antwoord.uitvoerapparaten || []) {
    luistermenu.appendChild(new Option(apparaat.naam, String(apparaat.nummer)));
  }
  luistermenu.value = [...luistermenu.options].some((keuze) => keuze.value === gekozen) ? gekozen : "";
  if (!(antwoord.microfoons || []).length) toonMelding("Geen microfoon gevonden. Controleer Windows-microfoonrechten.", true);
}

/*
  De browser ontvangt echte RMS- en samplepiekmetingen van Python.
  De groene balk en de witte lijn tonen NU allebei RMS op dezelfde schaal.
  De samplepiek krijgt een apart cijfer, zodat hij niet wordt verward met RMS.

  We verbergen ruis onder de zichtbare -60 dBFS-schaal. Een kleine
  hysterese voorkomt dat een niveau op de grens blijft knipperen.
  Alle metingen zelf blijven ongewijzigd in Python en in de API.
*/
const DECIBEL_ONDERKANT_VAN_METER = -60;
const DECIBEL_BOVENKANT_VAN_METER = 0;
const DECIBEL_WAARBIJ_METER_AANGAAT = -58;
const DECIBEL_WAARBIJ_METER_UITGAAT = -60;

const metersVoorAudio = [
  { balkId: "meter-microfoon", markeringId: "meter-microfoon-piek", rmsSchaal: 0,
    doelRms: 0, gemeten: false, signaalZichtbaar: false },
  { balkId: "meter-uitvoer", markeringId: "meter-uitvoer-piek", rmsSchaal: 0,
    doelRms: 0, gemeten: false, signaalZichtbaar: false }
];
let vorigeMeterFrameTijd = null;
let aangevraagdeMeterAnimatie = null;
const animatieBeperken = window.matchMedia("(prefers-reduced-motion: reduce)");

function geefDecibelVanGemetenNiveau(amplitude) {
  if (typeof amplitude !== "number" || !Number.isFinite(amplitude) || amplitude <= 0) {
    return Number.NEGATIVE_INFINITY;
  }
  return 20 * Math.log10(amplitude);
}

function meterPercentage(gemetenWaarde) {
  const decibel = geefDecibelVanGemetenNiveau(gemetenWaarde);
  if (!Number.isFinite(decibel)) return 0;
  // De maatstreepjes in CSS gebruiken exact dezelfde decibelgrenzen.
  return Math.max(0, Math.min(100,
    (decibel - DECIBEL_ONDERKANT_VAN_METER) * 100 /
    (DECIBEL_BOVENKANT_VAN_METER - DECIBEL_ONDERKANT_VAN_METER)));
}

function toonRms(rms, gemeten) {
  if (!gemeten) return "Niet gemeten";
  if (typeof rms !== "number" || !Number.isFinite(rms)) return "Ongeldige meting";
  const decibel = geefDecibelVanGemetenNiveau(rms);
  return Number.isFinite(decibel) ? `${decibel.toFixed(1)} dBFS` : "Stilte";
}

// Een piekwaarde blijft kort leesbaar. Dit verandert NIET de RMS-balk.
// Wanneer de bron stil wordt, verdwijnt de vastgehouden piek na 1,2 s.
const PIEK_VASTHOUDEN_MILLISECONDEN = 1200;
function toonVastgehoudenPiek(piek, rms, gemeten, nummer, tijdstip = performance.now()) {
  let vorig = toestand.laatstGemetenPieken[nummer];
  if (!gemeten) {
    toestand.laatstGemetenPieken[nummer] = null;
    return "Piek: —";
  }
  const nieuw = geefDecibelVanGemetenNiveau(piek);
  // Stille achtergrondruis mag nooit een schijnbaar blijvende piek worden.
  const isEchtSignaal = meterPercentage(rms) > 0 && Number.isFinite(nieuw) && nieuw > -60;
  if (isEchtSignaal && (!vorig || tijdstip >= vorig.tot || nieuw > vorig.decibel)) {
    vorig = { decibel: nieuw, tot: tijdstip + PIEK_VASTHOUDEN_MILLISECONDEN };
    toestand.laatstGemetenPieken[nummer] = vorig;
  }
  if (!vorig || tijdstip >= vorig.tot) {
    toestand.laatstGemetenPieken[nummer] = null;
    return "Piek: —";
  }
  return `Piek: ${vorig.decibel.toFixed(1)} dBFS`;
}

function tekenEenAudiometer(meter) {
  const percentage = Math.max(0, Math.min(100, meter.rmsSchaal));
  // Het kleurverloop blijft over de VOLLEDIGE schaal staan. Alleen het
  // zichtbare deel wordt bijgeknipt. Daardoor klopt de kleur bij -30 dBFS.
  element(meter.balkId).style.clipPath = `inset(0 ${100 - percentage}% 0 0)`;
  const markering = element(meter.markeringId);
  // Historische id eindigt op '-piek'; de markering is nu bewust RMS.
  markering.style.left = `${percentage}%`;
  markering.style.opacity = meter.gemeten && percentage > 0.2 ? "1" : "0";
}

function beweegLiveNiveaumeters(huidigeFrameTijd) {
  aangevraagdeMeterAnimatie = null;
  if (document.hidden || animatieBeperken.matches) {
    vorigeMeterFrameTijd = null;
    return;
  }
  const verstrekenSeconden = vorigeMeterFrameTijd === null
    ? 1 / 60
    : Math.min(0.08, Math.max(0, (huidigeFrameTijd - vorigeMeterFrameTijd) / 1000));
  vorigeMeterFrameTijd = huidigeFrameTijd;
  let moetVerderBewegen = false;

  for (const meter of metersVoorAudio) {
    const stijgt = meter.doelRms > meter.rmsSchaal;
    // De lijn stijgt snel maar de weergegeven RMS blijft een echte meting.
    // Terugvallen duurt korter dan vroeger; een lange uitloop suggereerde
    // ten onrechte dat iemand nog aan het praten was.
    const tijdconstante = stijgt ? 0.020 : 0.075;
    const deelVanVerschil = 1 - Math.exp(-verstrekenSeconden / tijdconstante);
    meter.rmsSchaal += (meter.doelRms - meter.rmsSchaal) * deelVanVerschil;
    if (Math.abs(meter.rmsSchaal - meter.doelRms) < 0.2) {
      meter.rmsSchaal = meter.doelRms;
    }
    tekenEenAudiometer(meter);
    if (meter.rmsSchaal !== meter.doelRms) moetVerderBewegen = true;
  }
  if (moetVerderBewegen) startMeterAnimatie();
}

function startMeterAnimatie() {
  if (aangevraagdeMeterAnimatie !== null || document.hidden || animatieBeperken.matches) return;
  aangevraagdeMeterAnimatie = requestAnimationFrame(beweegLiveNiveaumeters);
}

function zetNieuweNiveausInMeters(status, gemeten) {
  const metingen = [status.microfoon_rms, status.kabel_rms];
  for (let nummer = 0; nummer < metersVoorAudio.length; nummer++) {
    const meter = metersVoorAudio[nummer];
    const rms = metingen[nummer];
    meter.gemeten = gemeten;

    const decibel = geefDecibelVanGemetenNiveau(rms);
    if (!gemeten) {
      meter.signaalZichtbaar = false;
    } else if (!meter.signaalZichtbaar && decibel >= DECIBEL_WAARBIJ_METER_AANGAAT) {
      meter.signaalZichtbaar = true;
    } else if (meter.signaalZichtbaar && decibel < DECIBEL_WAARBIJ_METER_UITGAAT) {
      meter.signaalZichtbaar = false;
    }

    meter.doelRms = gemeten && meter.signaalZichtbaar ? meterPercentage(rms) : 0;
    if (animatieBeperken.matches) {
      meter.rmsSchaal = meter.doelRms;
      tekenEenAudiometer(meter);
    }
  }
  startMeterAnimatie();
}

// Gebruik één EventSource-verbinding voor snelle meters. Andere
// dashboardgegevens mogen rustig via de bestaande status-API lopen.
let stroomVanEchteNiveaus = null;
let laatsteOntvangstVanNiveaus = 0;
let streamingIsBeschikbaar = false;

function toonLimiterReductie(reductieDb, gemeten) {
  const reductie = gemeten && toestand.limiterAan && Number.isFinite(Number(reductieDb))
    ? Math.max(0, Math.min(60, Number(reductieDb))) : 0;
  element("limiter-reductie").textContent = `Piekreductie: ${reductie.toFixed(1).replace(".", ",")} dB`;
  element("limiter-balk").style.width = `${Math.min(100, reductie / 18 * 100)}%`;
}

function toonNieuweMeetwaarden(waarden, gemeten) {
  // Zowel de algemene meters als de stemmeters gebruiken dezelfde 30 Hz-stream.
  // Hiermee reageren korte woorden direct en hoeft /api/status niet sneller.
  werkStemmetersBij(waarden);
  toonLiveSoundboardniveau(waarden, gemeten);
  toonLimiterReductie(waarden.limiter_reductie_db, gemeten);
  zetNieuweNiveausInMeters(waarden, gemeten);
  element("tekst-microfoon").textContent = toonRms(waarden.microfoon_rms, gemeten);
  element("tekst-uitvoer").textContent = toonRms(waarden.kabel_rms, gemeten);
  element("tekst-microfoon-piek").textContent = toonVastgehoudenPiek(
    waarden.microfoon_piek, waarden.microfoon_rms, gemeten, 0
  );
  element("tekst-uitvoer-piek").textContent = toonVastgehoudenPiek(
    waarden.kabel_piek, waarden.kabel_rms, gemeten, 1
  );
}

function startDeDirecteNiveaustroom() {
  if (appAfsluitingAangevraagd || document.hidden || stroomVanEchteNiveaus || typeof EventSource === "undefined") return;
  const stroom = new EventSource("/api/niveaus/live");
  stroomVanEchteNiveaus = stroom;
  stroom.addEventListener("niveau", (gebeurtenis) => {
    if (appAfsluitingAangevraagd || document.hidden) return;
    try {
      const gegevens = JSON.parse(gebeurtenis.data);
      // Geen verzonnen audio: de browser tekent alleen de waarden die
      // Python tijdens de audiocallback daadwerkelijk heeft gemeten.
      streamingIsBeschikbaar = true;
      laatsteOntvangstVanNiveaus = performance.now();
      toonNieuweMeetwaarden(gegevens, Boolean(gegevens.gemeten));
      // Een globale sneltoets kan een uitzending starten terwijl deze tab
      // lokaal previewt. Dan onmiddellijk de preview stoppen.
      if (toestand.gewensteSpelmodus === 'preview' && toestand.previewGereedVoorExtern &&
          gegevens.huidig_geluid_id && gegevens.afspeelbeurt_id) {
        stopPreview('live_gestart_via_sneltoets');
        toestand.gewensteSpelmodus = 'live';
        toestand.previewGereedVoorExtern = false;
        vernieuwStatus();
      }
      // Dezelfde 30 Hz-meting voedt de tijdlijn: geen extra polling.
      if (toestand.gewensteSpelmodus !== 'preview') updateLiveTijdVanPython(gegevens);
      if (toestand.gewensteSpelmodus !== 'preview' &&
          ((gegevens.huidig_geluid_id && toestand.live?.afspeelbeurt !== gegevens.afspeelbeurt_id) ||
           (!gegevens.huidig_geluid_id && toestand.live))) {
        vernieuwStatus();
      }
    } catch (fout) {
      console.warn("Metergegevens waren ongeldig", fout);
    }
  });
  stroom.addEventListener("app", (gebeurtenis) => {
    try { if (JSON.parse(gebeurtenis.data).wordt_afgesloten) rondBrowserAfsluitingAf(); }
    catch (_) { /* Een ongeldig bericht sluit de app niet af. */ }
  });
  stroom.addEventListener("error", () => {
    // EventSource maakt zelf opnieuw verbinding. Als die tijdelijk weg is,
    // gebruikt het dashboard de gewone statusroute als veilige terugval.
    streamingIsBeschikbaar = false;
  });
}

function stopDeDirecteNiveaustroom() {
  stroomVanEchteNiveaus?.close();
  stroomVanEchteNiveaus = null;
  streamingIsBeschikbaar = false;
  laatsteOntvangstVanNiveaus = 0;
}

document.addEventListener("visibilitychange", () => {
  // De browser beperkt verborgen tabbladen. Sluit de stream daarom af en
  // begin met verse metingen bij het opnieuw tonen van het dashboard.
  if (appAfsluitingAangevraagd) return;
  vorigeMeterFrameTijd = null;
  if (document.hidden) {
    stopDeDirecteNiveaustroom();
  } else {
    startDeDirecteNiveaustroom();
    startMeterAnimatie();
    vernieuwStatus();
  }
});

async function vernieuwStatus() {
  if (appAfsluitingAangevraagd || toestand.bezetteStatusaanvraag) return;
  toestand.bezetteStatusaanvraag = true;
  const volumeVolgnummer = volumeBediening.volgnummer;
  const stemGeneratie = toestand.stemkeuzeGeneratie;
  const effectenGeneratie = effectenBediening.generatie;
  try {
    const status = await vraagAanPython("GET", "/api/status");
    if (appAfsluitingAangevraagd) return;
    if (status.app_wordt_afgesloten) { rondBrowserAfsluitingAf(); return; }
    if (effectenBediening.bezig || effectenGeneratie !== effectenBediening.generatie) {
      status.effecten_aan = effectenBediening.bevestigd ?? Boolean(toestand.status?.effecten_aan);
    } else if (typeof status.effecten_aan === 'boolean') {
      effectenBediening.bevestigd = status.effecten_aan;
    }
    toestand.status = status;
    if (!toestand.stemkeuzeBezig && stemGeneratie === toestand.stemkeuzeGeneratie) {
      if (typeof status.stemprofiel === 'string') toestand.stemprofiel = status.stemprofiel;
      if (status.natuurlijke_stem) werkNatuurlijkeStemBij(status.natuurlijke_stem);
    }
    toonStemverwerkingsfout(status);
    if (!toestand.stemkeuzeBezig && stemGeneratie === toestand.stemkeuzeGeneratie && typeof status.stemvervormer_aan === 'boolean') {
      toestand.stemactief = status.stemvervormer_aan;
      werkStemprofielKaartenBij({parameters:false});
    }
    // Verlies van de previewstream wordt ook zichtbaar als de instellingen dicht zijn.
    if (!toestand.stemvoorbeeldBezig && Boolean(status.stemvoorbeeld?.actief) !== toestand.stemvoorbeeldActief) {
      toestand.stemvoorbeeldActief = Boolean(status.stemvoorbeeld?.actief);
      werkStemvoorbeeldKnopBij();
    }
    if (Number.isInteger(status.effectvolume_percentage) &&
        volumeVolgnummer === volumeBediening.volgnummer &&
        !volumeBediening.bezig && volumeBediening.gewenst === null && !volumeBediening.slepen &&
        document.activeElement !== element("algemeen-effectvolume") &&
        !element("algemeen-effectvolume").disabled &&
        status.effectvolume_percentage !== toestand.effectvolumePercentage) {
      volumeBediening.bevestigd = status.effectvolume_percentage;
      toonSoundboardvolume(status.effectvolume_percentage);
    }
    if (typeof status.limiter_aan === "boolean") {
      toestand.limiterAan = status.limiter_aan;
      element("knop-limiter").setAttribute("aria-checked", String(status.limiter_aan));
    }
    const verbonden = status.toestand === "verbonden";
    const bezig = ["wordt_verbonden", "wordt_verbroken"].includes(status.toestand);
    const omschrijving = status.toestand === "wordt_verbonden" ? "Bezig met verbinden" :
      status.toestand === "wordt_verbroken" ? "Bezig met verbreken" :
      status.toestand === "fout" ? "Audiostoring" :
      verbonden ? (status.effecten_aan ? "Verbonden, effecten aan" : "Verbonden, alleen microfoon") : "Niet verbonden";
    element("kleine-status").querySelector("span").textContent = " " + omschrijving;
    element("kleine-status").classList.toggle("actief", verbonden);
    werkVerbindingsknopBij(status);
    // De live-stemmeters worden door de niveaustroom gevoed. De trage
    // statusroute mag geen oudere meting over een vers datapunt tekenen.
    element("microfoonkeuze").disabled = verbonden || bezig;
    element("knop-vernieuw").disabled = verbonden || bezig;
    werkEffectenBedieningBij();
    element("knop-monitor").setAttribute("aria-checked", String(Boolean(status.meeluisteren_aan)));
    toestand.eigenStemMonitorAan = Boolean(status.eigen_stem_horen_aan);
    toestand.eigenStemMonitorVolume = Number(status.eigen_stem_horen_volume) || 25;
    element("knop-eigen-stem").setAttribute("aria-checked", String(toestand.eigenStemMonitorAan));
    element("eigen-stem-volume").disabled = !toestand.eigenStemMonitorAan;
    if (document.activeElement !== element("eigen-stem-volume")) {
      element("eigen-stem-volume").value = String(toestand.eigenStemMonitorVolume);
      element("eigen-stem-volume-tekst").textContent = `${toestand.eigenStemMonitorVolume}%`;
    }
    const gemeten = Boolean(status.is_signaal_gemeten && verbonden);
    // De statusroute is een fallback. Een frisse 30 Hz-meting mag nooit
    // door een 200 ms oude statuswaarde worden teruggezet.
    if (!streamingIsBeschikbaar || performance.now() - laatsteOntvangstVanNiveaus > 250) {
      toonNieuweMeetwaarden(status, gemeten);
    }
    if (Number(status.limiter_terugvallen) > toestand.laatsteLimiterFouten) {
      toestand.laatsteLimiterFouten = Number(status.limiter_terugvallen);
      toonMelding("De piekbeveiliging werkt niet volledig. De noodbegrenzing blijft actief. Bekijk het logboek.", true);
    }
    element("buffer-status").textContent = `Bufferproblemen: ${status.bufferproblemen}`;
    element("monitor-melding").textContent = status.meeluisterfout
      ? `Monitorfout: ${status.meeluisterfout}` : status.meeluisteruitvoer || "Eigen geluidsuitvoer";
    let extra = "Kies je microfoon en klik op Verbinden.";
    if (verbonden) extra = status.geluid_voorbereiden
      ? `Geluid wordt voorbereid: ${status.geluid_voorbereiden}`
      : (status.huidig_geluid ? `Speelt: ${status.huidig_geluid}` : `Verbonden met ${status.microfoon}`);
    if (bezig) extra = status.toestand === "wordt_verbonden"
      ? `Audioverbinding starten, poging ${status.startpoging} van ${status.maximale_startpogingen}`
      : "Verbinding wordt afgesloten.";
    if (status.toestand === "fout") extra = `Audiofout: ${status.fout || "Zie software.jsonl"}`;
    element("extra-status").textContent = extra;
    if (status.laatste_afspeelfout && status.laatste_afspeelfout !== toestand.laatsteAudiofout) {
      toestand.laatsteAudiofout = status.laatste_afspeelfout;
      toonMelding(`Afspeelfout: ${status.laatste_afspeelfout}`, true);
    }
    werkLiveGeluidBij(status);
    pasWachtendBasisvolumeToe(status);
    werkVolumeSamenhangBij();
  } catch (fout) {
    if (appAfsluitingAangevraagd) return;
    // Een losse statusfout mag een werkende snelle niveaustroom niet wissen.
    if (!streamingIsBeschikbaar || performance.now() - laatsteOntvangstVanNiveaus > 250) {
      toonNieuweMeetwaarden({}, false);
    }
    element("extra-status").textContent = leesbareBrowsermelding(fout.message);
  } finally { toestand.bezetteStatusaanvraag = false; }
}

async function importeerGekozenBestanden(bestanden) {
  if (toestand.bezigMetImport || !bestanden.length) return;
  toestand.bezigMetImport = true;
  element("knop-importeer").disabled = true;
  let goed = 0, mislukt = 0, laatstToegevoegd = null;
  try {
    for (const bestand of bestanden) {
      try {
        if (bestand.size > 250 * 1024 * 1024) throw new Error("Bestand is groter dan 250 MiB.");
        element("knop-importeer").textContent = `Laden ${goed + mislukt + 1}/${bestanden.length}`;
        const antwoord = await vraagAanPython("POST", "/api/geluiden/importeer", undefined, bestand);
        laatstToegevoegd = antwoord.geluid_id;
        goed++;
      } catch (fout) {
        mislukt++;
        toonMelding(`${bestand.name}: ${fout.message}`, true);
      }
    }
  } finally {
    toestand.bezigMetImport = false;
    element("knop-importeer").disabled = false;
    element("knop-importeer").textContent = "Toevoegen";
    element("bestandkiezer").value = "";
    await laadBibliotheekOpnieuw();
    toonMelding(`${goed} toegevoegd${mislukt ? `, ${mislukt} mislukt` : ""}.`);
    if (goed === 1 && laatstToegevoegd) openBewerkvenster(laatstToegevoegd);
  }
}

function openFavorietKiezer(plek) {
  toestand.gekozenPlek = plek;
  element("toewijzen-titel").textContent = `Favoriet ${String(plek).padStart(2, "0")} invullen`;
  const keuzes = element("toewijzen-keuzes");
  keuzes.replaceChildren();
  for (const geluid of toestand.geluiden) {
    const knop = maakElement("button", "toewijzen-keuze", geluid.naam);
    knop.addEventListener("click", () => voerGebruikersactieUit("Favoriet instellen", async () => {
      await vraagAanPython("POST", `/api/favorieten/${plek}`, { geluid_id: geluid.id });
      element("dialoog-toewijzen").close();
      await laadBibliotheekOpnieuw();
    }));
    keuzes.appendChild(knop);
  }
  if (!toestand.geluiden.length) keuzes.appendChild(maakElement("p", "lege-lijst", "Voeg eerst een geluid toe."));
  element("dialoog-toewijzen").showModal();
}

/*
  Groepen zijn filters en geen fysieke bestandsmappen. Een geluid kan dus
  op meerdere plekken voorkomen, zonder extra kopieën op schijf te maken.
*/
function groepEnSubgroepen(groepId, verzameld = new Set()) {
  if (verzameld.has(groepId)) return verzameld;
  verzameld.add(groepId);
  for (const submap of toestand.groepen.filter((groep) => groep.ouder_id === groepId)) {
    groepEnSubgroepen(submap.id, verzameld);
  }
  return verzameld;
}
function hoortBijGroep(geluid, groepId) {
  return (geluid.groep_ids || []).some((id) => groepEnSubgroepen(groepId).has(id));
}
function getoondeGroepenAlsBoom() {
  const lijst = [];
  const wandel = (ouderId, diepte, gezien) => {
    for (const groep of toestand.groepen.filter((g) => (g.ouder_id || null) === ouderId)
      .sort((a,b) => element('mappen-sortering').value==='populair'
        ? populairteitGroep(b.id)-populairteitGroep(a.id) || a.naam.localeCompare(b.naam,'nl',{sensitivity:'base'})
        : a.naam.localeCompare(b.naam,'nl',{sensitivity:'base'}))) {
      if (gezien.has(groep.id)) continue;
      lijst.push({...groep, diepte});
      wandel(groep.id, diepte+1, new Set([...gezien, groep.id]));
    }
  };
  wandel(null, 0, new Set());
  // Onverwachte verweesde mappen blijven herstelbaar en zichtbaar.
  for (const groep of toestand.groepen) if (!lijst.some((x)=>x.id===groep.id)) lijst.push({...groep,diepte:0});
  return lijst;
}
function aantalInGroep(groepId) {
  return toestand.geluiden.filter((g)=>hoortBijGroep(g,groepId)).length;
}
function populairteitGroep(groepId) {
  return toestand.geluiden.filter((g)=>hoortBijGroep(g,groepId))
    .reduce((n,g)=>n+(Number(g.aantal_afgespeeld)||0),0);
}
function sorteerGeluiden(geluiden, soort) {
  const naam = (a,b)=>a.naam.localeCompare(b.naam,'nl',{numeric:true,sensitivity:'base'});
  geluiden.sort((a,b)=>soort==='populair'
    ? (Number(b.aantal_afgespeeld||0)-Number(a.aantal_afgespeeld||0))||naam(a,b)
    : soort==='naam-terug' ? -naam(a,b) : naam(a,b));
  return geluiden;
}
function maakGroepenZichtbaar() {
  const lijst = element('groepen-lijst');
  const zoekmap = normaliseerZoektekst(element('groepen-zoeken')?.value || '').trim();
  lijst.replaceChildren();
  const voegToe = (groep, naam, id, aantal, diepte=0) => {
    if (zoekmap && !normaliseerZoektekst(naam).includes(zoekmap)) return;
    const rij = maakElement('div','groep-filterrij');
    const knop = maakElement('button', `groep-filter${toestand.actieveGroep===id?' gekozen':''}`);
    knop.type='button'; knop.title=naam;
    knop.style.paddingLeft=`${11+Math.min(diepte,8)*13}px`;
    knop.append(maakElement('span','groep-filternaam',naam),maakElement('span','groep-aantal',String(aantal)));
    knop.addEventListener('click',()=>{
      toestand.actieveGroep=id;
      dashboardAfspeelFilter = "alle";
      if (groep) registreerGroepsgebruik(id);
      maakGroepenZichtbaar();maakBibliotheekZichtbaar();
    });
    if (groep) {
      knop.addEventListener('dragover',(e)=>{e.preventDefault();e.dataTransfer.dropEffect='move'});
      knop.addEventListener('drop',(e)=>verwerkMapDrop(e,id));
    }
    rij.appendChild(knop);
    if (groep) {
      const menu=maakElement('button','groep-acties','…');
      menu.type='button';menu.title=`Map ${naam} aanpassen`;
      menu.addEventListener('click',()=>beheerMap(groep));
      rij.appendChild(menu);
    }
    lijst.appendChild(rij);
  };
  voegToe(null,'Alle geluiden','alle',toestand.geluiden.length);
  voegToe(null,'Zonder map','zonder',toestand.geluiden.filter(g=>!(g.groep_ids||[]).length).length);
  for(const groep of getoondeGroepenAlsBoom())
    voegToe(groep,groep.naam,groep.id,aantalInGroep(groep.id),groep.diepte);
  if (!lijst.children.length) lijst.appendChild(maakElement('p', 'lege-mappen', 'Geen mappen gevonden.'));
}

function bepaalEditorBronduur(geluid) {
  const gemeten = Number(geluid.bronduur);
  return Number.isFinite(gemeten) && gemeten > 0 ? gemeten : 120;
}

function geefGeselecteerdeFragmentduur() {
  return Math.max(0, Number(element("trim-eind").value) - Number(element("trim-begin").value));
}

function stelSelectieInEditorIn(begin, einde, aanpassing = "begin") {
  const geluid = vindGeluid(toestand.gekozenGeluid);
  if (!geluid) return;
  const bronduur = bepaalEditorBronduur(geluid);
  const minimaal = Math.min(0.001, bronduur);
  begin = Math.max(0, Math.min(bronduur - minimaal, Number(begin) || 0));
  einde = Math.max(minimaal, Math.min(bronduur, Number(einde) || minimaal));
  // Maximaal 120 seconden, maar ook nooit langer dan er nog in de bron zit.
  if (aanpassing === "begin") {
    einde = Math.max(begin + minimaal, Math.min(einde, begin + 120, bronduur));
  } else {
    begin = Math.min(begin, einde - minimaal);
    begin = Math.max(begin, einde - 120, 0);
  }
  const duur = Math.max(minimaal, einde - begin);
  element("trim-begin").value = String(begin);
  element("trim-eind").value = String(einde);
  element("bewerken-start").value = (Math.round(begin * 1000) / 1000).toFixed(3);
  element("bewerken-duur").value = (Math.round(duur * 1000) / 1000).toFixed(3);
  element("trim-zone").style.left = `${begin / bronduur * 100}%`;
  element("trim-zone").style.width = `${duur / bronduur * 100}%`;
  element("trim-linkerlabel").textContent = netteTijdMetMilliseconden(begin);
  element("trim-rechterlabel").textContent = netteTijdMetMilliseconden(einde);
  element("selectie-duur").textContent = `${netteTijdMetMilliseconden(duur)} geselecteerd`;
  tekenEditorKnipranden();
  element("editor-hint").textContent = duur >= 119.99
    ? "Maximale fragmentduur: 2:00. Het origineel blijft intact."
    : `Dit fragment duurt ${netteTijd(duur)}. Het origineel blijft intact.`;
  // De selectie kan tijdens het beluisteren veranderen. Pauzeer in dat geval
  // eerst, zodat er nooit onbedoeld geluid buiten het nieuwe fragment klinkt.
  if (toestand.editorVoorbeeld?.speelt) pauzeerEditorPreview("selectie_aangepast");
  werkEditorAfspeelpositieBij(toestand.editorAfspeelpositie, true);
  // Een grenssleper hoeft de MP3 niet bij iedere millimeter opnieuw
  // te decoderen. De golfvorm blijft staan; alleen de grens verschuift.
}

/*
  De server levert tot 960 echte meetkolommen, inclusief RMS-envelop.
  Dat is meer detail dan de vroegere 160 balkjes. Een wijziging van de
  selectie wordt kort gedebounced om herhaald MP3-decoden te voorkomen.
*/
function planGolfvormTekenen(begin, duur) {
  if (toestand.editorGolfvormWachttijd) clearTimeout(toestand.editorGolfvormWachttijd);
  const volgnummer = ++toestand.golfvormVolgnummer;
  toestand.editorGolfvormWachttijd = setTimeout(async () => {
    const geluidId = toestand.gekozenGeluid;
    if (!geluidId || !element("dialoog-bewerken").open) return;
    const breedte = element("editor-golfvorm-gebied").clientWidth || 760;
    const resolutie = Math.max(300, Math.min(960, Math.round(breedte * 1.1)));
    try {
      const parameters = new URLSearchParams({ begin: String(begin), duur: String(duur), resolutie: String(resolutie) });
      const gegevens = await vraagAanPython("GET", `/api/geluiden/${geluidId}/golfvorm?${parameters}`);
      if (volgnummer !== toestand.golfvormVolgnummer || geluidId !== toestand.gekozenGeluid) return;
      toestand.editorGolfvormData = gegevens;
      tekenDeEchteGolfvorm(gegevens.pieken, gegevens.rms);
    } catch (fout) {
      if (volgnummer !== toestand.golfvormVolgnummer) return;
      console.warn("Golfvorm niet beschikbaar", fout);
      registreerBrowserfout("Golfvorm van fragment kon niet worden opgehaald", fout.stack || "");
      toestand.editorGolfvormData = null;
      tekenDeEchteGolfvorm([]);
    }
  }, 260);
}

function tekenDeEchteGolfvorm(pieken, gemiddelden = []) {
  const canvas = element("golfvorm-canvas");
  const context = canvas.getContext("2d");
  if (!context) return;
  const dpi = Math.min(window.devicePixelRatio || 1, 2);
  const breedte = Math.max(200, canvas.clientWidth || 760);
  const hoogte = canvas.clientHeight || 152;
  canvas.width = Math.round(breedte * dpi);
  canvas.height = Math.round(hoogte * dpi);
  context.setTransform(dpi, 0, 0, dpi, 0, 0);
  context.clearRect(0, 0, breedte, hoogte);
  context.fillStyle = "#111e25";
  context.fillRect(0, 0, breedte, hoogte);
  const midden = hoogte / 2;
  context.strokeStyle = "rgba(148,181,191,.12)";
  context.beginPath(); context.moveTo(0, midden); context.lineTo(breedte, midden); context.stroke();
  if (!pieken?.length) {
    context.font = "12px Segoe UI, sans-serif";
    context.textAlign = "center";
    context.fillStyle = "#839da5";
    context.fillText("Golfvorm wordt geladen", breedte / 2, midden + 5);
    return;
  }
  const maxhoogte = midden - 12;
  const stap = breedte / pieken.length;
  const tekenEnvelop = (waarden, vulkleur, lijnkleur) => {
    context.beginPath();
    waarden.forEach((waarde, index) => {
      const x = (index + .5) * stap;
      const y = midden - Math.max(.75, Math.min(1, Math.max(0, Number(waarde) || 0)) * maxhoogte);
      if (index === 0) context.moveTo(x, y);
      else context.lineTo(x, y);
    });
    for (let index = waarden.length - 1; index >= 0; index--) {
      const x = (index + .5) * stap;
      const y = midden + Math.max(.75, Math.min(1, Math.max(0, Number(waarden[index]) || 0)) * maxhoogte);
      context.lineTo(x, y);
    }
    context.closePath();
    context.fillStyle = vulkleur;
    context.fill();
    context.strokeStyle = lijnkleur;
    context.lineWidth = .8;
    context.stroke();
  };
  tekenEnvelop(pieken, "rgba(80,181,171,.20)", "rgba(104,209,192,.68)");
  if (gemiddelden?.length === pieken.length) {
    tekenEnvelop(gemiddelden, "rgba(117,221,202,.50)", "rgba(168,244,228,.65)");
  }
}

function toonDoorzoekbareGroepenInEditor() {
  const lijst = element('groepen-in-editor');
  lijst.replaceChildren();
  const zoekterm = element('editor-groepen-zoeken').value.trim().toLocaleLowerCase('nl-NL');
  const groepen = getoondeGroepenAlsBoom();
  const bijId = new Map(toestand.groepen.map((groep) => [groep.id, groep]));
  const maakPad = (groep) => {
    const namen = [groep.naam];
    const gezien = new Set([groep.id]);
    let ouder = groep.ouder_id;
    while (ouder && !gezien.has(ouder)) {
      gezien.add(ouder);
      const boven = bijId.get(ouder);
      if (!boven) break;
      namen.unshift(boven.naam);
      ouder = boven.ouder_id;
    }
    return namen.join(' / ');
  };
  const zichtbaar = groepen.filter((groep) => maakPad(groep).toLocaleLowerCase('nl-NL').includes(zoekterm));
  for (const groep of zichtbaar) {
    const label = maakElement('label', 'groep-keuze');
    label.style.paddingLeft = `${10 + Math.min(groep.diepte, 8) * 15}px`;
    const vakje = maakElement('input');
    vakje.type = 'checkbox';
    vakje.value = groep.id;
    vakje.checked = toestand.editorGroepenKeuze.has(groep.id);
    vakje.addEventListener('change', () => {
      if (vakje.checked) toestand.editorGroepenKeuze.add(groep.id);
      else toestand.editorGroepenKeuze.delete(groep.id);
      werkEditorGroepstellerBij();
    });
    const naam = maakElement('span', '', groep.naam);
    label.title = maakPad(groep);
    label.append(vakje, naam);
    lijst.appendChild(label);
  }
  if (!zichtbaar.length) {
    lijst.appendChild(maakElement('span', 'geen-groep-hint',
      groepen.length ? 'Geen mappen gevonden.' : 'Maak je eerste map in de bibliotheek.'));
  }
  werkEditorGroepstellerBij();
}

function werkEditorGroepstellerBij() {
  element('editor-groepen-teller').textContent =
    `${toestand.editorGroepenKeuze.size} van ${toestand.groepen.length} mappen gekozen`;
}

function vulGroepskeuzesInDeEditor(geluid) {
  toestand.editorGroepenKeuze = new Set(geluid.groep_ids || []);
  element('editor-groepen-zoeken').value = '';
  toonDoorzoekbareGroepenInEditor();
}

function toonMediaInEditor(geluid) {
  const venster = element("editor-media");
  venster.replaceChildren();
  if (geluid.is_video && geluid.mediabron) {
    const video = document.createElement("video");
    video.src = geluid.mediabron; video.preload = "metadata";
    video.muted = true; video.playsInline = true;
    video.addEventListener("loadedmetadata", () => {
      video.currentTime = Math.min(geluid.beginpositie || 0, Math.max(0, video.duration - 0.05));
    }, { once: true });
    venster.appendChild(video);
  } else if (geluid.afbeelding) {
    // Gebruik bij GIF in rust een stil eerste frame. De GIF start pas
    // tijdens een echte preview of een actieve afspeelbeurt.
    venster.appendChild(maakAfbeelding(geluid.miniatuur || geluid.afbeelding));
  } else {
    venster.appendChild(maakElement("div", "editor-media-placeholder", "AUDIO"));
  }
}

function openBewerkvenster(geluidId) {
  const geluid = vindGeluid(geluidId);
  if (!geluid) return;
  stopEditorPreview("editor_ander_geluid");
  toestand.gekozenGeluid = geluidId;
  toestand.editorGolfvormData = null;
  element("bewerken-naam").value = geluid.naam;
  element("bewerken-beeld").value = geluid.beeldvoorkeur || "automatisch";
  element("bewerken-volume").value = String(Math.round((geluid.volume ?? 1) * 100));
  element("volume-uitleg").textContent = `${Math.round((geluid.volume ?? 1) * 100)}%`;
  toonMediaInEditor(geluid);
  vulGroepskeuzesInDeEditor(geluid);
  const bronduur = bepaalEditorBronduur(geluid);
  element("bewerken-beschrijving").value = geluid.beschrijving || "";
  element("bewerken-gesproken-tekst").value = geluid.gesproken_tekst || "";
  element("bewerken-zoekwoorden").value = geluid.zoekwoorden || "";
  element("bronduur-label").textContent = geluid.bronduur === null ? "Bronduur onbekend" : `Bron ${netteTijd(bronduur)}`;
  element("trim-begin").max = String(bronduur);
  element("trim-eind").max = String(bronduur);
  element("bewerken-start").max = String(bronduur);
  element("dialoog-bewerken").showModal();
  const begin = Math.min(Math.max(0, Number(geluid.beginpositie) || 0), Math.max(0, bronduur - .1));
  const duur = Math.min(120, Number(geluid.fragmentduur ?? geluid.maximale_duur) || 120, bronduur - begin);
  toestand.editorAfspeelpositie = begin;
  toestand.editorVensterBegin = bronduur > 120 ? Math.max(0, begin - 3) : 0;
  toestand.editorVensterDuur = Math.min(120, bronduur - toestand.editorVensterBegin);
  stelSelectieInEditorIn(begin, begin + Math.max(.001, duur), "begin");
  beperkEditorVenster(toestand.editorVensterBegin, toestand.editorVensterDuur);
  werkEditorKnoppenBij("Gereed");
  werkVolumeSamenhangBij();
}

/*
  Fragmenteditor: de afspeelkop gebruikt de echte media.currentTime.
  De browser luistert alleen lokaal; deze functies raken VB-CABLE niet.
  Het trimvenster bepaalt waar je mag luisteren, de cursor waar je begint.
*/
/*
  De editor bewaart tijden met drie decimalen. Dat is een tijdsresolutie
  van 1 ms, maar de codec/browser bepaalt de feitelijke seek-precisie.
*/
function netteTijdMetMilliseconden(seconden) {
  const milliseconden = Math.max(0, Math.round((Number(seconden) || 0) * 1000));
  const minuten = Math.floor(milliseconden / 60000);
  const heleSeconden = Math.floor(milliseconden / 1000) % 60;
  return `${minuten}:${String(heleSeconden).padStart(2, "0")}.${String(milliseconden % 1000).padStart(3, "0")}`;
}

function beperkEditorVenster(begin, duur) {
  const geluid = vindGeluid(toestand.gekozenGeluid);
  const totaal = geluid ? bepaalEditorBronduur(geluid) : 120;
  const span = Math.min(totaal, Math.max(0.05, Number(duur) || totaal));
  const links = Math.min(Math.max(0, Number(begin) || 0), Math.max(0, totaal - span));
  toestand.editorVensterBegin = links;
  toestand.editorVensterDuur = span;
  element("editor-zoom-tekst").textContent = span >= totaal - 0.001
    ? "Volledige bron" : `${netteTijdMetMilliseconden(span)} zichtbaar`;
  element("editor-venster-links").textContent = netteTijdMetMilliseconden(links);
  element("editor-venster-rechts").textContent = netteTijdMetMilliseconden(links + span);
  tekenEditorKnipranden();
  planGolfvormTekenen(links, span);
}

function zoomInEditor(factor, rondSeconde = toestand.editorAfspeelpositie) {
  const links = toestand.editorVensterBegin;
  const oud = toestand.editorVensterDuur;
  const midden = Math.max(links, Math.min(links + oud, rondSeconde));
  const nieuw = oud * factor;
  beperkEditorVenster(midden - (midden - links) * factor, nieuw);
}

function tekenEditorKnipranden() {
  const gebied = element("editor-golfvorm-gebied");
  if (!gebied) return;
  const links = toestand.editorVensterBegin;
  const span = Math.max(0.001, toestand.editorVensterDuur);
  const begin = Number(element("trim-begin").value);
  const einde = Number(element("trim-eind").value);
  const percentage = (tijd) => (tijd - links) / span * 100;
  const toonBegin = begin >= links && begin <= links + span;
  const toonEinde = einde >= links && einde <= links + span;
  const start = Math.max(0, Math.min(100, percentage(begin)));
  const stop = Math.max(0, Math.min(100, percentage(einde)));
  const zone = element("editor-selectie-venster");
  zone.style.left = `${start}%`;
  zone.style.width = `${Math.max(0, stop - start)}%`;
  for (const [id, zichtbaar, plek] of [
    ["editor-grens-begin", toonBegin, begin], ["editor-grens-einde", toonEinde, einde]
  ]) {
    const grens = element(id);
    grens.style.display = zichtbaar ? "block" : "none";
    grens.style.left = `${percentage(plek)}%`;
  }
  // Plaats de cursor met dezelfde zichtbare tijdschaal als de golfvorm,
  // maar laat de voortgangsteller de hele selectie blijven beschrijven.
  const cursor = element("editor-afspeelkop");
  const positie = toestand.editorAfspeelpositie;
  cursor.style.display = positie < links || positie > links + span ? "none" : "block";
  cursor.style.left = `${percentage(positie)}%`;
}

function geefSecondeBijPointer(gebeurtenis) {
  const grenzen = element("editor-afspeelvlak").getBoundingClientRect();
  const aandeel = Math.max(0, Math.min(1, (gebeurtenis.clientX - grenzen.left) / Math.max(1, grenzen.width)));
  return toestand.editorVensterBegin + aandeel * toestand.editorVensterDuur;
}

function netteTijdMetTienden(seconden) {
  const veilig = Math.max(0, Number.isFinite(seconden) ? seconden : 0);
  const tienden = Math.floor(veilig * 10 + 0.00001);
  return `${Math.floor(tienden / 600)}:${String(Math.floor(tienden / 10) % 60).padStart(2, "0")}.${tienden % 10}`;
}

function geefEditorSelectie() {
  const begin = Number(element("trim-begin").value);
  const einde = Number(element("trim-eind").value);
  if (!Number.isFinite(begin) || !Number.isFinite(einde) || einde <= begin) {
    throw new Error("Geen geldige fragmentselectie. Controleer begin en einde.");
  }
  return { begin, einde, duur: einde - begin };
}

function werkEditorAfspeelpositieBij(positie, binnenSelectieHouden = false) {
  const { begin, einde, duur } = geefEditorSelectie();
  const veilig = Number.isFinite(Number(positie)) ? Number(positie) : begin;
  const plek = Math.max(begin, Math.min(einde, veilig));
  toestand.editorAfspeelpositie = plek;
  const aandeel = duur > 0 ? (plek - begin) / duur : 0;
  tekenEditorKnipranden();
  element("editor-voortgang-vulling").style.width = `${aandeel * 100}%`;
  element("editor-positie-tijd").textContent = netteTijdMetMilliseconden(plek - begin);
  element("editor-selectie-eindtijd").textContent = netteTijdMetMilliseconden(duur);
  const vlak = element("editor-afspeelvlak");
  vlak.setAttribute("aria-valuemax", duur.toFixed(3));
  vlak.setAttribute("aria-valuenow", (plek - begin).toFixed(3));
  vlak.setAttribute("aria-valuetext", `${netteTijdMetMilliseconden(plek - begin)} van ${netteTijdMetMilliseconden(duur)}`);
  if (binnenSelectieHouden && toestand.editorVoorbeeld?.speler?.readyState >= 1) {
    // Niet blijven zoeken tijdens een lopende requestAnimationFrame. Alleen
    // aanpassen als de selectie of het eigenlijke sleepdoel echt is gewijzigd.
    const speler = toestand.editorVoorbeeld.speler;
    if (Math.abs(speler.currentTime - plek) > 0.045) speler.currentTime = plek;
  }
}

function werkEditorKnoppenBij(tekst = "Gereed") {
  const voorbeeld = toestand.editorVoorbeeld;
  const speelt = Boolean(voorbeeld?.speelt);
  const laden = Boolean(voorbeeld?.laden);
  const liveGeluid = toestand.editorUitzendGeluidId === toestand.gekozenGeluid &&
    (toestand.live?.geluidId === toestand.gekozenGeluid ||
     toestand.verwachtGeluid?.id === toestand.gekozenGeluid ||
     toestand.status?.huidig_geluid_id === toestand.gekozenGeluid);
  element('knop-editor-preview').textContent = laden ? 'Laden…' : speelt ? 'Pauzeren' : 'Preview';
  element('knop-editor-preview').disabled = laden;
  element('knop-editor-uitzenden').disabled = laden;
  element('knop-editor-uitzenden').setAttribute('aria-pressed', String(Boolean(liveGeluid)));
  element('knop-editor-stop').disabled = !voorbeeld && !liveGeluid;
  element('editor-speelstatus').textContent = tekst;
}

function annuleerEditorAfspeelAnimatie() {
  if (toestand.editorAfspeelAnimatie !== null) {
    cancelAnimationFrame(toestand.editorAfspeelAnimatie);
    toestand.editorAfspeelAnimatie = null;
  }
}

function geefGeluidstijdInEditor(voorbeeld) {
  if (!voorbeeld?.speelt || voorbeeld.gestartOp === null) return 0;
  return Math.min(120, Math.max(0, (performance.now() - voorbeeld.gestartOp) / 1000));
}

function pauzeerEditorPreview(reden = "editor_gepauzeerd") {
  const voorbeeld = toestand.editorVoorbeeld;
  if (!voorbeeld) return;
  const wasActief = voorbeeld.speelt;
  const duur = wasActief ? geefGeluidstijdInEditor(voorbeeld) : 0;
  voorbeeld.speelt = false;
  voorbeeld.gestartOp = null;
  voorbeeld.speler.pause();
  annuleerEditorAfspeelAnimatie();
  if (wasActief) registreerPreviewBijPython(voorbeeld.geluidId, "gestopt", duur, reden, voorbeeld.afspeelbeurt);
  if (!toestand.editorIsAanHetSlepen) {
    werkEditorAfspeelpositieBij(voorbeeld.speler.currentTime);
  }
  // Een GIF beweegt alleen zolang de preview daadwerkelijk speelt.
  const geluid = vindGeluid(voorbeeld.geluidId);
  if (geluid && !geluid.is_video && geluid.afbeelding?.toLowerCase().endsWith(".gif")) {
    toonMediaInEditor(geluid);
  }
  werkEditorKnoppenBij(reden === "editor_einde" ? "Einde fragment" : "Gepauzeerd");
}

function stopEditorPreview(reden = "editor_gestopt", resetPositie = false) {
  const voorbeeld = toestand.editorVoorbeeld;
  if (voorbeeld) {
    pauzeerEditorPreview(reden);
    toestand.editorVoorbeeld = null;
    voorbeeld.speler.pause();
    if (voorbeeld.audioBus) voorbeeld.audioBus.versterker.gain.value = 0;
    // Het audio-element kan los in geheugen hangen; laat de decoder vrij.
    // Een video-element in de editor wordt hieronder opnieuw opgebouwd.
    voorbeeld.speler.removeAttribute("src");
    voorbeeld.speler.load();
    if (element("dialoog-bewerken").open) {
      const geluid = vindGeluid(voorbeeld.geluidId);
      if (geluid) toonMediaInEditor(geluid);
    }
  }
  annuleerEditorAfspeelAnimatie();
  if (resetPositie && element("dialoog-bewerken").open && toestand.gekozenGeluid) {
    werkEditorAfspeelpositieBij(Number(element("trim-begin").value));
  }
  werkEditorKnoppenBij(resetPositie ? "Gereed" : "Gepauzeerd");
}

function blijfAfspeelpositieVanEditorVolgen(voorbeeld) {
  annuleerEditorAfspeelAnimatie();
  const frame = () => {
    toestand.editorAfspeelAnimatie = null;
    if (toestand.editorVoorbeeld !== voorbeeld || !voorbeeld.speelt || !element("dialoog-bewerken").open) return;
    const { einde } = geefEditorSelectie();
    const speler = voorbeeld.speler;
    if (!toestand.editorIsAanHetSlepen) werkEditorAfspeelpositieBij(speler.currentTime);
    if (speler.ended || speler.currentTime >= einde - 0.025) {
      pauzeerEditorPreview("editor_einde");
      werkEditorAfspeelpositieBij(einde);
      return;
    }
    toestand.editorAfspeelAnimatie = requestAnimationFrame(frame);
  };
  toestand.editorAfspeelAnimatie = requestAnimationFrame(frame);
}

function wachtTotMediabestandBruikbaarIs(speler) {
  if (speler.readyState >= 1) return Promise.resolve();
  return new Promise((resolve, reject) => {
    let klaar = false;
    const afronden = (fout = null) => {
      if (klaar) return;
      klaar = true;
      clearTimeout(wachttijd);
      speler.removeEventListener("loadedmetadata", gereed);
      speler.removeEventListener("error", mislukt);
      if (fout) reject(fout);
      else resolve();
    };
    const gereed = () => afronden();
    const mislukt = () => afronden(new Error("Kan dit mediabestand niet lezen."));
    const wachttijd = setTimeout(() => afronden(new Error("Mediabestand reageert niet binnen 8 seconden.")), 8000);
    speler.addEventListener("loadedmetadata", gereed);
    speler.addEventListener("error", mislukt);
  });
}

// Live- en editorpreview delen dezelfde afspeelwachtrij. Een editorpreview
// mag niet tegelijkertijd met uitzending via VB-CABLE lopen.
function ontgrendelEditorAudioBijKlik() {
  const AudioContextKlasse = window.AudioContext || window.webkitAudioContext;
  if (!AudioContextKlasse) return;
  try {
    if (!previewAudioContext) previewAudioContext = new AudioContextKlasse();
    previewAudioContext.resume().catch(() => {});
  } catch (_) { /* Foutmelding volgt in de gewone previewroute. */ }
}

function startEditorPreviewExclusief() {
  if (toestand.editorVoorbeeld?.speelt) return voerGebruikersactieUit('Preview pauzeren', speelEditorSelectieLokaal);
  ontgrendelEditorAudioBijKlik();
  return planExclusieveSpeleractie('Editorpreview starten', 'preview', async () => {
    // Afspelen op een gekozen positie betekent geen nieuw soundboardgeluid.
    await vraagAanPython('POST', '/api/stop', {});
    let gestopt = false;
    for (let poging = 0; poging < 40; poging++) {
      if (toestand.gewensteSpelmodus !== 'preview') return;
      const status = await vraagAanPython('GET', '/api/status');
      if (!status.huidig_geluid_id && !status.geluid_voorbereiden) {
        gestopt = true;
        break;
      }
      await new Promise((klaar) => setTimeout(klaar, 35));
    }
    if (!gestopt) throw new Error('Het uitgezonden geluid stopt nog. Probeer opnieuw.');
    toestand.editorUitzendGeluidId = null;
    if (toestand.live?.animatie) cancelAnimationFrame(toestand.live.animatie);
    toestand.live?.videobediening?.stop();
    toestand.live = null;
    toestand.verwachtGeluid = null;
    await speelEditorSelectieLokaal();
  });
}

function startEditorUitzenden() {
  const geluidId = toestand.gekozenGeluid;
  const selectie = geefEditorSelectie();
  const volume = Number(element('bewerken-volume').value) / 100;
  stopEditorPreview('editor_uitzenden');
  const instelling = {beginpositie: selectie.begin, maximale_duur: selectie.duur, volume};
  return beginGeluidAfspelen(geluidId, instelling);
}

function stopEditorGeluid() {
  stopEditorPreview('editor_gestopt', true);
  const liveVanDezeEditor = toestand.editorUitzendGeluidId === toestand.gekozenGeluid &&
    (toestand.live?.geluidId === toestand.gekozenGeluid ||
     toestand.verwachtGeluid?.id === toestand.gekozenGeluid ||
     toestand.status?.huidig_geluid_id === toestand.gekozenGeluid);
  if (liveVanDezeEditor) {
    return planExclusieveSpeleractie('Uitzending stoppen', 'gestopt', async () => {
      await vraagAanPython('POST', '/api/stop', {});
      toestand.editorUitzendGeluidId = null;
      toestand.verwachtGeluid = null;
      if (toestand.live?.animatie) cancelAnimationFrame(toestand.live.animatie);
      toestand.live?.videobediening?.stop();
      toestand.live = null;
      toonStilMediascherm();
      werkEditorKnoppenBij('Uitzending gestopt');
    });
  }
  werkEditorKnoppenBij('Gereed');
}

async function herberekenEditorVoorbeeldvolume() {
  pasEditorBasisvolumeAan();
}


async function speelEditorSelectieLokaal() {
  const geluid = vindGeluid(toestand.gekozenGeluid);
  if (!geluid?.mediabron || !geluid.bestand_gevonden) {
    throw new Error("Het bronbestand ontbreekt of kan niet worden geopend.");
  }
  if (toestand.editorVoorbeeld?.speelt) {
    pauzeerEditorPreview();
    return;
  }
  const selectie = geefEditorSelectie();
  if (!toestand.editorVoorbeeld) {
    // Een editorpreview hoort de reeds lopende kaartpreview af te sluiten,
    // anders zou de browser twee lokale geluiden tegelijk maken.
    if (toestand.preview) stopPreview("editor_gestart");
    const speler = geluid.is_video
      ? element("editor-media").querySelector("video") || document.createElement("video")
      : new Audio();
    speler.preload = "metadata";
    speler.playsInline = true;
    speler.volume = 1;
    speler.src = geluid.mediabron;
    const voorbeeld = {
      speler, geluidId: geluid.id, speelt: false, laden: false,
      basisvolume: Number(element('bewerken-volume').value) / 100,
      gestartOp: null,
    };
    toestand.editorVoorbeeld = voorbeeld;
    speler.addEventListener("ended", () => {
      if (toestand.editorVoorbeeld !== voorbeeld) return;
      pauzeerEditorPreview("editor_einde");
      werkEditorAfspeelpositieBij(geefEditorSelectie().einde);
    });
    speler.addEventListener("error", () => {
      if (toestand.editorVoorbeeld !== voorbeeld || !voorbeeld.speelt) return;
      registreerBrowserfout("Editorpreview kon audio niet verder afspelen", String(speler.error?.message || "MediaError"));
      pauzeerEditorPreview("editor_mediafout");
      toonMelding("De lokale preview is gestopt door een mediafout.", true);
    });
  }
  const voorbeeld = toestand.editorVoorbeeld;
  voorbeeld.laden = true;
  werkEditorKnoppenBij("Laden…");
  try {
    const { bus, activering } = maakPreviewAudioBus(voorbeeld.speler);
    voorbeeld.audioBus = bus;
    const selectie = geefEditorSelectie();
    const normalisatieVerzoek = leesPreviewNormalisatie(geluid.id, selectie.begin,
      selectie.einde - selectie.begin, Number(element('bewerken-volume').value) / 100);
    await wachtTotMediabestandBruikbaarIs(voorbeeld.speler);
    const analyse = await normalisatieVerzoek;
    await activering;
    if (toestand.editorVoorbeeld !== voorbeeld) return;
    voorbeeld.normalisatieData = analyse;
    voorbeeld.basisvolume = Number(element('bewerken-volume').value) / 100;
    gebruikPreviewNormalisatie(voorbeeld);
    if (toestand.editorVoorbeeld !== voorbeeld) return;
    // Einde bereikt? Dan start een volgende klik weer aan het begin van de
    // selectie. Bij een zelf verplaatste cursor spelen we vanaf die plek.
    const huidigeSelectie = geefEditorSelectie();
    let plek = toestand.editorAfspeelpositie;
    if (plek >= huidigeSelectie.einde - 0.03) plek = huidigeSelectie.begin;
    plek = Math.max(huidigeSelectie.begin, Math.min(huidigeSelectie.einde - .01, plek));
    voorbeeld.speler.currentTime = plek;
    // Anders blijft een MP4 met het bestaande stille miniatuur-element gedempt.
    voorbeeld.speler.muted = false;
    await voorbeeld.speler.play();
    if (toestand.editorVoorbeeld !== voorbeeld) {
      voorbeeld.speler.pause();
      return;
    }
    voorbeeld.laden = false;
    voorbeeld.speelt = true;
    voorbeeld.gestartOp = performance.now();
    voorbeeld.afspeelbeurt = crypto.randomUUID();
    registreerPreviewBijPython(geluid.id, "gestart", 0, "editor_preview", voorbeeld.afspeelbeurt);
    // Geanimeerde afbeeldingen verschijnen alleen zolang de speler loopt.
    if (!geluid.is_video && geluid.afbeelding?.toLowerCase().endsWith(".gif")) {
      element("editor-media").replaceChildren(maakAfbeelding(geluid.afbeelding));
    }
    werkEditorAfspeelpositieBij(plek);
    werkEditorKnoppenBij("Speelt af");
    blijfAfspeelpositieVanEditorVolgen(voorbeeld);
  } catch (fout) {
    if (toestand.editorVoorbeeld === voorbeeld) stopEditorPreview("editor_startfout");
    throw fout;
  }
}

/*
  Een klik of sleepactie kiest een absolute positie in de *geselecteerde*
  tijdspanne. We zetten de browsermedia pas bij loslaten op die plek; tijdens
  slepen hoeft een groot MP4-bestand dus niet continu opnieuw te seeken.
*/
function verplaatsEditorCursorMetAanwijzer(gebeurtenis) {
  const vlak = element("editor-afspeelvlak");
  const grenzen = vlak.getBoundingClientRect();
  if (grenzen.width <= 0) return;
  werkEditorAfspeelpositieBij(geefSecondeBijPointer(gebeurtenis));
}

function zetEditorMediaOpGekozenPositie() {
  const voorbeeld = toestand.editorVoorbeeld;
  if (voorbeeld?.speler?.readyState >= 1) {
    const { einde } = geefEditorSelectie();
    if (toestand.editorAfspeelpositie >= einde - .01 && voorbeeld.speelt) {
      pauzeerEditorPreview("editor_einde");
    }
    voorbeeld.speler.currentTime = toestand.editorAfspeelpositie;
  }
  const { begin } = geefEditorSelectie();
  registreerPreviewBijPython(toestand.gekozenGeluid, "verplaatst",
    Math.max(0, Math.min(120, toestand.editorAfspeelpositie - begin)), "editor_cursor_verplaatst");
}

function koppelEditorAfspeelcursor() {
  const vlak = element("editor-afspeelvlak");
  vlak.addEventListener("pointerdown", (gebeurtenis) => {
    if (gebeurtenis.button !== 0) return;
    gebeurtenis.preventDefault();
    vlak.focus({ preventScroll: true });
    toestand.editorIsAanHetSlepen = true;
    toestand.editorLaatstePointerX = gebeurtenis.clientX;
    const breedte = Math.max(1, vlak.getBoundingClientRect().width);
    const tijd = geefSecondeBijPointer(gebeurtenis);
    const selectie = geefEditorSelectie();
    const grensdrempel = toestand.editorVensterDuur * 14 / breedte;
    const afstandBegin = Math.abs(tijd - selectie.begin);
    const afstandEinde = Math.abs(tijd - selectie.einde);
    toestand.editorKniprand = Math.min(afstandBegin, afstandEinde) <= grensdrempel
      ? (afstandBegin <= afstandEinde ? "begin" : "einde") : null;
    // Lang vasthouden bij een kniprand geeft het nauwkeurige 1,5 s venster.
    // De pointer blijft daarna werken op de ingezoomde tijdschaal.
    if (toestand.editorKniprand) {
      const aangeraakt = toestand.editorKniprand === "begin" ? selectie.begin : selectie.einde;
      toestand.editorLangVasthouden = setTimeout(() => {
        toestand.editorLangVasthouden = null;
        beperkEditorVenster(aangeraakt - .75, 1.5);
      }, 500);
    }
    vlak.classList.add("is-verslepen");
    vlak.setPointerCapture(gebeurtenis.pointerId);
    if (!toestand.editorKniprand) verplaatsEditorCursorMetAanwijzer(gebeurtenis);
  });
  vlak.addEventListener("pointermove", (gebeurtenis) => {
    if (!toestand.editorIsAanHetSlepen) return;
    if (Math.abs(gebeurtenis.clientX - toestand.editorLaatstePointerX) > 5 && toestand.editorLangVasthouden) {
      clearTimeout(toestand.editorLangVasthouden);
      toestand.editorLangVasthouden = null;
    }
    if (toestand.editorKniprand) {
      const selectie = geefEditorSelectie();
      const tijd = Math.round(geefSecondeBijPointer(gebeurtenis) * 1000) / 1000;
      if (toestand.editorKniprand === "begin") stelSelectieInEditorIn(tijd, selectie.einde, "begin");
      else stelSelectieInEditorIn(selectie.begin, tijd, "einde");
    } else verplaatsEditorCursorMetAanwijzer(gebeurtenis);
  });
  function stopMetSlepen(gebeurtenis) {
    if (!toestand.editorIsAanHetSlepen) return;
    if (toestand.editorLangVasthouden) clearTimeout(toestand.editorLangVasthouden);
    toestand.editorLangVasthouden = null;
    if (!toestand.editorKniprand) verplaatsEditorCursorMetAanwijzer(gebeurtenis);
    toestand.editorKniprand = null;
    toestand.editorIsAanHetSlepen = false;
    vlak.classList.remove("is-verslepen");
    if (vlak.hasPointerCapture(gebeurtenis.pointerId)) vlak.releasePointerCapture(gebeurtenis.pointerId);
    zetEditorMediaOpGekozenPositie();
  }
  vlak.addEventListener("pointerup", stopMetSlepen);
  vlak.addEventListener("pointercancel", (gebeurtenis) => {
    toestand.editorIsAanHetSlepen = false;
    toestand.editorKniprand = null;
    if (toestand.editorLangVasthouden) clearTimeout(toestand.editorLangVasthouden);
    toestand.editorLangVasthouden = null;
    vlak.classList.remove("is-verslepen");
    if (vlak.hasPointerCapture(gebeurtenis.pointerId)) vlak.releasePointerCapture(gebeurtenis.pointerId);
  });
  vlak.addEventListener("wheel", (gebeurtenis) => {
    gebeurtenis.preventDefault();
    if (gebeurtenis.ctrlKey) zoomInEditor(gebeurtenis.deltaY < 0 ? .6 : 1.6, geefSecondeBijPointer(gebeurtenis));
    else beperkEditorVenster(toestand.editorVensterBegin +
      Math.sign(gebeurtenis.deltaY) * toestand.editorVensterDuur * .12, toestand.editorVensterDuur);
  }, { passive: false });
  vlak.addEventListener("keydown", (gebeurtenis) => {
    const stap = gebeurtenis.altKey ? .001 : gebeurtenis.shiftKey ? .1 : .01;
    const selectie = geefEditorSelectie();
    let positie = toestand.editorAfspeelpositie;
    if (gebeurtenis.key === "ArrowRight") positie += stap;
    else if (gebeurtenis.key === "ArrowLeft") positie -= stap;
    else if (gebeurtenis.key === "Home") positie = selectie.begin;
    else if (gebeurtenis.key === "End") positie = selectie.einde;
    else return;
    gebeurtenis.preventDefault();
    werkEditorAfspeelpositieBij(positie);
    zetEditorMediaOpGekozenPositie();
  });
}

function magSpatieDeEditorBedienen(gebeurtenis) {
  if (!element("dialoog-bewerken").open || gebeurtenis.code !== "Space" || gebeurtenis.repeat) return false;
  if (gebeurtenis.ctrlKey || gebeurtenis.altKey || gebeurtenis.metaKey) return false;
  const doel = gebeurtenis.target;
  // Typen, numerieke tijden aanpassen en bereik-schuiven mogen geen audio
  // starten; spatie blijft daar de normale functie van het veld houden.
  if (doel?.isContentEditable || doel?.closest?.("input, textarea, select, button, [role=checkbox]")) return false;
  return true;
}


/*
  De uitgebreide bibliotheek is een aparte beheerweergave. Het soundboard
  blijft zichtbaar achter het venster en de audiostream hoeft niet te stoppen.
*/
function geefDoorzoekbareTekstVanGeluid(geluid) {
  const groepsnamen = (geluid.groep_ids || []).map((id) =>
    toestand.groepen.find((groep) => groep.id === id)?.naam || "");
  return [geluid.naam, geluid.bestandsnaam, geluid.beschrijving,
    geluid.gesproken_tekst, geluid.zoekwoorden, ...groepsnamen]
    .filter(Boolean).join(" ").toLocaleLowerCase("nl-NL");
}

function geefZichtbareBeheergeluiden() {
  const zoekterm = element("beheer-zoeken").value.trim().toLocaleLowerCase("nl-NL");
  const groep = element("beheer-groep").value;
  const formaat = element("beheer-formaat").value;
  const zichtbaar = toestand.geluiden.filter((geluid) => {
    const groepKlopt = groep === "alle" || (groep === "zonder"
      ? !(geluid.groep_ids || []).length : hoortBijGroep(geluid,groep));
    const formaatKlopt = formaat === "alle" || geluid.formaat === formaat;
    return groepKlopt && formaatKlopt && pastBijZoekopdracht(geluid, zoekterm);
  });
  const sortering = element("beheer-sortering").value;
  const opNaam = (a, b) => a.naam.localeCompare(b.naam, "nl", { numeric: true, sensitivity: "base" });
  zichtbaar.sort((a, b) => {
    if (sortering === "populair") return Number(b.aantal_afgespeeld||0)-Number(a.aantal_afgespeeld||0)||opNaam(a,b);
    if (sortering === "naam-terug") return -opNaam(a, b);
    if (sortering === "duur-kort") return (a.fragmentduur ?? Infinity) - (b.fragmentduur ?? Infinity) || opNaam(a, b);
    if (sortering === "duur-lang") return (b.fragmentduur ?? -1) - (a.fragmentduur ?? -1) || opNaam(a, b);
    if (sortering === "formaat") return a.formaat.localeCompare(b.formaat) || opNaam(a, b);
    return opNaam(a, b);
  });
  return zichtbaar;
}

function tekenGroepenoverzichtInBeheer() {
  const overzicht=element('beheer-groepkaarten'); overzicht.replaceChildren();
  const huidigeGroep=element('beheer-groep').value;
  const opties=[
    {id:'alle',naam:'Alle geluiden',diepte:0,aantal:toestand.geluiden.length},
    {id:'zonder',naam:'Zonder map',diepte:0,aantal:toestand.geluiden.filter(g=>!(g.groep_ids||[]).length).length},
    ...getoondeGroepenAlsBoom().map(g=>({...g,aantal:aantalInGroep(g.id)}))
  ];
  for(const optie of opties){
    const knop=maakElement('button','beheer-groepkaart');knop.type='button';
    knop.title=optie.naam;
    knop.style.paddingLeft=`${12+Math.min(optie.diepte,8)*15}px`;
    knop.append(maakElement('span','beheer-groep-icoon',optie.id==='alle'?'▦':optie.id==='zonder'?'◇':'▸'),
      maakElement('span','beheer-mapnaam',optie.naam),maakElement('span','beheer-groepteller',String(optie.aantal)));
    knop.classList.toggle('actief',optie.id===huidigeGroep);
    knop.setAttribute('aria-pressed',String(optie.id===huidigeGroep));
    knop.addEventListener('click',()=>{
      element('beheer-groep').value=optie.id;
      toestand.beheerZichtbaarAantal=60; maakGroteBibliotheekZichtbaar();
    });
    if(optie.id!=='alle'&&optie.id!=='zonder'){
      knop.draggable=true;
      knop.addEventListener('dragstart',e=>{
        e.dataTransfer.setData('text/plain',JSON.stringify({soort:'groep',id:optie.id}));
        e.dataTransfer.effectAllowed='move';
      });
      knop.addEventListener('dragover',e=>e.preventDefault());
      knop.addEventListener('drop',e=>verwerkMapDrop(e,optie.id));
      const rij=maakElement('div','beheer-mappenrij');
      const beheer=maakElement('button','beheer-mapacties','…');
      beheer.title=`Map ${optie.naam} aanpassen`;
      beheer.addEventListener('click',()=>beheerMap(optie));
      rij.append(knop,beheer);overzicht.appendChild(rij);
    }else{
      knop.addEventListener('dragover',e=>e.preventDefault());
      if(optie.id==='alle')knop.addEventListener('drop',e=>verwerkMapDrop(e,null));
      overzicht.appendChild(knop);
    }
  }
}
async function verwerkMapDrop(event,ouderId){
  event.preventDefault();event.stopPropagation();
  let data;
  try{data=JSON.parse(event.dataTransfer.getData('text/plain'));}catch{return;}
  if(data.soort==='groep'){
    await voerGebruikersactieUit('Map verplaatsen',async()=>{
      await vraagAanPython('POST',`/api/groepen/${data.id}/verplaats`,{ouder_id:ouderId});
      await laadBibliotheekOpnieuw();
    });
  }else if(data.soort==='bibliotheek'&&ouderId){
    await voerGebruikersactieUit('Geluid in map plaatsen',async()=>{
      await vraagAanPython('POST',`/api/groepen/${ouderId}/geluiden`,{geluid_id:data.id});
      await laadBibliotheekOpnieuw();
    });
  }
}
function beheerMap(groep){
  const dialoog=element('dialoog-map-beheer');
  dialoog.dataset.groepId=groep.id;
  element('map-beheer-naam').value=groep.naam;
  const ouderKeuze=element('map-beheer-ouder');
  ouderKeuze.replaceChildren(new Option('Geen, hoofdmap',''));
  const nietToegestaan=groepEnSubgroepen(groep.id);
  for(const optie of getoondeGroepenAlsBoom()){
    if(nietToegestaan.has(optie.id))continue;
    ouderKeuze.appendChild(new Option(`${'  '.repeat(Math.min(optie.diepte,8))}${optie.naam}`,optie.id));
  }
  ouderKeuze.value=groep.ouder_id||'';
  dialoog.showModal();
  element('map-beheer-naam').focus();
}

function vernieuwBeheerselectieTeller() {
  const aantal = toestand.beheerGeselecteerd.size;
  element("beheer-selectie-teller").textContent = `${aantal} geselecteerd`;
  element("knop-beheer-exporteer").disabled = aantal === 0;
  element("knop-beheer-koppel-groep").disabled = aantal === 0;
  element('knop-beheer-losmaak-groep').disabled = aantal === 0;
  element("knop-beheer-verwijderen").disabled = aantal === 0;
  element("knop-beheer-volume").disabled = aantal === 0;
}

function maakGroteBibliotheekZichtbaar() {
  sluitGeluidActiemenu();
  const groepmenu = element("beheer-groep");
  const vorigeGroep = groepmenu.value || "alle";
  groepmenu.replaceChildren();
  for (const [nummer, naam] of [["alle", "Alle groepen"], ["zonder", "Zonder map"],
    ...getoondeGroepenAlsBoom().map((groep) => [groep.id, `${"　".repeat(Math.min(groep.diepte,8))}${groep.naam}`])]) {
    const optie = document.createElement("option"); optie.value = nummer; optie.textContent = naam;
    groepmenu.appendChild(optie);
  }
  groepmenu.value = [...groepmenu.options].some((optie) => optie.value === vorigeGroep) ? vorigeGroep : "alle";
  tekenGroepenoverzichtInBeheer();
  const groepskeuze = element("beheer-groep-toevoegen");
  const geselecteerdeGroep = groepskeuze.value;
  groepskeuze.replaceChildren(new Option("Groep kiezen", ""));
  for (const groep of getoondeGroepenAlsBoom()) groepskeuze.appendChild(new Option(`${"　".repeat(Math.min(groep.diepte,8))}${groep.naam}`, groep.id));
  groepskeuze.value = toestand.groepen.some((groep) => groep.id === geselecteerdeGroep)
    ? geselecteerdeGroep : toestand.groepen.some((groep) => groep.id === groepmenu.value)
      ? groepmenu.value : '';

  const zichtbaar = geefZichtbareBeheergeluiden();
  const lijst = element("beheer-lijst");
  lijst.replaceChildren();
  for (const geluid of zichtbaar.slice(0, toestand.beheerZichtbaarAantal)) {
    const rij = maakElement("div", "beheer-rij");
    rij.dataset.geluidId = geluid.id;
    rij.draggable=true;
    rij.addEventListener('dragstart',(e)=>{
      e.dataTransfer.setData('text/plain',JSON.stringify({soort:'bibliotheek',id:geluid.id}));
      e.dataTransfer.effectAllowed='copyMove';
    });
    const selectie = document.createElement("input");
    selectie.type = "checkbox";
    selectie.checked = toestand.beheerGeselecteerd.has(geluid.id);
    selectie.setAttribute("aria-label", `Selecteer ${geluid.naam}`);
    selectie.addEventListener("change", () => {
      if (selectie.checked) toestand.beheerGeselecteerd.add(geluid.id);
      else toestand.beheerGeselecteerd.delete(geluid.id);
      vernieuwBeheerselectieTeller();
    });
    const kunst = maakElement("div", "beheer-kunst");
    const plaatje = geefStatischeAfbeelding(geluid);
    if (plaatje) kunst.appendChild(maakAfbeelding(plaatje));
    else kunst.appendChild(speelicoon());
    const titel = maakElement("div", "beheer-rij-tekst");
    titel.appendChild(maakElement("strong", "", geluid.naam));
    const tekst = geluid.gesproken_tekst || geluid.beschrijving || geluid.zoekwoorden || geluid.bestandsnaam;
    titel.appendChild(maakElement("small", "", tekst.slice(0, 180)));
    const groepen = maakElement("div", "beheer-rij-groepen");
    for (const nummer of (geluid.groep_ids || []).slice(0, 3)) {
      const groep = toestand.groepen.find((waarde) => waarde.id === nummer);
      if (groep) groepen.appendChild(maakElement("span", "beheer-rij-groep", groep.naam));
    }
    titel.appendChild(groepen);
    const duur = maakElement('span', 'beheer-rij-duur');
    for (const [tekst, uitleg] of [
      [geluid.formaat.toUpperCase(), 'Bestandstype'],
      [netteTijd(geluid.fragmentduur), 'Totale duur van het fragment'],
      [`${geluid.aantal_afgespeeld || 0} keer`, 'Aantal keren uitgezonden via de virtuele microfoon']
    ]) {
      const waarde = maakElement('span', 'beheer-metadatatip', tekst);
      waarde.title = uitleg;
      waarde.dataset.uitleg = uitleg;
      waarde.setAttribute('aria-label', `${uitleg}: ${tekst}`);
      waarde.tabIndex = 0;
      duur.appendChild(waarde);
    }
    const preview = maakPreviewknopVoorGeluid(geluid);
    const uitzenden = maakUitzendknopVoorGeluid(geluid);
    const bewerken = maakElement("button", "knop knop-ghost beheer-bewerken", "Bewerken");
    bewerken.type = "button";
    bewerken.addEventListener("click", () => openEditorVanuitBeheer(geluid.id));
    const meer = maakElement("button", "icoonknop bibliotheek-acties-knop", "…");
    meer.type = "button";
    meer.setAttribute("aria-label", `Meer acties voor ${geluid.naam}`);
    meer.setAttribute("aria-haspopup", "menu");
    meer.setAttribute("aria-expanded", "false");
    meer.addEventListener("click", (gebeurtenis) => {
      gebeurtenis.stopPropagation();
      toonGeluidActiemenu(geluid.id, meer);
    });
    rij.append(selectie, kunst, titel, duur, preview, uitzenden, bewerken, meer);
    lijst.appendChild(rij);
  }
  if (!zichtbaar.length) lijst.appendChild(maakElement("p", "lege-lijst", "Geen geluiden gevonden."));
  element("beheer-aantal-zichtbaar").textContent = `${zichtbaar.length} gevonden van ${toestand.geluiden.length} geluiden`;
  element("knop-beheer-meer").hidden = zichtbaar.length <= toestand.beheerZichtbaarAantal;
  vernieuwBeheerselectieTeller();
  werkPreviewEnStopknoppenBij();
}

function openEditorVanuitBeheer(geluidId) {
  // Na het bewerken komen we terug in dezelfde gefilterde lijst.
  // Dat scheelt onnodig opnieuw zoeken wanneer je tientallen clips beheert.
  toestand.terugNaarBibliotheekbeheer = true;
  openBewerkvenster(geluidId);
}


/*
  Losse exports staan bewust los van de bibliotheek-ZIP.
  MP3 bevat alleen geluid; MP4 combineert videobeeld en het bijbehorende geluid.
  Een gekoppelde GIF blijft een afzonderlijk origineel bestand.
*/
const keuzeVoorLosseExport = {
  geluidId: null,
  begin: null,
  duur: null,
  bezig: false
};

function openLosseExport(geluidId, gebruikHuidigeEditorSelectie = false, toonVenster = true) {
  const geluid = vindGeluid(geluidId);
  if (!geluid?.bestand_gevonden) {
    toonMelding("Het bronbestand ontbreekt. Importeer het opnieuw.", true);
    return;
  }
  keuzeVoorLosseExport.geluidId = geluidId;
  keuzeVoorLosseExport.begin = gebruikHuidigeEditorSelectie
    ? Number(element("bewerken-start").value) : null;
  keuzeVoorLosseExport.duur = gebruikHuidigeEditorSelectie
    ? Number(element("bewerken-duur").value) : null;
  element("export-titel").textContent = geluid.naam;
  const gekoppeldeGif = Boolean(geluid.afbeelding?.toLowerCase().endsWith(".gif"));
  const formaten = Array.isArray(geluid.exportformaten) ? geluid.exportformaten : [];
  for (const formaat of ["mp3", "mp4", "afbeelding", "gif"]) {
    const knop = element(`knop-export-${formaat}`);
    knop.hidden = !formaten.includes(formaat);
    knop.disabled = !formaten.includes(formaat);
  }
  const selectieTekst = gebruikHuidigeEditorSelectie
    ? "Je huidige selectie wordt gebruikt, ook als die nog niet is opgeslagen."
    : "De opgeslagen knipinstellingen worden gebruikt.";
  element("export-uitleg").textContent = selectieTekst;
  element("export-voortgang").textContent = gekoppeldeGif
    ? "GIF: alleen de animatie. MP4: animatie en geselecteerde audio samen, tot 2 minuten."
    : geluid.is_video
      ? "MP4: beeld en geluid samen. GIF: alleen de animatie, maximaal 12 seconden."
      : "Video of GIF is alleen beschikbaar als er beeld bij dit geluid hoort.";
  if (toonVenster) element("dialoog-losse-export").showModal();
}

async function downloadLosBestand(formaat) {
  if (keuzeVoorLosseExport.bezig || !keuzeVoorLosseExport.geluidId) return;
  keuzeVoorLosseExport.bezig = true;
  const keuzes = [...document.querySelectorAll("[data-exportformaat]")];
  const vorigeDisabled = keuzes.map((knop) => knop.disabled);
  keuzes.forEach((knop) => { knop.disabled = true; });
  element("export-voortgang").textContent = `${formaat.toUpperCase()} wordt voorbereid…`;
  try {
    // POST met de dashboardbeveiligingscode. Een simpele externe link kan
    // dus niet ongemerkt zware mediaconversies op deze computer starten.
    const antwoord = await haalBijApplicatie(`/api/geluiden/${keuzeVoorLosseExport.geluidId}/exporteer`, {
      method: "POST",
      cache: "no-store",
      headers: {
        "X-Drost-Token": beveiligingscode,
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        formaat,
        begin: keuzeVoorLosseExport.begin,
        duur: keuzeVoorLosseExport.duur
      })
    });
    if (!antwoord.ok) {
      let inhoud = {};
      try { inhoud = await antwoord.json(); } catch { /* Diagnose blijft in het logboek. */ }
      throw maakAntwoordfout(inhoud, antwoord.status);
    }
    const inhoudstype = {
      mp3: ["audio/mpeg"], mp4: ["video/mp4"], gif: ["image/gif"],
      afbeelding: ["image/png", "image/jpeg", "image/webp"]
    }[formaat];
    if (!inhoudstype?.some((soort) => antwoord.headers.get("Content-Type")?.startsWith(soort))) {
      throw new Error("Het bestand kon niet in dit formaat worden gemaakt. Probeer een ander formaat.");
    }
    const antwoordKop = antwoord.headers.get("Content-Disposition") || "";
    const overeenkomendeNaam = antwoordKop.match(/filename="([A-Za-z0-9_-]+\.(?:mp3|mp4|gif|png|jpg|jpeg|webp))"/);
    const bestandsnaam = overeenkomendeNaam?.[1] || `DrostSoundboard.${formaat}`;
    const inhoud = await antwoord.blob();
    if (!inhoud.size) throw new Error("Er is geen bestand ontvangen.");
    const downloadadres = URL.createObjectURL(inhoud);
    const link = document.createElement("a");
    link.href = downloadadres;
    link.download = bestandsnaam;
    document.body.appendChild(link);
    link.click();
    link.remove();
    // Wacht met vrijgeven omdat de download niet bij iedere browser meteen
    // is gestart op het moment waarop de klikfunctie terugkeert.
    setTimeout(() => URL.revokeObjectURL(downloadadres), 30_000);
    element("export-voortgang").textContent = `${bestandsnaam} is gereed.`;
    toonMelding(`${formaat.toUpperCase()} wordt gedownload.`);
  } finally {
    keuzeVoorLosseExport.bezig = false;
    keuzes.forEach((knop, nummer) => { knop.disabled = vorigeDisabled[nummer]; });
  }
}

function exporteerGeselecteerdeGeluiden() {
  const nummers = [...toestand.beheerGeselecteerd].filter((id) => vindGeluid(id));
  if (!nummers.length) { toonMelding("Selecteer eerst geluiden om te exporteren.", true); return; }
  if (nummers.length > 500) { toonMelding("Exporteer maximaal 500 geluiden tegelijk.", true); return; }
  // Browserdownload met HTTP-stream in plaats van een grote Blob in RAM.
  const parameters = new URLSearchParams();
  for (const nummer of nummers) parameters.append("id", nummer);
  const link = document.createElement("a");
  link.href = `/api/bibliotheek/exporteer?${parameters.toString()}`;
  link.download = "DrostSoundboard_bibliotheek.zip";
  document.body.appendChild(link);
  link.click();
  link.remove();
  toonMelding(`Export gestart voor ${nummers.length} geluid(en).`);
}

function maakAudiopackBoom(){
  const doel=element('audiopack-boom');doel.replaceChildren();
  const root={naam:'',kinderen:new Map(),geluiden:[]};
  const toestaan=element('audiopack-ook-dubbelen').checked;
  const magKiezen=(item)=>toestaan||(!item.al_aanwezig&&!item.dubbel_in_pakket);
  for(const item of toestand.audiopackGeluiden){
    const paden=item.groepspaden?.length?item.groepspaden:[[]];
    for(const pad of paden){
      let map=root;
      for(const naam of pad){
        if(!map.kinderen.has(naam))map.kinderen.set(naam,{naam,kinderen:new Map(),geluiden:[]});
        map=map.kinderen.get(naam);
      }
      map.geluiden.push(item);
    }
  }
  const kiesVak=(tekst,indices,diepte,subtitel='',bestaand=false)=>{
    const label=maakElement('label',bestaand?'audiopack-rij bestaand':'audiopack-rij');
    label.style.paddingLeft=`${12+Math.min(diepte,12)*19}px`;
    const input=document.createElement('input');input.type='checkbox';
    const toegestaan=indices.filter(i=>magKiezen(toestand.audiopackGeluiden[i]));
    const aantal=toegestaan.filter(i=>toestand.audiopackSelectie.has(i)).length;
    input.checked=aantal>0;input.indeterminate=aantal>0&&aantal<toegestaan.length;
    input.disabled=!toegestaan.length;
    label.append(input,maakElement('span','audiopack-naam',tekst));
    if(subtitel)label.append(maakElement('small','',subtitel));
    input.addEventListener('change',()=>{
      const selecteer=input.checked;
      for(const i of toegestaan){if(selecteer)toestand.audiopackSelectie.add(i);else toestand.audiopackSelectie.delete(i);}
      maakAudiopackBoom();
    });
    doel.appendChild(label);
  };
  const verzamel=(map)=>[...map.geluiden.map(g=>g.index),...Array.from(map.kinderen.values()).flatMap(verzamel)];
  const wandel=(map,diepte)=>{
    for(const kind of [...map.kinderen.values()].sort((a,b)=>a.naam.localeCompare(b.naam,'nl'))){
      const nummers=[...new Set(verzamel(kind))];
      kiesVak(`▸ ${kind.naam}`,nummers,diepte,`${nummers.length} geluid(en)`);
      wandel(kind,diepte+1);
    }
    for(const item of map.geluiden){
      const dubbel=item.al_aanwezig||item.dubbel_in_pakket;
      const info=item.al_aanwezig?`Al aanwezig: ${item.bestaande_naam||item.naam}`
        :item.dubbel_in_pakket?'Dubbel in dit audiopack'
        :item.zelfde_naam?`${item.formaat}, naam bestaat al maar inhoud verschilt`:item.formaat;
      kiesVak(item.naam,[item.index],diepte,info,dubbel);
    }
  };
  wandel(root,0);
  const dubbelAantal=toestand.audiopackGeluiden.filter(g=>g.al_aanwezig||g.dubbel_in_pakket).length;
  element('audiopack-status').textContent=
    `${toestand.audiopackSelectie.size} van ${toestand.audiopackGeluiden.length} geselecteerd. `+
    `${dubbelAantal} bestaande of dubbele bestanden herkend. Nieuwe geluiden staan standaard aangevinkt.`;
  element('audiopack-importeer').disabled=!toestand.audiopackSelectie.size;
}
async function bekijkAudiopackVoorImport(bestand){
  if(!bestand)return;
  if(!bestand.name.toLowerCase().endsWith('.zip')||bestand.size>1024*1024*1024+8*1024*1024)
    throw new Error('Kies een audiopack-ZIP met maximaal 1 GiB inhoud.');
  toonMelding('Audiopack wordt gecontroleerd. De bibliotheek verandert nog niet.');
  const antwoord=await vraagAanPython('POST','/api/bibliotheek/audiopack-bekijk',undefined,bestand);
  toestand.audiopackBestand=bestand;
  toestand.audiopackGeluiden=antwoord.geluiden||[];
  element('audiopack-ook-dubbelen').checked=false;
  toestand.audiopackSelectie=new Set(toestand.audiopackGeluiden.filter(g=>!g.al_aanwezig&&!g.dubbel_in_pakket).map(g=>g.index));
  maakAudiopackBoom();
  element('dialoog-audiopack').showModal();
}
async function importeerAudiopackSelectie(){
  const bestand=toestand.audiopackBestand;
  const indices=[...toestand.audiopackSelectie].sort((a,b)=>a-b);
  if(!bestand||!indices.length)throw new Error('Selecteer minstens één geluid.');
  const knop=element('audiopack-importeer');knop.disabled=true;
  element('audiopack-status').textContent=`${indices.length} geluiden importeren…`;
  try{
    // Dezelfde ZIP gaat opnieuw lokaal naar de server, nu met gevalideerde indexselectie.
    const dubbelOptie=element('audiopack-ook-dubbelen').checked?'toestaan':'overslaan';
    const antwoord=await vraagAanPython('POST',`/api/bibliotheek/importeer?selectie=${indices.join(',')}&dubbelen=${dubbelOptie}`,undefined,bestand);
    element('dialoog-audiopack').close();
    toestand.audiopackBestand=null;toestand.audiopackGeluiden=[];
    toestand.beheerGeselecteerd.clear();
    await laadBibliotheekOpnieuw();
    toonMelding(antwoord.melding||'Audiopack geïmporteerd.');
  }finally{knop.disabled=false;}
}

async function openVolledigeBibliotheekExport(){
  const antwoord=await vraagAanPython('GET','/api/bibliotheek/exportoverzicht');
  const doel=element('export-overzicht-inhoud');doel.replaceChildren();
  const bytes=(antwoord.media_bytes/(1024*1024)).toLocaleString('nl-NL',{maximumFractionDigits:1});
  element('export-overzicht-status').textContent=
    `${antwoord.aantal} geluiden in ${antwoord.mappen} mappen, samen ongeveer ${bytes} MiB. Maximaal 500 geluiden en 1 GiB.`;
  const omschrijving=maakElement('strong','','Inhoud van deze export:');doel.appendChild(omschrijving);
  for(const tekst of ['Alle geluiden met de oorspronkelijke audiobestanden','Geluidsnamen, volume, fragmenten, afbeeldingen en metadata',
    'De mappenstructuur, inclusief lege mappen'])doel.append(maakElement('div','mapnaam',`✓ ${tekst}`));
  for(const naam of antwoord.mappaden.slice(0,70))doel.append(maakElement('div','mapnaam',`📁 ${naam}`));
  if(antwoord.mappaden.length>70)doel.append(maakElement('div','mapnaam',`En ${antwoord.mappaden.length-70} andere mappen...`));
  doel.append(maakElement('strong','','Geluiden in het pakket:'));
  for(const geluid of antwoord.geluiden||[]){
    const map=(geluid.mappen||[]).join(', ')||'Zonder map';
    doel.append(maakElement('div','mapnaam',`${geluid.naam} (${geluid.formaat}) in ${map}`));
  }
  for(const naam of antwoord.ontbrekende_bestanden.slice(0,10))doel.append(maakElement('div','mapnaam',`Ontbrekend: ${naam}`));
  const knop=element('knop-export-helemaal');knop.disabled=!antwoord.kan_exporteren;
  if(!antwoord.kan_exporteren)element('export-overzicht-status').textContent+=
    ' Export niet mogelijk: ontbrekend bronbestand of limiet overschreden.';
  element('dialoog-export-overzicht').showModal();
}
function downloadVolledigeBibliotheek(){
  const link=document.createElement('a');link.href='/api/bibliotheek/exporteer';
  link.download='DrostSoundboard_volledige_bibliotheek.zip';
  document.body.appendChild(link);link.click();link.remove();
  element('dialoog-export-overzicht').close();
  toonMelding('Volledige bibliotheek wordt als ZIP gedownload.');
}

function koppelBibliotheekbeheer() {
  element('formulier-map-beheer').addEventListener('submit',(event)=>{
    event.preventDefault();
    voerGebruikersactieUit('Map aanpassen', async()=>{
      const dialoog=element('dialoog-map-beheer');
      const id=dialoog.dataset.groepId;
      const bestaand=toestand.groepen.find(g=>g.id===id);
      if(!bestaand)throw new Error('Map bestaat niet meer. Herlaad de bibliotheek.');
      const naam=element('map-beheer-naam').value.trim();
      const ouder=element('map-beheer-ouder').value||null;
      if(naam!==bestaand.naam){await vraagAanPython('POST',`/api/groepen/${id}`,{naam});}
      if(ouder!==(bestaand.ouder_id||null)){
        await vraagAanPython('POST',`/api/groepen/${id}/verplaats`,{ouder_id:ouder});
      }
      dialoog.close();
      await laadBibliotheekOpnieuw();
      toonMelding('Map opgeslagen.');
    });
  });
  element('knop-map-verwijderen').addEventListener('click',()=>{
    const dialoog=element('dialoog-map-beheer');
    const id=dialoog.dataset.groepId;
    const bestaand=toestand.groepen.find(g=>g.id===id);
    if(!bestaand)return;
    if(!window.confirm(`Map ${bestaand.naam} verwijderen? Geluiden blijven behouden. Submappen schuiven één niveau omhoog.`))return;
    voerGebruikersactieUit('Map verwijderen',async()=>{
      await vraagAanPython('DELETE',`/api/groepen/${id}`);
      if(element('beheer-groep').value===id)element('beheer-groep').value='alle';
      dialoog.close();
      await laadBibliotheekOpnieuw();
      toonMelding('Map verwijderd. Geluidsbestanden zijn behouden.');
    });
  });
  element("knop-bibliotheek-groot").addEventListener("click", () => {
    toestand.beheerZichtbaarAantal = 60;
    window.location.hash='#bibliotheek';
    maakGroteBibliotheekZichtbaar();
    element("beheer-zoeken").focus();
  });
  element("beheer-zoeken").addEventListener("input", () => {
    toestand.beheerZichtbaarAantal = 60;
    maakGroteBibliotheekZichtbaar();
  });
  element("beheer-groep").addEventListener("change", () => {
    toestand.beheerZichtbaarAantal = 60;
    maakGroteBibliotheekZichtbaar();
  });
  for (const id of ["beheer-formaat", "beheer-sortering"]) {
    element(id).addEventListener("change", () => {
      toestand.beheerZichtbaarAantal = 60;
      maakGroteBibliotheekZichtbaar();
    });
  }
  element("knop-beheer-bestanden").addEventListener("click", () => element("bestandkiezer").click());
  element('knop-beheer-nieuwe-groep').addEventListener('click',()=>element('knop-nieuwe-groep').click());
  element('knop-submap').addEventListener('click',()=>{
    const ouder=element('beheer-groep').value;
    if(ouder==='alle'||ouder==='zonder'){
      toonMelding('Kies eerst een bovenliggende map.',true);return;
    }
    element('nieuwe-groepsnaam').value='';
    element('dialoog-groep').dataset.ouderId=ouder;
    element('dialoog-groep').showModal();
    element('nieuwe-groepsnaam').focus();
  });
  element("dialoog-bewerken").addEventListener("close", () => {
    if (!toestand.terugNaarBibliotheekbeheer) return;
    toestand.terugNaarBibliotheekbeheer = false;
    maakGroteBibliotheekZichtbaar();
  });
  element("knop-beheer-selecteer-alles").addEventListener("click", () => {
    for (const geluid of geefZichtbareBeheergeluiden().slice(0, 250)) toestand.beheerGeselecteerd.add(geluid.id);
    maakGroteBibliotheekZichtbaar();
  });
  element("knop-beheer-deselecteer").addEventListener("click", () => {
    toestand.beheerGeselecteerd.clear();
    maakGroteBibliotheekZichtbaar();
  });
  element("knop-beheer-meer").addEventListener("click", () => {
    toestand.beheerZichtbaarAantal += 60;
    maakGroteBibliotheekZichtbaar();
  });
  element("knop-beheer-exporteer").addEventListener("click", exporteerGeselecteerdeGeluiden);
  element('knop-beheer-export-alles').addEventListener('click',()=>voerGebruikersactieUit('Bibliotheekexport voorbereiden',openVolledigeBibliotheekExport));
  element('knop-export-helemaal').addEventListener('click',downloadVolledigeBibliotheek);
  element('audiopack-ook-dubbelen').addEventListener('change',()=>{
    if(!element('audiopack-ook-dubbelen').checked){
      for(const item of toestand.audiopackGeluiden){
        if(item.al_aanwezig||item.dubbel_in_pakket)toestand.audiopackSelectie.delete(item.index);
      }
    }
    maakAudiopackBoom();
  });
  element('knop-beheer-exporteer-map').addEventListener('click',()=>{
    const groep=element('beheer-groep').value;
    const selectie=geefZichtbareBeheergeluiden();
    const nummers=selectie.map(g=>g.id);
    if(!nummers.length){toonMelding('Deze map bevat geen geluiden.',true);return;}
    if(nummers.length>500){toonMelding('Een audiopack bevat maximaal 500 geluiden. Exporteer een selectie.',true);return;}
    if(!window.confirm(`Audiopack maken van ${nummers.length} geluiden${groep==='alle'?'': ' uit deze map'}?`))return;
    const params=new URLSearchParams();
    nummers.forEach(id=>params.append('id',id));
    const link=document.createElement('a');link.href=`/api/bibliotheek/exporteer?${params}`;
    link.download='DrostSoundboard_Audiopack.zip';document.body.appendChild(link);link.click();link.remove();
  });
  element("knop-beheer-volume").addEventListener("click", () => voerGebruikersactieUit(
    "Geselecteerde geluidsvolumes instellen", async () => {
      const geluid_ids = [...toestand.beheerGeselecteerd].filter((id) => vindGeluid(id));
      if (!geluid_ids.length) return;
      if (!window.confirm(`Zet ${geluid_ids.length} geselecteerde geluid(en) op origineel volume (100%)? De knipinstellingen blijven behouden.`)) return;
      const resultaat = await vraagAanPython("POST", "/api/bibliotheek/volume", { geluid_ids, volume: 1.0 });
      await laadBibliotheekOpnieuw();
      toonMelding(resultaat.melding);
    }));
  element("knop-beheer-koppel-groep").addEventListener("click", () => voerGebruikersactieUit(
    "Geluiden aan groep toevoegen", async () => {
      const groep_id = element("beheer-groep-toevoegen").value;
      if (!groep_id) throw new Error("Kies eerst een groep.");
      const geluid_ids = [...toestand.beheerGeselecteerd].filter((id) => vindGeluid(id));
      const antwoord = await vraagAanPython("POST", "/api/bibliotheek/groep-toewijzen", { groep_id, geluid_ids });
      await laadBibliotheekOpnieuw();
      toonMelding(antwoord.melding);
    }));
  element('knop-beheer-losmaak-groep').addEventListener('click', () => voerGebruikersactieUit(
    'Geluiden uit map halen', async () => {
      const groep_id = element('beheer-groep-toevoegen').value;
      const geluid_ids = [...toestand.beheerGeselecteerd].filter((id) => vindGeluid(id));
      if (!groep_id) throw new Error('Kies de map waaruit je geluiden wilt halen.');
      if (!geluid_ids.length) throw new Error('Selecteer eerst één of meer geluiden.');
      const groep = toestand.groepen.find((item) => item.id === groep_id);
      if (!window.confirm(`${geluid_ids.length} geselecteerde geluiden uit map "${groep?.naam || 'Map'}" halen? De geluiden blijven in de bibliotheek en andere mappen.`)) return;
      const antwoord = await vraagAanPython('POST','/api/bibliotheek/groep-losmaken',{groep_id,geluid_ids});
      toestand.beheerGeselecteerd.clear();
      await laadBibliotheekOpnieuw();
      toonMelding(antwoord.melding);
    }));
  element("knop-beheer-verwijderen").addEventListener("click", () => voerGebruikersactieUit(
    "Geluiden uit bibliotheek halen", async () => {
      const geluid_ids = [...toestand.beheerGeselecteerd].filter((id) => vindGeluid(id));
      if (!geluid_ids.length) return;
      if (!window.confirm(`Haal ${geluid_ids.length} geluid(en) uit de bibliotheek? De oorspronkelijke audiobestanden blijven behouden.`)) return;
      const antwoord = await vraagAanPython("POST", "/api/bibliotheek/verwijder-selectie",
        {geluid_ids, bevestiging:"VERWIJDER"});
      toestand.beheerGeselecteerd.clear();
      await laadBibliotheekOpnieuw();
      toonMelding(antwoord.melding);
    }));
  const kiesArchief = () => element("archiefkiezer").click();
  element("knop-importeer-archief").addEventListener("click", kiesArchief);
  element("knop-beheer-importeer").addEventListener("click", kiesArchief);
  element("archiefkiezer").addEventListener("change", (gebeurtenis) => {
    const bestand=gebeurtenis.target.files?.[0];
    voerGebruikersactieUit('Audiopack bekijken',async()=>{
      try{await bekijkAudiopackVoorImport(bestand);}
      finally{element('archiefkiezer').value='';}
    });
  });
  element('audiopack-importeer').addEventListener('click',()=>voerGebruikersactieUit(
    'Audiopack importeren',importeerAudiopackSelectie));
  element('audiopack-alles').addEventListener('click',()=>{
    element('audiopack-ook-dubbelen').checked=false;
    toestand.audiopackSelectie=new Set(toestand.audiopackGeluiden
      .filter(g=>!g.al_aanwezig&&!g.dubbel_in_pakket).map(g=>g.index));
    maakAudiopackBoom();
  });
  element('audiopack-niets').addEventListener('click',()=>{
    toestand.audiopackSelectie.clear();maakAudiopackBoom();
  });
}

function berekenSoundboardDempingDb(percentage) {
  if (percentage === 0) return null;
  return -20 * Math.log10(percentage / 100);
}

function toonLiveSoundboardniveau(waarden, gemeten) {
  const doel = element("effectvolume-live");
  if (!doel) return;
  if (!gemeten || !waarden.effect_actief) {
    doel.textContent = "Speel een geluid af om het effectniveau te meten.";
    return;
  }
  const voor = Number(waarden.effect_rms_voor);
  const na = Number(waarden.effect_rms_na);
  if (![voor, na].every(Number.isFinite) || voor <= 0.000001) {
    doel.textContent = "Geen meetbaar geluidssignaal in dit fragment.";
    return;
  }
  const dB = waarde => waarde <= 0.000001 ? "stil" : `${(20 * Math.log10(waarde)).toFixed(1).replace(".", ",")} dBFS`;
  doel.textContent = `Effect vóór: ${dB(voor)}. Na volume: ${dB(na)}.`;
}

function werkEffectvolumeWeergaveBij(percentage) {
  element('algemeen-effectvolume-waarde').textContent = `${percentage}%`;
  const db = percentage > 0 ? 20 * Math.log10(percentage / 100) : null;
  element('effectvolume-hint').textContent = percentage === 0
    ? 'Alle soundboardgeluiden zijn stil. Je microfoon verandert niet.'
    : percentage > 100 ? 'Boven 100% worden geluiden versterkt. Bij luide bestanden kan de piekbeveiliging ingrijpen.'
    : 'Voor alle soundboardgeluiden. Het basisvolume per geluid blijft apart instelbaar.';
  element('effectvolume-demping').textContent = db === null ? 'Totaalvolume: stil'
    : `Volumeverandering: ${db > 0 ? '+' : ''}${db.toFixed(1).replace('.', ',')} dB`;
}

async function laadAlgemeenEffectvolume() {
  const antwoord = await vraagAanPython("GET", "/api/instellingen/effectvolume");
  const waarde = antwoord.percentage;
  if (!Number.isInteger(waarde) || waarde < 0 || waarde > 200) {
    throw new Error("Het opgeslagen soundboardvolume is ongeldig.");
  }
  toestand.effectvolumePercentage = waarde;
  element("algemeen-effectvolume").value = String(waarde);
  element("algemeen-effectvolume").disabled = false;
  element("effectvolume-reset").disabled = false;
  volumeBediening.bevestigd = waarde;
  toonSoundboardvolume(waarde);
}

function koppelAlgemeenEffectvolume() {
  koppelVolumeSchuif(element('algemeen-effectvolume'));
  element('effectvolume-reset').addEventListener('click', () => planSoundboardvolume(75, true));
}

async function laadGeluidsnormalisatie() {
  const keuze = element("normalisatie-keuze");
  try {
    const antwoord = await vraagAanPython("GET", "/api/instellingen/normalisatie");
    if (!["uit", "subtiel", "normaal", "sterk"].includes(antwoord.stand)) {
      throw new Error("Onbekende normalisatiestand ontvangen.");
    }
    toestand.normalisatiestand = antwoord.stand;
    keuze.value = antwoord.stand;
    keuze.disabled = false;
  } catch (fout) {
    keuze.disabled = true;
    element("normalisatie-uitleg").textContent = "De instelling is niet bereikbaar. Herlaad het dashboard.";
    throw fout;
  }
}

function koppelGeluidsnormalisatie() {
  const keuze = element("normalisatie-keuze");
  keuze.addEventListener("change", () => voerGebruikersactieUit("Normalisatie instellen", async () => {
    const vorige = toestand.normalisatiestand;
    keuze.disabled = true;
    try {
      const antwoord = await vraagAanPython("POST", "/api/instellingen/normalisatie", { stand: keuze.value });
      toestand.normalisatiestand = antwoord.stand;
      keuze.value = antwoord.stand;
      gebruikPreviewNormalisatie(toestand.preview, true);
      gebruikPreviewNormalisatie(toestand.editorVoorbeeld);
      toonMelding("Geluidsnormalisatie opgeslagen. Een lopende Preview schakelt direct mee; uitzenden gebruikt de nieuwe stand vanaf het volgende fragment.");
    } catch (fout) {
      keuze.value = vorige;
      throw fout;
    } finally {
      keuze.disabled = false;
    }
  }));
}

async function laadPiekbeveiliging() {
  const knop = element("knop-limiter");
  const instelling = await vraagAanPython("GET", "/api/instellingen/pieklimiter");
  if (typeof instelling.ingeschakeld !== "boolean") throw new Error("Limiterinstelling is ongeldig.");
  toestand.limiterAan = instelling.ingeschakeld;
  knop.setAttribute("aria-checked", String(toestand.limiterAan));
  knop.disabled = false;
}

function koppelPiekbeveiliging() {
  const knop = element("knop-limiter");
  knop.addEventListener("click", () => voerGebruikersactieUit("Piekbeveiliging instellen", async () => {
    knop.disabled = true;
    try {
      const antwoord = await vraagAanPython("POST", "/api/instellingen/pieklimiter", {
        ingeschakeld: !toestand.limiterAan
      });
      if (typeof antwoord.ingeschakeld !== "boolean") throw new Error("Limiterstatus ongeldig.");
      toestand.limiterAan = antwoord.ingeschakeld;
      knop.setAttribute("aria-checked", String(toestand.limiterAan));
      if (!toestand.limiterAan) toonLimiterReductie(0, false);
      toonMelding(`Piekbeveiliging ${toestand.limiterAan ? "ingeschakeld" : "uitgeschakeld"}. Dit geldt direct voor de uitvoermix.`);
    } finally {
      knop.disabled = false;
    }
  }));
}

// Alleen bij de eerste weergave verbinden als precies één fysieke WASAPI-
// microfoon overblijft. Nooit automatisch na handmatig Verbreken of bij
// een onduidelijke of ontbrekende virtuele kabel. Een fout geeft geen lus.
function magAutomatischVerbinden() {
  return !toestand.automatischeVerbindingGeprobeerd &&
    !toestand.microfoonHandmatigGekozen &&
    Boolean(toestand.automatischEenMicrofoon) &&
    element('microfoonkeuze').value === toestand.automatischEenMicrofoon &&
    toestand.status?.toestand === 'verbroken' &&
    toestand.vbCable?.status === 'gereed' && toestand.vbCable?.bruikbaar === true &&
    !isAutomatischeVerbindingOnderdrukt();
}

function isAutomatischeVerbindingOnderdrukt() {
  try { return window.sessionStorage.getItem('drost-handmatig-verbroken') === 'ja'; }
  catch (_) { return false; }
}
function markeerHandmatigVerbroken(uit) {
  try {
    if (uit) window.sessionStorage.setItem('drost-handmatig-verbroken', 'ja');
    else window.sessionStorage.removeItem('drost-handmatig-verbroken');
  } catch (_) { /* Opslag niet beschikbaar: nog steeds één automatische poging. */ }
}
async function verbindEnigeMicrofoonBijStart() {
  if (!magAutomatischVerbinden()) return;
  toestand.automatischeVerbindingGeprobeerd = true;
  // Herlees de status op de server. Een tweede tab kan inmiddels al verbinden.
  const laatste = await vraagAanPython('GET','/api/status');
  toestand.status = laatste;
  if (laatste.toestand !== 'verbroken') return;
  toestand.automatischeVerbindingBezig = true;
  try { await schakelMicrofoonverbinding(); }
  finally { toestand.automatischeVerbindingBezig = false; }
}

// Wisselt op basis van actuele serverstatus. De audiodriver draait in Python;
// dit regelt uitsluitend één gebruikersactie, met bescherming tegen dubbelklikken.
async function schakelMicrofoonverbinding() {
  const automatisch = Boolean(toestand.automatischeVerbindingBezig);
  if (toestand.verbindingInBehandeling) return;
  toestand.verbindingInBehandeling = true;
  werkVerbindingsknopBij(toestand.status);
  try {
    // Beoordeel de status opnieuw op de server: een verouderde browserstatus
    // mag de verkeerde actie niet uitvoeren tijdens herstart of audioherstel.
    const actueleStatus = await vraagAanPython("GET", "/api/status");
    toestand.status = actueleStatus;
    if (actueleStatus.toestand === "verbonden") {
      if (automatisch) return;
      stopPreview();
      await vraagAanPython("POST", "/api/verbreken", {});
      if (!automatisch) markeerHandmatigVerbroken(true);
      toonMelding("Verbinding wordt verbroken.");
    } else if (["verbroken", "fout"].includes(actueleStatus.toestand)) {
      if (toestand.vbCable && ["ontbreekt", "onvolledig", "meerdere"].includes(toestand.vbCable.status)) {
        element("vb-cable-waarschuwing").scrollIntoView({ behavior: "smooth", block: "center" });
        element("vb-cable-opnieuw").focus({ preventScroll: true });
        return;
      }
      const nummer = element("microfoonkeuze").value;
      if (!nummer) throw new Error("Kies eerst een microfoon.");
      await vraagAanPython("POST", "/api/verbinden", { microfoonnummer: Number(nummer) });
      if (!automatisch) markeerHandmatigVerbroken(false);
      toonMelding(automatisch ? "Enige microfoon automatisch verbonden." : "De microfoon wordt verbonden.");
    } // Tijdens verbinden of verbreken wordt een tweede aanvraag genegeerd.
  } finally {
    toestand.verbindingInBehandeling = false;
    werkVerbindingsknopBij(toestand.status);
    await vernieuwStatus();
  }
}

// 6.1 Beta 2: pictogrammen en intensiteiten leven alleen onder Instellingen.
// De catalogus komt van Python, zodat live-DSP, preview en UI dezelfde lijst delen.
const STEM_ICON_PADEN = Object.freeze({
  monsterkoor: 'M5 8L3 3l5 2 M19 8l2-5-5 2 M5 8c0-5 14-5 14 0v7c0 7-14 7-14 0z M8 11h1 M15 11h1 M8 16h8 M10 16v3 M14 16v3 M2 10v6 M22 10v6',
  ruimtepak: 'M4 13V9a8 8 0 0 1 16 0v4 M7 7h10v7H7z M4 12H2v5h4 M20 12h2v5h-4 M6 17v4h12v-4 M9 18h6 M11 10h2',
  spook: 'M5 21V9a7 7 0 0 1 14 0v12l-3-3-4 3-4-3z M9 9v2 M15 9v2 M10 14q2 3 4 0',
  retrocomputer: 'M3 3h18v13H3z M9 16v4 M15 16v4 M6 21h12 M6 7l3 3-3 3 M12 12h5',
  mic: 'M12 2a3 3 0 0 1 3 3v7a3 3 0 0 1-6 0V5a3 3 0 0 1 3-3z M5 10a7 7 0 0 0 14 0 M12 17v5 M8 22h8',
  radio: 'M4 10h16v11H4z M7 14h3 M7 17h3 M16 14a2 2 0 1 0 .01 0 M6 10L17 3',
  bot: 'M5 8h14v12H5z M12 8V4 M10 4h4 M9 13h.1 M15 13h.1 M9 17h6',
  'arrow-down': 'M12 3v18 M5 14l7 7 7-7',
  'chevrons-down': 'M4 5l8 8 8-8 M4 13l8 8 8-8',
  'arrow-up': 'M12 21V3 M5 10l7-7 7 7',
  'chevrons-up': 'M4 19l8-8 8 8 M4 11l8-8 8 8',
  orbit: 'M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18 M3 14c5-10 15-12 18-7 M3 14c6-2 12-3 18-7 M15 11h.01',
  phone: 'M5 3l5 5-2 3c1 3 4 5 6 6l3-2 4 5c-2 3-5 3-8 2C6 18 2 12 2 6c0-2 1-3 3-3',
  skull: 'M12 3c5 0 9 4 9 9 0 3-2 5-4 6v3H7v-3c-2-1-4-3-4-6 0-5 4-9 9-9z M8 12h.1 M16 12h.1 M10 17v3 M14 17v3',
  waves: 'M2 12c3-5 5-5 8 0s5 5 8 0 4-5 4-5 M2 19c3-5 5-5 8 0s5 5 8 0 4-5 4-5',
  megaphone: 'M3 10l14-6v16L3 14z M3 10v4 M8 15l2 6h3l-2-7',
  smile: 'M12 2a10 10 0 1 0 0 20a10 10 0 0 0 0-20 M8 10h.1 M16 10h.1 M8 15c2 3 6 3 8 0',
  sparkles: 'M12 2l2.4 7.4L22 12l-7.6 2.6L12 22l-2.4-7.4L2 12l7.6-2.6z',
  'user-round': 'M12 12a5 5 0 1 0 0-10a5 5 0 1 0 0 10 M4 21c0-8 16-8 16 0',
  flower: 'M12 6a3 3 0 1 0 0-6a3 3 0 0 0 0 6 M12 18a3 3 0 1 0 0 6a3 3 0 0 0 0-6 M6 12a3 3 0 1 0-6 0a3 3 0 0 0 6 0 M18 12a3 3 0 1 0 6 0a3 3 0 0 0-6 0 M12 12a3 3 0 1 0 0-6a3 3 0 0 0 0 6z',
  gamepad: 'M6 8h12l4 10-3 3-4-3H9l-4 3-3-3z M8 11v6 M5 14h6 M16 12h.1 M19 15h.1',
  music: 'M9 18V5l12-2v13 M9 9l12-2 M9 18a3 3 0 1 1-3-3c2 0 3 1 3 3 M21 16a3 3 0 1 1-3-3c2 0 3 1 3 3',
  'nova-basis': 'M12 3a5 5 0 1 0 0 10a5 5 0 0 0 0-10 M4 21c0-8 16-8 16 0 M20 3v5 M18 5h4',
  'nova-warm': 'M6 3v9a6 6 0 0 0 12 0V3 M12 3v12 M8 18h8 M12 18v4',
  'nova-helder': 'M12 2v4 M12 18v4 M2 12h4 M18 12h4 M5 5l3 3 M16 16l3 3 M19 5l-3 3 M8 16l-3 3 M12 8a4 4 0 1 0 0 8a4 4 0 0 0 0-8',
  'nova-radio': 'M3 8h18v13H3z M6 8l12-6 M7 12h.1 M7 16h.1 M12 12h6 M12 16h6',
  'radio-tower': 'M12 5v16 M8 21h8 M12 5l-5 7 M12 5l5 7 M6 4a9 9 0 0 0-2 12 M18 4a9 9 0 0 1 2 12 M8 8a5 5 0 0 0-1 8 M16 8a5 5 0 0 1 1 8 M11 4h2',

});
let bewaarStemintensiteitTimer = null;
let stemintensiteitOpdrachten = Promise.resolve();
let stemparameterOpdrachten = Promise.resolve();
let bewaarStemparameterTimer = null;
let stemDemoVolgnummer = 0;
let stemDemoController = null;
let stemDemoUrl = null;
let stemDemoVerzoek = null;
let stemDemoBezig = false;
let stemDemoBron = false;

function natuurlijkeStemGekozen() {
  return Boolean(toestand.natuurlijkeStem?.gekozen ?? toestand.natuurlijkeStem?.aan);
}
function gekozenStemId() {
  return natuurlijkeStemGekozen() ? (toestand.natuurlijkeStem?.variant || 'llvc_basis') : toestand.stemprofiel;
}
const VERVALLEN_STEMPROFIELEN = new Set(['jongen', 'meisje', 'oudeman', 'oudevrouw']);

function alleStemkeuzes() {
  return [...toestand.stemprofielen, ...(toestand.natuurlijkeStem?.varianten || [])]
    .filter(profiel => !VERVALLEN_STEMPROFIELEN.has(profiel.id));
}
function stemkeuzeActief() {
  return natuurlijkeStemGekozen() ? toestand.natuurlijkeStem?.aan === true : toestand.stemactief;
}
function stemLaadInformatie() {
  const opdracht = toestand.stemkeuzeOpdracht;
  const id = opdracht?.keuze || gekozenStemId();
  const naam = alleStemkeuzes().find(p => p.id === id)?.naam || 'Gekozen stem';
  if (applicatieVerbinding.bereikbaar === false) return {bezig:false, id, fout:true, tekst:'De app is niet bereikbaar. De stemstatus kan niet worden bevestigd.'};
  if (toestand.stemkeuzeBezig) return {bezig:true, id, tekst:opdracht?.actie === 'schakel'
    ? (opdracht.aan ? `${naam} inschakelen…` : 'Stem uitschakelen…') : `Wisselen naar ${naam}…`};
  if (natuurlijkeStemGekozen() && toestand.natuurlijkeStem?.aan) {
    const status = toestand.natuurlijkeStem;
    if (status.toestand === 'laden') return {bezig:true, id, tekst:`${naam} laden… Je microfoon blijft intussen gedempt.`};
    if (status.toestand === 'fout') return {bezig:false, id, fout:true, tekst:status.melding || 'Stem niet beschikbaar. Je microfoon is gedempt.'};
    if (status.toestand === 'gereed') return {bezig:false, id, tekst:`${naam} gereed. Verbind de microfoon of start je microfoontest.`};
  }
  return {bezig:false, id, tekst:stemkeuzeActief() && id !== 'normaal' ? `Actief: ${naam}` : `${naam} geselecteerd, uitgeschakeld`};
}

function werkStemLaadstatusBij() {
  const info = stemLaadInformatie();
  const tekst = element('stem-laadstatus');
  if (tekst) { tekst.textContent = info.tekst; tekst.dataset.fout = String(Boolean(info.fout)); toonLaadindicator(tekst, info.bezig); }
  const snel = element('snel-stem-status');
  snel.textContent = info.tekst; toonLaadindicator(snel, info.bezig);
  for (const id of ['knop-natuurlijke-stem', 'knop-snel-stem']) {
    const knop = element(id); if (!knop) continue;
    toonLaadindicator(knop, info.bezig);
    if (toestand.stemkeuzeBezig) {
      knop.disabled = true;
      knop.textContent = toestand.stemkeuzeOpdracht?.actie === 'schakel'
        ? (toestand.stemkeuzeOpdracht.aan ? 'Inschakelen…' : 'Uitschakelen…') : 'Stem wisselen…';
    } else if (info.bezig) {
      knop.textContent = 'Laden… Uitzetten';
      knop.title = 'De stem wordt geladen. Klik om de stemvervormer uit te zetten.';
    } else knop.title = '';
  }
  document.querySelectorAll('.stemprofiel-kaart').forEach(kaart => {
    toonLaadindicator(kaart, info.bezig && kaart.dataset.profiel === info.id);
  });
}

function werkVoorbeeldBedieningBij() {
  const gedeeld = toestand.stemvoorbeeldActief || toestand.stemvoorbeeldBezig || toestand.stemkeuzeBezig || toestand.natuurlijkeStem?.test_bezig;
  const modelLaadt = natuurlijkeStemGekozen() && (!toestand.natuurlijkeStem?.beschikbaar || toestand.natuurlijkeStem?.toestand === 'laden');
  const knop = element('knop-stem-demo'), bron = element('knop-stem-demo-bron');
  knop.disabled = Boolean(gedeeld || modelLaadt || stemDemoBezig);
  bron.disabled = Boolean(gedeeld || stemDemoBezig);
  knop.textContent = stemDemoBezig && !stemDemoBron ? 'Voorbeeld voorbereiden…' : 'Voorbeeld afspelen';
  bron.textContent = stemDemoBezig && stemDemoBron ? 'Bron voorbereiden…' : 'Bron beluisteren';
  toonLaadindicator(knop, stemDemoBezig && !stemDemoBron);
  toonLaadindicator(bron, stemDemoBezig && stemDemoBron);
  toonLaadindicator(element('stem-demo-status'), stemDemoBezig);
  const stop = element('knop-stem-demo-stop');
  if (stop) stop.disabled = !stemDemoBezig && !element('stem-demo-audio').getAttribute('src');
}

function neemSteminstellingenOver(data) {
  if (!Array.isArray(data.profielen) || !data.profielen.some(p => p.id === data.profiel))
    throw new Error('Stemprofielen konden niet worden geladen.');
  const migratie = element('stem-migratiemelding');
  if (migratie) {
    migratie.textContent = typeof data.migratiemelding === 'string' ? data.migratiemelding : '';
    migratie.hidden = !migratie.textContent;
  }
  toestand.stemprofiel = data.profiel;
  toestand.stemactief = data.actief === true;
  toestand.stemprofielen = data.profielen;
  toestand.stemintensiteiten = data.intensiteiten || {};
  toestand.stemparameters = data.effectparameters || {};
  toestand.stemparametersCatalogus = data.parameters_catalogus || {};
  toestand.voorbeeldspreker = data.voorbeeldspreker || 'bob';
  element('stem-demo-spreker').value = toestand.voorbeeldspreker;
  toestand.stemvoorbeeldActief = Boolean(data.preview?.actief);
  if (data.natuurlijke_stem) toestand.natuurlijkeStem = data.natuurlijke_stem;
  element('stemprofiel-keuze').disabled = false;
  bouwStemprofielKaarten(); vulSnelleStemkeuze();
  werkNatuurlijkeStemBij(toestand.natuurlijkeStem); werkStemvoorbeeldKnopBij();
}
async function stuurStemkeuze(keuze) {
  if (toestand.stemkeuzeBezig || toestand.natuurlijkeStem?.test_bezig) return;
  if (keuze === gekozenStemId()) return;
  toestand.stemkeuzeOpdracht = {actie:'kies', keuze};
  toestand.stemkeuzeBezig = true; ++toestand.stemkeuzeGeneratie;
  stopVoorbeeldstem(); werkStemprofielKaartenBij();
  try {
    await bewaarStemintensiteitNu(); await bewaarStemparametersNu();
    const data = await vraagAanPython('POST', '/api/stemkeuze', {keuze});
    neemSteminstellingenOver(data);
    element('stem-demo-status').textContent = 'Stem gekozen. Met Voorbeeld afspelen hoor je Bob of Elise.';
  } catch (fout) {
    try { neemSteminstellingenOver(await vraagAanPython('GET','/api/stemkeuze')); } catch { /* Behoud de laatste bevestigde keuze. */ }
    throw fout;
  } finally { toestand.stemkeuzeBezig = false; toestand.stemkeuzeOpdracht = null; ++toestand.stemkeuzeGeneratie; werkStemprofielKaartenBij(); werkNatuurlijkeStemBij(toestand.natuurlijkeStem); }
}
async function schakelGekozenStem() {
  if (toestand.stemkeuzeBezig || toestand.natuurlijkeStem?.test_bezig) return;
  if (!stemkeuzeActief() && gekozenStemId() === 'normaal') {
    toonMelding('Kies eerst een stemprofiel om in te schakelen.'); return;
  }
  const aan = !stemkeuzeActief();
  toestand.stemkeuzeOpdracht = {actie:'schakel', aan, keuze:gekozenStemId()};
  toestand.stemkeuzeBezig = true; ++toestand.stemkeuzeGeneratie;
  stopVoorbeeldstem(); werkStemprofielKaartenBij();
  try { neemSteminstellingenOver(await vraagAanPython('POST','/api/stemkeuze/actief',{aan})); }
  catch (fout) {
    try { neemSteminstellingenOver(await vraagAanPython('GET','/api/stemkeuze')); } catch { /* Geen aangenomen succes. */ }
    throw fout;
  } finally { toestand.stemkeuzeBezig = false; toestand.stemkeuzeOpdracht = null; ++toestand.stemkeuzeGeneratie; werkStemprofielKaartenBij(); werkNatuurlijkeStemBij(toestand.natuurlijkeStem); }
}

async function speelVoorbeeldstemAf(bron = false) {
  if (toestand.stemvoorbeeldActief || toestand.stemvoorbeeldBezig || toestand.stemkeuzeBezig) return;
  stopVoorbeeldstem();
  const nummer = stemDemoVolgnummer;
  const verzoek = 'demo_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2);
  stemDemoVerzoek = verzoek; stemDemoBezig = true; stemDemoBron = bron;
  const keuze = gekozenStemId();
  const naam = bron ? 'Bron zonder stemvervorming' : (alleStemkeuzes().find(p => p.id === keuze)?.naam || keuze);
  element('stem-demo-status').textContent = `${toestand.voorbeeldspreker === 'bob' ? 'Bob' : 'Elise'}: ${naam} wordt voorbereid…`;
  element('stem-demo-status').dataset.fout = 'false';
  werkVoorbeeldBedieningBij();
  try {
    await bewaarStemintensiteitNu(); await bewaarStemparametersNu();
    if (nummer !== stemDemoVolgnummer) return;
    stemDemoController = new AbortController();
    const pad = bron
      ? `/api/stemkeuze/bron?spreker=${encodeURIComponent(toestand.voorbeeldspreker)}&verzoek=${verzoek}`
      : `/api/stemkeuze/voorbeeld?spreker=${encodeURIComponent(toestand.voorbeeldspreker)}&keuze=${encodeURIComponent(keuze)}&verzoek=${verzoek}`;
    const antwoord = await haalBijApplicatie(pad,{method:'GET',cache:'no-store',signal:stemDemoController.signal,headers:{'X-Drost-Token':beveiligingscode}});
    if (!antwoord.ok) {
      let inhoud = {}; try { inhoud = await antwoord.json(); } catch {}
      throw maakAntwoordfout(inhoud,antwoord.status);
    }
    const wav = await antwoord.blob();
    if (nummer !== stemDemoVolgnummer) return;
    stemDemoUrl = URL.createObjectURL(wav);
    const speler = element('stem-demo-audio'); speler.src = stemDemoUrl;
    await speler.play();
    if (nummer === stemDemoVolgnummer) element('stem-demo-status').textContent = `${naam}: voorbeeld speelt alleen lokaal.`;
  } catch (fout) {
    if (nummer !== stemDemoVolgnummer || fout.name === 'AbortError') return;
    element('stem-demo-status').textContent = fout.message || 'Het voorbeeld kon niet worden afgespeeld.';
    element('stem-demo-status').dataset.fout = 'true';
    throw fout;
  } finally {
    if (nummer === stemDemoVolgnummer) { stemDemoBezig = false; stemDemoVerzoek = null; werkVoorbeeldBedieningBij(); }
  }
}

function stopVoorbeeldstem() {
  ++stemDemoVolgnummer;
  if (stemDemoController) stemDemoController.abort();
  if (stemDemoVerzoek) {
    haalBijApplicatie('/api/stemkeuze/voorbeeld/stop',{method:'POST',keepalive:true,
      headers:{'X-Drost-Token':beveiligingscode,'Content-Type':'application/json'},
      body:JSON.stringify({verzoek:stemDemoVerzoek})}).catch(() => {});
  }
  stemDemoVerzoek = null; stemDemoBezig = false;
  const speler = element('stem-demo-audio'); speler.pause(); speler.removeAttribute('src');
  if (stemDemoUrl) URL.revokeObjectURL(stemDemoUrl);
  stemDemoUrl = null; werkVoorbeeldBedieningBij();
}

function bouwStemparameters() {
  const paneel = element('stem-extra-paneel');
  const velden = natuurlijkeStemGekozen() ? [] : (toestand.stemparametersCatalogus[toestand.stemprofiel] || []);
  paneel.hidden = !velden.length;
  const raster = element('stem-extra-velden');
  raster.replaceChildren();
  if (!velden.length) return;
  const params = toestand.stemparameters[toestand.stemprofiel];
  if (!params) return;
  for (const veld of velden) {
    const rij = document.createElement('div');
    rij.className = 'stem-extra-veld';
    const label = document.createElement('label');
    const naam = document.createElement('span');
    naam.textContent = veld.label;
    const waarde = document.createElement('output');
    waarde.textContent = `${params[veld.id]}${veld.eenheid || ''}`;
    label.append(naam, waarde);
    const invoer = veld.type === 'select' ? document.createElement('select') : document.createElement('input');
    if (veld.type === 'select') {
      for (const optie of veld.keuzes) {
        const el = document.createElement('option');
        el.value = optie;
        el.textContent = optie;
        invoer.append(el);
      }
    } else {
      invoer.type = 'range';
      invoer.min = String(veld.min);
      invoer.max = String(veld.max);
      invoer.step = '1';
    }
    invoer.disabled = Boolean(toestand.natuurlijkeStem?.aan);
    invoer.value = String(params[veld.id]);
    const verander = () => {
      if (toestand.stemprofiel !== rij.dataset.profiel) return;
      const nieuw = veld.type === 'select' ? invoer.value : Number(invoer.value);
      toestand.stemparameters[toestand.stemprofiel][veld.id] = nieuw;
      waarde.textContent = `${nieuw}${veld.eenheid || ''}`;
      clearTimeout(bewaarStemparameterTimer);
      bewaarStemparameterTimer = setTimeout(bewaarStemparametersNu, 220);
    };
    rij.dataset.profiel = toestand.stemprofiel;
    invoer.addEventListener(veld.type === 'select' ? 'change' : 'input', verander);
    invoer.addEventListener('change', () => { verander(); bewaarStemparametersNu(); });
    rij.append(label, invoer);
    raster.append(rij);
  }
}

function bewaarStemparametersNu() {
  clearTimeout(bewaarStemparameterTimer);
  const profiel = toestand.stemprofiel;
  if (natuurlijkeStemGekozen() || !(profiel in toestand.stemparameters)) return stemparameterOpdrachten;
  const parameters = { ...toestand.stemparameters[profiel] };
  stemparameterOpdrachten = stemparameterOpdrachten.catch(() => {}).then(() =>
    vraagAanPython('POST', '/api/instellingen/stemparameters', {profiel, parameters})
  );
  stemparameterOpdrachten.catch(fout => toonMelding(`Effectinstelling opslaan mislukt: ${fout.message}`, true));
  return stemparameterOpdrachten;
}


function maakStemicoon(naam) {
  const namespace = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(namespace, 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('width', '25');
  svg.setAttribute('height', '25');
  svg.setAttribute('aria-hidden', 'true');
  svg.setAttribute('fill', 'none');
  svg.setAttribute('stroke', 'currentColor');
  svg.setAttribute('stroke-width', '1.75');
  svg.setAttribute('stroke-linecap', 'round');
  svg.setAttribute('stroke-linejoin', 'round');
  const lijn = document.createElementNS(namespace, 'path');
  lijn.setAttribute('d', STEM_ICON_PADEN[naam] || STEM_ICON_PADEN.mic);
  svg.append(lijn);
  return svg;
}

function vulStemopties(selectie) {
  selectie.replaceChildren();
  for (const profiel of alleStemkeuzes()) {
    selectie.append(new Option(profiel.naam, profiel.id));
  }
}

function bouwStemprofielKaarten() {
  const raster = element('stemprofielen-raster'); raster.replaceChildren();
  vulStemopties(element('stemprofiel-keuze'));
  for (const profiel of alleStemkeuzes()) {
    const knop = document.createElement('button'); knop.type = 'button'; knop.className = 'stemprofiel-kaart';
    knop.dataset.profiel = profiel.id; knop.dataset.motor = profiel.motor || 'effect';
    knop.title = profiel.beschrijving; knop.append(maakStemicoon(profiel.icoon));
    const naam = document.createElement('span'); naam.textContent = profiel.naam; knop.append(naam);
    if (profiel.motor === 'llvc') { const label = document.createElement('small'); label.textContent = profiel.label; knop.append(label); }
    knop.addEventListener('click', () => voerGebruikersactieUit('Stem kiezen', () => stuurStemkeuze(profiel.id)));
    raster.append(knop);
  }
  werkStemprofielKaartenBij();
}

function werkStemprofielKaartenBij({parameters = true} = {}) {
  const gekozen = gekozenStemId();
  const bezig = toestand.stemkeuzeBezig || toestand.natuurlijkeStem?.test_bezig;
  element('stemprofiel-keuze').value = gekozen;
  document.querySelectorAll('.stemprofiel-kaart').forEach(kaart => {
    kaart.setAttribute('aria-pressed',String(kaart.dataset.profiel === gekozen));
    kaart.disabled = Boolean(bezig || element('stemprofiel-keuze').disabled ||
      (kaart.dataset.motor === 'llvc' && !toestand.natuurlijkeStem?.beschikbaar));
  });
  const profiel = toestand.stemprofiel, natuurlijk = natuurlijkeStemGekozen();
  const waarde = toestand.stemintensiteiten[profiel];
  if (Number.isInteger(waarde)) { element('stemintensiteit-schuif').value=String(waarde); element('stemintensiteit-waarde').textContent=`${waarde}%`; }
  element('stemintensiteit-schuif').disabled = Boolean(bezig || natuurlijk || profiel === 'normaal');
  element('knop-stem-reset').disabled = Boolean(bezig || natuurlijk || profiel === 'normaal');
  element('knop-stem-reset-alles').disabled = Boolean(bezig || natuurlijk || !toestand.stemprofielen.length);
  element('stemintensiteit-schuif').closest('.stemintensiteit-paneel').hidden = natuurlijk;
  const info = alleStemkeuzes().find(p=>p.id===gekozen);
  const beschrijving = element('stem-keuze-beschrijving');
  if (element('stem-keuze-naam')) element('stem-keuze-naam').textContent=info?.naam || 'Normaal';
  if (beschrijving) beschrijving.textContent = (info?.beschrijving || '') +
    (natuurlijk ? ' Deze vier keuzes gebruiken hetzelfde getrainde model.' : '');
  if (parameters) bouwStemparameters(); werkSnelleStemweergaveBij(); werkVoorbeeldBedieningBij();
  werkStemLaadstatusBij();
}

function meterStemDb(rms, gemeten, vullingId, tekstId) {
  const waarde = Number(rms);
  const geldig = gemeten && Number.isFinite(waarde) && waarde > 0;
  // dBFS is de werkelijke digitale waarde. Alleen de breedte van de meter
  // wordt begrensd; een zacht signaal mag niet als "−60,0 dBFS" worden verzonnen.
  const decibel = geldig ? 20 * Math.log10(waarde) : null;
  const breedte = decibel === null ? 0 : Math.max(0, Math.min(100, (decibel + 72) / 72 * 100));
  element(vullingId).style.width = `${breedte}%`;
  element(tekstId).textContent = !gemeten ? '— dBFS'
    : decibel === null ? 'Stil'
    : decibel < -90 ? '< −90 dBFS'
    : `${decibel.toFixed(1).replace('.', ',')} dBFS`;
  return decibel;
}

function werkStemmetersBij(status) {
  const preview = status?.stemvoorbeeld || {};
  const lokaal = Boolean(preview.actief);
  const liveVerbinding = !lokaal && status?.toestand === 'verbonden';
  const gemeten = lokaal ? Boolean(preview.gemeten) :
    liveVerbinding && Boolean(status?.is_signaal_gemeten);
  const bron = lokaal ? preview : status;
  const binnen = meterStemDb(bron?.microfoon_rms, gemeten, 'stemmeters-in', 'stemmeters-in-db');
  meterStemDb(lokaal ? preview.stem_rms : status?.stem_rms, gemeten, 'stemmeters-uit', 'stemmeters-uit-db');
  const onderbrekingen = lokaal ? Number(preview.driverproblemen || 0) : Number(status?.bufferproblemen || 0);
  element('stemmeters-status').textContent = !(lokaal || liveVerbinding)
    ? 'Start Mijn eigen stem testen of verbind je microfoon.'
    : !gemeten ? 'Wachten op nieuwe audiometingen…'
    : onderbrekingen > 0
      ? `Audioapparaat meldt ${onderbrekingen} onderbreking(en). Controleer je driver bij gekraak.`
      : binnen !== null && binnen > -58 ? 'Microfoonsignaal ontvangen'
      : 'Geen of zeer zacht microfoonsignaal';
}

function werkStemvoorbeeldKnopBij() {
  const knop = element('knop-stemvoorbeeld');
  const actief = toestand.stemvoorbeeldActief;
  knop.textContent = actief ? 'Mijn stemtest stoppen' : 'Mijn eigen stem testen';
  knop.setAttribute('aria-pressed', String(actief));
  knop.disabled = toestand.stemvoorbeeldBezig || (!actief && (toestand.stemkeuzeBezig || (natuurlijkeStemGekozen() && (!toestand.natuurlijkeStem?.aan || !['gereed','actief'].includes(toestand.natuurlijkeStem?.toestand)))));
  if (!actief && natuurlijkeStemGekozen() && !toestand.natuurlijkeStem?.aan) element('stemvoorbeeld-status').textContent='Zet de gekozen karakterstem aan om je eigen microfoon te testen. Bob en Elise kun je ook zo beluisteren.';
  else if (element('stemvoorbeeld-status').textContent.startsWith('Zet de gekozen karakterstem')) element('stemvoorbeeld-status').textContent='Gebruik een koptelefoon. Verbreek eerst de liveverbinding om je microfoon lokaal te testen.';
  werkVoorbeeldBedieningBij();
}

async function laadStemprofiel() {
  neemSteminstellingenOver(await vraagAanPython('GET','/api/instellingen/stemprofiel'));
}

// Alle opslagverzoeken gaan na elkaar, zodat een oude schuifaanpassing een
// latere reset niet ongedaan kan maken. Geen opslag op de audiocallback.
function bewaarStemintensiteitNu() {
  clearTimeout(bewaarStemintensiteitTimer);
  if (!toestand.stemprofielen.length || natuurlijkeStemGekozen()) return stemintensiteitOpdrachten;
  const profiel = toestand.stemprofiel;
  const intensiteit = Number(toestand.stemintensiteiten[profiel]);
  stemintensiteitOpdrachten = stemintensiteitOpdrachten.catch(() => {}).then(async () => {
    await vraagAanPython('POST', '/api/instellingen/stemintensiteit', { profiel, intensiteit });
  });
  stemintensiteitOpdrachten.catch((fout) => toonMelding(`Intensiteit opslaan mislukt: ${fout.message}`, true));
  return stemintensiteitOpdrachten;
}

async function stopLokaleStempreview({ stil = false } = {}) {
  if (!toestand.stemvoorbeeldActief && !toestand.stemvoorbeeldBezig) return;
  await vraagAanPython('POST', "/api/stemvoorbeeld/stop", {});
  toestand.stemvoorbeeldActief = false;
  werkStemvoorbeeldKnopBij();
  werkStemmetersBij({});
  element('stemvoorbeeld-status').textContent = 'De lokale microfoonpreview is gestopt.';
  if (!stil) toonMelding('Stempreview gestopt.');
}

window.addEventListener("pagehide", () => {
  stopVoorbeeldstem();
  if (!toestand.stemvoorbeeldActief) return;
  haalBijApplicatie("/api/stemvoorbeeld/stop", {
    method: 'POST', keepalive: true,
    headers: { 'X-Drost-Token': beveiligingscode, 'Content-Type': 'application/json' },
    body: '{}'
  }).catch(() => {});
});

function koppelStemvervormer() {
  koppelStemcontrole();
  element('knop-natuurlijke-stem').addEventListener('click', () =>
    voerGebruikersactieUit('Stemvervormer', schakelGekozenStem));
  element('knop-stem-demo-stop').addEventListener('click', () => {
    stopVoorbeeldstem(); element('stem-demo-status').textContent = 'Voorbeeld gestopt.';
  });
  element('stem-demo-audio').addEventListener('ended', () => {
    stopVoorbeeldstem();
    element('stem-demo-status').textContent = 'Voorbeeld afgerond. Klik op Voorbeeld afspelen om het opnieuw te horen.';
    element('stem-demo-audio').removeAttribute('src'); werkVoorbeeldBedieningBij();
  });
  element('stem-demo-spreker').addEventListener('change', () => voerGebruikersactieUit('Voorbeeldstem kiezen', async () => {
    stopVoorbeeldstem();
    const spreker = element('stem-demo-spreker').value;
    const antwoord = await vraagAanPython('POST','/api/instellingen/stemvoorbeeldspreker', {spreker});
    toestand.voorbeeldspreker = antwoord.voorbeeldspreker;
    element('stem-demo-status').textContent = 'Spreker geselecteerd. Klik op Voorbeeld afspelen om te luisteren.';
  }));
  element('knop-stem-demo').addEventListener('click', () =>
    voerGebruikersactieUit('Voorbeeldstem afspelen', speelVoorbeeldstemAf));
  element('knop-stem-demo-bron').addEventListener('click', () =>
    voerGebruikersactieUit('Bron beluisteren', () => speelVoorbeeldstemAf(true)));
  const keuze = element('stemprofiel-keuze');
  keuze.addEventListener('change', () => voerGebruikersactieUit('Stemprofiel kiezen', () => stuurStemkeuze(keuze.value)));

  const schuif = element('stemintensiteit-schuif');
  schuif.addEventListener('input', () => {
    toestand.stemintensiteiten[toestand.stemprofiel] = Number(schuif.value);
    element('stemintensiteit-waarde').textContent = `${schuif.value}%`;
    clearTimeout(bewaarStemintensiteitTimer);
    bewaarStemintensiteitTimer = setTimeout(bewaarStemintensiteitNu, 180);
  });
  schuif.addEventListener('change', bewaarStemintensiteitNu);

  element('knop-stem-reset').addEventListener('click', () => voerGebruikersactieUit('Profiel resetten', async () => {
    clearTimeout(bewaarStemintensiteitTimer);
    await stemintensiteitOpdrachten.catch(() => {});
    await stemparameterOpdrachten.catch(() => {});
    const result = await vraagAanPython('POST', '/api/instellingen/stemintensiteit/herstel', { profiel: toestand.stemprofiel });
    toestand.stemintensiteiten = result.intensiteiten;
    if (toestand.stemprofiel in toestand.stemparameters) {
      const params = await vraagAanPython('POST','/api/instellingen/stemparameters/herstel',{profiel:toestand.stemprofiel});
      toestand.stemparameters = params.effectparameters;
    }
    werkStemprofielKaartenBij();
    toonMelding('Standaardintensiteit voor dit profiel hersteld.');
  }));
  element('knop-stem-reset-alles').addEventListener('click', () => voerGebruikersactieUit('Alle stemprofielen resetten', async () => {
    if (!window.confirm('Alle intensiteiten van de stemprofielen terugzetten naar de standaardwaarden?')) return;
    clearTimeout(bewaarStemintensiteitTimer);
    await stemintensiteitOpdrachten.catch(() => {});
    await stemparameterOpdrachten.catch(() => {});
    const result = await vraagAanPython('POST', '/api/instellingen/stemintensiteit/herstel-alles', {});
    toestand.stemintensiteiten = result.intensiteiten;
    const params = await vraagAanPython('POST','/api/instellingen/stemparameters/herstel-alles',{});
    toestand.stemparameters = params.effectparameters;
    werkStemprofielKaartenBij();
    toonMelding('Standaardintensiteiten van alle stemprofielen hersteld.');
  }));

  element('knop-stemvoorbeeld').addEventListener('click', () => voerGebruikersactieUit('Stempreview', async () => {
    if (toestand.stemvoorbeeldBezig) return;
    toestand.stemvoorbeeldBezig = true;
    werkStemvoorbeeldKnopBij();
    try {
      if (toestand.stemvoorbeeldActief) {
        await stopLokaleStempreview();
        return;
      }
      if ((toestand.status?.toestand || 'verbroken') !== 'verbroken') {
        element('stemvoorbeeld-status').textContent =
          'Verbreek eerst de live microfoonverbinding om je eigen stem lokaal te testen.';
        toonMelding('Stempreview: Verbreek eerst de liveverbinding voordat je je stem lokaal beluistert.', true);
        return;
      }
      stopVoorbeeldstem();
      element('stem-demo-status').textContent = 'Je eigen microfoon wordt getest; Bob en Elise worden niet afgespeeld.';
      const nummer = element('microfoonkeuze').value;
      if (!nummer) throw new Error('Kies eerst een microfoon op het dashboard.');
      const uitvoer = element('monitor-uitvoer').value;
      const result = await vraagAanPython('POST', "/api/stemvoorbeeld/start", {
        microfoonnummer: Number(nummer), uitvoernummer: uitvoer ? Number(uitvoer) : null
      });
      toestand.stemvoorbeeldActief = Boolean(result.actief);
      element('stemvoorbeeld-status').textContent = 'Je hoort nu de bewerkte microfoon via je eigen luisterapparaat.';
      toonMelding('Lokale stempreview gestart. Het geluid wordt niet uitgezonden.');
    } finally {
      toestand.stemvoorbeeldBezig = false;
      werkStemvoorbeeldKnopBij();
    }
  }));
}

function vulSnelleStemkeuze(){
  const keuze=element('snel-stem-keuze'); keuze.replaceChildren();
  vulStemopties(keuze);
  werkSnelleStemweergaveBij();
}
function werkSnelleStemweergaveBij(){
  const gekozen=gekozenStemId(), natuurlijk=natuurlijkeStemGekozen();
  const bezig=Boolean(toestand.stemkeuzeBezig || toestand.natuurlijkeStem?.test_bezig || !toestand.stemprofielen.length);
  const keuze=element('snel-stem-keuze'); keuze.disabled=bezig; keuze.value=gekozen;
  const knop=element('knop-snel-stem'); knop.disabled=bezig || (natuurlijk && !toestand.natuurlijkeStem?.beschikbaar && !stemkeuzeActief());
  const naam=alleStemkeuzes().find(p=>p.id===gekozen)?.naam || 'Normaal';
  const aan=stemkeuzeActief() && gekozen!=='normaal';
  knop.textContent=aan?'Uitschakelen':'Inschakelen';knop.setAttribute('aria-pressed',String(aan));
  element('snel-stem-status').textContent=natuurlijk && aan ? `${naam}: ${toestand.natuurlijkeStem.melding}`
    : aan ? `Actief: ${naam}` : `${naam} geselecteerd, uitgeschakeld`;
  werkStemLaadstatusBij();
}
function koppelSnelleStem(){
  element('snel-stem-keuze').addEventListener('change', () =>
    voerGebruikersactieUit('Stem kiezen', () => stuurStemkeuze(element('snel-stem-keuze').value)));
  element('knop-snel-stem').addEventListener('click', () => voerGebruikersactieUit('Stemvervormer', schakelGekozenStem));
}

/*
  Een wheelbeweging op het einde van de afspeelbibliotheek of mappenlijst
  moet direct het dashboard verder bewegen. Op Windows/Chromium kan scroll
  latching anders een paar wielbewegingen vasthouden op een lege lijstgrens.
  Binnen de lijst laten we de gewone browser-scrollwerking ongemoeid.
*/
function koppelDoorschuivenVanLijsten() {
  for (const id of ['bibliotheek-lijst', 'groepen-lijst']) {
    const lijst = element(id);
    if (!lijst) continue;
    lijst.addEventListener('wheel', (gebeurtenis) => {
      if (gebeurtenis.defaultPrevented || gebeurtenis.ctrlKey || gebeurtenis.metaKey ||
          gebeurtenis.shiftKey || !gebeurtenis.deltaY || document.querySelector('dialog:modal')) return;
      const ondergrens = Math.max(0, lijst.scrollHeight - lijst.clientHeight);
      const omlaag = gebeurtenis.deltaY > 0;
      const aanRand = omlaag ? lijst.scrollTop >= ondergrens - 1 : lijst.scrollTop <= 1;
      if (!aanRand) return;
      const pagina = document.scrollingElement;
      if (!pagina || pagina.scrollHeight <= pagina.clientHeight + 1) return;
      const stap = gebeurtenis.deltaY * (gebeurtenis.deltaMode === 1 ? 16
        : gebeurtenis.deltaMode === 2 ? window.innerHeight : 1);
      // Niet 'smooth': elke beweging moet meteen reageren, ook na Stop.
      const positie = Math.max(0, Math.min(pagina.scrollHeight - pagina.clientHeight,
        pagina.scrollTop + stap));
      if (positie === pagina.scrollTop) return;
      gebeurtenis.preventDefault();
      pagina.scrollTop = positie;
    }, { passive: false });
  }
}

function koppelAlleKnoppen() {
  koppelDoorschuivenVanLijsten();
  element('knop-app-vernieuwen').addEventListener('click', () => {
    if (element('dialoog-bewerken').open &&
        !window.confirm('Bij vernieuwen gaan niet-opgeslagen editorwijzigingen verloren. Pagina vernieuwen?')) return;
    window.location.reload();
  });
  element('groepen-zoeken').addEventListener('input', maakGroepenZichtbaar);
  koppelStemvervormer();
  koppelSnelleStem();
  koppelPiekbeveiliging();
  koppelGeluidsnormalisatie();
  document.addEventListener("pointerdown", (gebeurtenis) => {
    if (!gebeurtenis.target.closest("#geluid-actiemenu, .bibliotheek-acties-knop")) sluitGeluidActiemenu();
    if (!gebeurtenis.target.closest("#favoriet-actiemenu, .bewerk-vak")) sluitFavorietActiemenu();
  });
  window.addEventListener("resize", sluitGeluidActiemenu);
  window.addEventListener("scroll", (gebeurtenis) => {
    if (!element("geluid-actiemenu").contains(gebeurtenis.target)) sluitGeluidActiemenu();
  }, true);
  document.addEventListener("keydown", (gebeurtenis) => {
    if (gebeurtenis.key === "Escape" && !element("favoriet-actiemenu").hidden) sluitFavorietActiemenu();
    if (gebeurtenis.key === "Escape" && !element("geluid-actiemenu").hidden) {
      gebeurtenis.preventDefault();
      gebeurtenis.stopPropagation();
      sluitGeluidActiemenu();
    }
  }, true);
  element("knop-exporteer-editor").addEventListener("click", () =>
    openLosseExport(toestand.gekozenGeluid, true));
  document.querySelectorAll("[data-exportformaat]").forEach((knop) => {
    knop.addEventListener("click", () => voerGebruikersactieUit(
      "Los bestand exporteren", () => downloadLosBestand(knop.dataset.exportformaat)
    ));
  });
  element("microfoonkeuze").addEventListener("change", () => {
    toestand.microfoonHandmatigGekozen = true;
    werkVerbindingsknopBij(toestand.status);
  });
  element("knop-vernieuw").addEventListener("click", () => voerGebruikersactieUit("Apparaten vernieuwen", async () => {
    await laadApparaten();
    await controleerVBCable();
  }));
  element("vb-cable-opnieuw").addEventListener("click", () => voerGebruikersactieUit("VB-CABLE controleren", async () => {
    await controleerVBCable({ toonBevestiging: true });
    await laadApparaten();
  }));
  element("knop-verbinden").addEventListener("click", () =>
    voerGebruikersactieUit("Microfoonverbinding wijzigen", schakelMicrofoonverbinding));
  element("knop-effecten").addEventListener("click", () =>
    voerGebruikersactieUit("Soundboard schakelen", schakelGeluidseffecten));
  const monitorAanpassen = () => voerGebruikersactieUit("Meeluisteren instellen", async () => {
    const aan = element("knop-monitor").getAttribute("aria-checked") !== "true";
    const nummer = element("monitor-uitvoer").value;
    toestand.laatstGekozenMonitor = nummer;
    await vraagAanPython("POST", "/api/monitor", { aan, uitvoernummer: nummer ? Number(nummer) : null });
    await vernieuwStatus();
  });
  element("knop-monitor").addEventListener("click", monitorAanpassen);
  element("knop-eigen-stem").addEventListener("click", () => voerGebruikersactieUit("Eigen stem horen wijzigen", async () => {
    const aan = element("knop-eigen-stem").getAttribute("aria-checked") !== "true";
    const volume = Number(element("eigen-stem-volume").value);
    await vraagAanPython("POST", "/api/monitor-stem", {aan, volume});
    await vernieuwStatus();
  }));
  element("eigen-stem-volume").addEventListener("input", () => {
    element("eigen-stem-volume-tekst").textContent = `${element("eigen-stem-volume").value}%`;
  });
  element("eigen-stem-volume").addEventListener("change", () => voerGebruikersactieUit("Stemmonitorvolume instellen", async () => {
    const volume = Number(element("eigen-stem-volume").value);
    await vraagAanPython("POST", "/api/monitor-stem", {aan: true, volume});
    await vernieuwStatus();
  }));
  element("monitor-uitvoer").addEventListener("change", () => voerGebruikersactieUit("Luisterapparaat aanpassen", async () => {
    const nummer = element("monitor-uitvoer").value;
    toestand.laatstGekozenMonitor = nummer;
    await vraagAanPython("POST", "/api/monitor", {
      aan: Boolean(toestand.status?.meeluisteren_aan), uitvoernummer: nummer ? Number(nummer) : null
    });
    await vernieuwStatus();
  }));
  element("knop-stop").addEventListener("click", () => {
    // Direct de lokale preview sluiten, ook als een vorige start nog loopt.
    stopPreview();
    planExclusieveSpeleractie('Geluid stoppen', 'gestopt', async () => {
      await vraagAanPython('POST', '/api/stop', {});
      if (toestand.live?.animatie) cancelAnimationFrame(toestand.live.animatie);
      toestand.live?.videobediening?.stop();
      toestand.live = null; toestand.verwachtGeluid = null;
      werkActieveKaartenBij(); toonStilMediascherm();
    });
  });
  element("knop-preview-stop").addEventListener("click", () => stopPreview());
  koppelPreviewSpelerbediening();
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !element("knop-stop").disabled && !document.querySelector("dialog[open]")) {
      e.preventDefault(); element("knop-stop").click();
    }
  });
  element("knop-nieuwe-groep").addEventListener("click", () => {
    element("nieuwe-groepsnaam").value = "";
    element("dialoog-groep").dataset.ouderId = "";
    element("dialoog-groep").showModal();
    element("nieuwe-groepsnaam").focus();
  });
  element("formulier-groep").addEventListener("submit", (event) => {
    event.preventDefault();
    voerGebruikersactieUit("Groep maken", async () => {
      const antwoord = await vraagAanPython("POST", "/api/groepen", { naam: element("nieuwe-groepsnaam").value.trim(), ouder_id: element("dialoog-groep").dataset.ouderId || null });
      element("dialoog-groep").close();
      toestand.actieveGroep = antwoord.groep_id;
      await laadBibliotheekOpnieuw();
      toonMelding("Groep aangemaakt.");
    });
  });
  element("trim-begin").addEventListener("input", () =>
    stelSelectieInEditorIn(Number(element("trim-begin").value), Number(element("trim-eind").value), "begin"));
  element("trim-eind").addEventListener("input", () =>
    stelSelectieInEditorIn(Number(element("trim-begin").value), Number(element("trim-eind").value), "einde"));
  element("bewerken-start").addEventListener("change", () => {
    const begin = Number(element("bewerken-start").value);
    stelSelectieInEditorIn(begin, begin + Number(element("bewerken-duur").value), "begin");
  });
  element("bewerken-duur").addEventListener("change", () => {
    const begin = Number(element("bewerken-start").value);
    stelSelectieInEditorIn(begin, begin + Number(element("bewerken-duur").value), "einde");
  });
  element('knop-editor-preview').addEventListener('click', startEditorPreviewExclusief);
  element('knop-editor-uitzenden').addEventListener('click', () =>
    voerGebruikersactieUit('Editorselectie uitzenden', startEditorUitzenden));
  element('knop-editor-stop').addEventListener('click', stopEditorGeluid);
  element('editor-groepen-zoeken').addEventListener('input', toonDoorzoekbareGroepenInEditor);
  element("knop-zoom-in").addEventListener("click", () => zoomInEditor(.5));
  element("knop-zoom-uit").addEventListener("click", () => zoomInEditor(2));
  element("knop-zoom-volledig").addEventListener("click", () => {
    const geluid = vindGeluid(toestand.gekozenGeluid);
    if (!geluid) return;
    const totaal = bepaalEditorBronduur(geluid);
    const maximaal = Math.min(totaal, 120);
    beperkEditorVenster(Math.max(0, Math.min(toestand.editorAfspeelpositie - maximaal / 2, totaal - maximaal)), maximaal);
  });
  koppelEditorAfspeelcursor();
  // Wanneer het venster smaller of breder wordt, tekenen we de reeds
  // gemeten golfvorm opnieuw. Er hoeft daarvoor geen MP3 te worden herlezen.
  if (typeof ResizeObserver !== "undefined") {
    const waarnemer = new ResizeObserver(() => {
      const gegevens = toestand.editorGolfvormData;
      if (gegevens && element("dialoog-bewerken").open) {
        tekenDeEchteGolfvorm(gegevens.pieken, gegevens.rms);
      }
    });
    waarnemer.observe(element("editor-golfvorm-gebied"));
  }
  document.addEventListener("keydown", (gebeurtenis) => {
    if (!magSpatieDeEditorBedienen(gebeurtenis)) return;
    gebeurtenis.preventDefault();
    startEditorPreviewExclusief();
  });
  element("dialoog-bewerken").addEventListener("close", () => {
    stopEditorPreview("editor_gesloten");
    toestand.editorIsAanHetSlepen = false;
    if (toestand.editorGolfvormWachttijd) clearTimeout(toestand.editorGolfvormWachttijd);
    toestand.golfvormVolgnummer++;
  });
  // Bibliotheek volledig opnieuw beginnen, met een aparte bevestiging.
  const resetDialoog = element('dialoog-bibliotheek-reset');
  const bevestiging = element('bibliotheek-reset-bevestiging');
  const resetKnop = element('knop-bibliotheek-reset-bevestig');
  element('knop-bibliotheek-reset-open').addEventListener('click', () => {
    bevestiging.value = '';
    resetKnop.disabled = true;
    resetDialoog.showModal();
    bevestiging.focus();
  });
  bevestiging.addEventListener('input', () => { resetKnop.disabled = bevestiging.value !== 'BEVESTIG'; });
  resetKnop.addEventListener('click', () => voerGebruikersactieUit('Bibliotheek leegmaken', async () => {
    if (bevestiging.value !== 'BEVESTIG' || resetKnop.disabled) return;
    resetKnop.disabled = true;
    try {
      stopPreview();
      const resultaat = await vraagAanPython('POST','/api/bibliotheek/leegmaken', {bevestiging: 'BEVESTIG'});
      resetDialoog.close();
      toestand.beheerGeselecteerd.clear();
      toestand.actieveGroep = 'alle';
      toestand.live = null;
      toestand.verwachtGeluid = null;
      await laadBibliotheekOpnieuw();
      element('bibliotheek-reset-resultaat').textContent =
        `Bibliotheek leeg. ${resultaat.geluiden_verwijderd} geluiden en ${resultaat.mappen_verwijderd} mappen verwijderd. ` +
        `Herstelkopie: ${resultaat.reservekopie}. Audiobestanden blijven bewaard.`;
    } finally { resetKnop.disabled = bevestiging.value !== 'BEVESTIG'; }
  }));
  koppelBibliotheekbeheer();
  element("knop-importeer").addEventListener("click", () => element("bestandkiezer").click());
  element("bestandkiezer").addEventListener("change", (e) => voerGebruikersactieUit("Importeren", () =>
    importeerGekozenBestanden(Array.from(e.target.files || []))));
  element('bibliotheek-sortering').addEventListener('change',()=>maakBibliotheekZichtbaar());
  element('mappen-sortering').addEventListener('change',()=>{
    maakGroepenZichtbaar();
    if(!element('bibliotheek-pagina').hidden)maakGroteBibliotheekZichtbaar();
  });
  element('bibliotheek-zoek-alle').addEventListener('change', () => {
    toestand.bibliotheekZichtbaarAantal = 60;
    maakBibliotheekZichtbaar();
  });
  element('knop-zoek-wissen').addEventListener('click', () => {
    element('zoeken').value = '';
    toestand.bibliotheekZichtbaarAantal = 60;
    maakBibliotheekZichtbaar();
    element('zoeken').focus();
  });
  element("zoeken").addEventListener("input", () => {
    toestand.bibliotheekZichtbaarAantal = 60;
    maakBibliotheekZichtbaar();
  });
  document.querySelectorAll("[data-sluit]").forEach((knop) => knop.addEventListener("click", () => element(knop.dataset.sluit).close()));
  element("knop-leegmaken").addEventListener("click", () => voerGebruikersactieUit("Favoriet leegmaken", async () => {
    if (toestand.gekozenPlek === null) return;
    await vraagAanPython("DELETE", `/api/favorieten/${toestand.gekozenPlek}`);
    element("dialoog-toewijzen").close(); await laadBibliotheekOpnieuw();
  }));
  element('bewerken-volume').addEventListener('input', pasEditorBasisvolumeAan);
  element('bewerken-volume').addEventListener('change', () =>
    voerGebruikersactieUit('Basisvolume aanpassen', herberekenEditorVoorbeeldvolume));
  element("formulier-bewerken").addEventListener("submit", (e) => {
    e.preventDefault(); voerGebruikersactieUit("Geluid opslaan", async () => {
      await vraagAanPython("POST", `/api/geluiden/${toestand.gekozenGeluid}/instellingen`, {
        naam: element("bewerken-naam").value,
        beginpositie: Number(element("bewerken-start").value),
        maximale_duur: Number(element("bewerken-duur").value),
        beeldvoorkeur: element("bewerken-beeld").value,
        volume: Number(element("bewerken-volume").value) / 100,
        beschrijving: element("bewerken-beschrijving").value,
        gesproken_tekst: element("bewerken-gesproken-tekst").value,
        zoekwoorden: element("bewerken-zoekwoorden").value
      });
      // Een zoekfilter mag geen niet-zichtbare, eerder geselecteerde mappen wissen.
      const nieuweGroepen = [...toestand.editorGroepenKeuze];
      await vraagAanPython("POST", `/api/geluiden/${toestand.gekozenGeluid}/groepen`, {
        groep_ids: nieuweGroepen
      });
      element("dialoog-bewerken").close(); await laadBibliotheekOpnieuw();
      toonMelding("Geluid aangepast.");
    });
  });
  element("knop-afbeelding").addEventListener("click", () => element("afbeeldingkiezer").click());
  element("afbeeldingkiezer").addEventListener("change", () => voerGebruikersactieUit("Afbeelding koppelen", async () => {
    const afbeelding = element("afbeeldingkiezer").files?.[0];
    if (!afbeelding) return;
    if (afbeelding.size > 8 * 1024 * 1024) throw new Error("Afbeelding is groter dan 8 MiB.");
    await vraagAanPython("POST", `/api/geluiden/${toestand.gekozenGeluid}/afbeelding`, undefined, afbeelding);
    element("afbeeldingkiezer").value = "";
    await laadBibliotheekOpnieuw(); toonMelding("Afbeelding of GIF gekoppeld.");
  }));
  element("knop-verwijder-geluid").addEventListener("click", () => voerGebruikersactieUit("Geluid verwijderen", async () => {
    const geluid = vindGeluid(toestand.gekozenGeluid);
    if (!window.confirm(`'${geluid?.naam || "Geluid"}' uit je bibliotheek halen? Het bronbestand wordt niet gewist.`)) return;
    await vraagAanPython("DELETE", `/api/geluiden/${toestand.gekozenGeluid}`);
    element("dialoog-bewerken").close(); await laadBibliotheekOpnieuw();
    toonMelding("Uit de bibliotheek verwijderd. Het bestand blijft bewaard.");
  }));
}

// RC2: de indeling is een eigen instelling, los van het bestaande thema.
const dashboardStandaard = Object.freeze({indeling: 'klassiek', tekstgrootte: 'normaal', hoeken: 'afgerond'});
const dashboardNamen = {klassiek: 'Klassiek', bibliotheek: 'Bibliotheek centraal', favorieten: 'Favorieten eerst'};
let opgeslagenDashboardvoorkeuren = null;
let dashboardIndelingBezig = false;
let dashboardAfspeelFilter = 'alle';
let actieveFavorietActieknop = null;

function pasDashboardOpmaakToe(voorkeur) {
  const correct = {...dashboardStandaard, ...(voorkeur || {})};
  document.body.dataset.tekstgrootte = correct.tekstgrootte;
  document.body.dataset.kaarthoeken = correct.hoeken;
  document.documentElement.dataset.dashboardindeling = dashboardNamen[correct.indeling] ? correct.indeling : 'klassiek';
  if (element('dashboard-indeling-status')) tekenDashboardindeling(correct);
  const snel = element('dashboard-snelfilters');
  if (snel) snel.hidden = correct.indeling === 'klassiek';
  if (snel && !snel.hidden) tekenDashboardSnelFilters();
}

function tekenDashboardindeling(voorkeur) {
  for (const knop of document.querySelectorAll('[data-indeling]')) {
    const gekozen = knop.dataset.indeling === voorkeur.indeling;
    knop.setAttribute('aria-pressed', String(gekozen));
  }
}

async function laadDashboardvoorkeuren() {
  const voorkeur = await vraagAanPython('GET', '/api/instellingen/dashboard');
  if (!dashboardNamen[voorkeur.indeling]) throw new Error('Onbekende opgeslagen dashboardindeling.');
  opgeslagenDashboardvoorkeuren = voorkeur;
  pasDashboardOpmaakToe(voorkeur);
  const status = element('dashboard-indeling-status');
  status.textContent = `${dashboardNamen[voorkeur.indeling]} is actief en opgeslagen.`;
  status.dataset.fout = 'false';
}

async function bewaarDashboardindeling(indeling) {
  if (dashboardIndelingBezig || !dashboardNamen[indeling]) return;
  dashboardIndelingBezig = true;
  const knoppen = [...document.querySelectorAll('[data-indeling]')];
  knoppen.forEach(knop => {knop.disabled = true; knop.setAttribute('aria-busy', 'true');});
  const status = element('dashboard-indeling-status');
  status.textContent = 'Dashboardindeling opslaan…';
  status.dataset.fout = 'false';
  try {
    const opgeslagen = await vraagAanPython('POST', '/api/instellingen/dashboard', {indeling});
    if (opgeslagen.indeling !== indeling) throw new Error('De app heeft deze indeling niet bevestigd.');
    opgeslagenDashboardvoorkeuren = opgeslagen;
    pasDashboardOpmaakToe(opgeslagen);
    status.textContent = `${dashboardNamen[indeling]} is actief en opgeslagen.`;
    toonMelding(status.textContent);
  } catch (fout) {
    status.textContent = 'Opslaan is niet gelukt. De vorige indeling blijft actief.';
    status.dataset.fout = 'true';
    pasDashboardOpmaakToe(opgeslagenDashboardvoorkeuren || dashboardStandaard);
    throw fout;
  } finally {
    dashboardIndelingBezig = false;
    knoppen.forEach(knop => {knop.disabled = false; knop.removeAttribute('aria-busy');});
  }
}

function koppelDashboardindelingen() {
  for (const knop of document.querySelectorAll('.dashboard-indeling-keuze')) {
    knop.addEventListener('click', () => voerGebruikersactieUit('Dashboardindeling', () =>
      bewaarDashboardindeling(knop.dataset.indeling)));
  }
  element('knop-dashboard-audio-meer')?.addEventListener('click', () => {
    const paneel = document.querySelector('#dashboard .hoofdpaneel');
    const knop = element('knop-dashboard-audio-meer');
    const open = paneel.dataset.audioExtra !== 'open';
    paneel.dataset.audioExtra = open ? 'open' : 'dicht';
    knop.setAttribute('aria-expanded', String(open));
    knop.textContent = open ? 'Minder audioinstellingen' : 'Meer audioinstellingen';
  });
  element('dashboard-indeling-terug')?.addEventListener('click', () => {
    // Hashnavigatie opent het bestaande dashboard en laat de microfoon met rust.
    if (window.location.hash === '#dashboard') toonGekozenPagina();
  });
}

function tekenDashboardSnelFilters() {
  const container = element('dashboard-snelfilters');
  if (!container || container.hidden) return;
  container.replaceChildren();
  const voegToe = (naam, soort, id = null) => {
    const actief = soort === 'recent' ? dashboardAfspeelFilter === 'recent'
      : dashboardAfspeelFilter === 'alle' && toestand.actieveGroep === id;
    const knop = maakElement('button', 'dashboard-filterknop', naam);
    knop.type = 'button'; knop.setAttribute('aria-pressed', String(actief));
    knop.addEventListener('click', () => {
      dashboardAfspeelFilter = soort === 'recent' ? 'recent' : 'alle';
      toestand.actieveGroep = soort === 'recent' ? 'alle' : id;
      if (id && id !== 'alle') registreerGroepsgebruik(id);
      maakGroepenZichtbaar(); maakBibliotheekZichtbaar();
    });
    container.appendChild(knop);
  };
  voegToe('Alle', 'map', 'alle');
  voegToe('Recent gebruikt', 'recent');
  for (const naam of ['Memes','Windows','Minecraft','Music','Discord']) {
    const groep = toestand.groepen.find(g => g.naam.toLocaleLowerCase('nl-NL') === naam.toLocaleLowerCase('nl-NL'));
    if (groep) voegToe(naam, 'map', groep.id);
  }
}

function sluitFavorietActiemenu() {
  const menu = element('favoriet-actiemenu');
  if (!menu) return;
  menu.hidden = true; menu.replaceChildren();
  if (actieveFavorietActieknop) actieveFavorietActieknop.setAttribute('aria-expanded', 'false');
  actieveFavorietActieknop = null;
}
function toonFavorietActiemenu(plek, geluid, knop) {
  if (actieveFavorietActieknop === knop) {sluitFavorietActiemenu();return;}
  sluitFavorietActiemenu(); sluitGeluidActiemenu();
  actieveFavorietActieknop = knop; knop.setAttribute('aria-expanded','true');
  const menu = element('favoriet-actiemenu');
  function actie(naam, callback, soort = '') {
    const item = maakElement('button','geluid-menu-actie ' + soort,naam);
    item.type='button'; item.setAttribute('role','menuitem');
    item.addEventListener('click',(evt)=>{evt.stopPropagation();sluitFavorietActiemenu();callback();});
    menu.appendChild(item);
  }
  actie('Geluid bewerken',()=>openBewerkvenster(geluid.id),'menu-bewerken');
  actie('Vervangen',()=>openFavorietKiezer(plek));
  actie('In bibliotheek bekijken',()=>{
    window.location.hash='#bibliotheek';
    element('beheer-zoeken').value=geluid.naam;
    maakGroteBibliotheekZichtbaar();
  });
  actie('Plek leegmaken',()=>voerGebruikersactieUit('Favoriet verwijderen',async()=>{
    await vraagAanPython('DELETE',`/api/favorieten/${plek}`);
    await laadBibliotheekOpnieuw();
  }));
  plaatsGeluidActiemenuBijKnop(menu,knop);
}

const dashboardAccentPresets = [
  ['Turquoise','#78D6C5'], ['Blauw','#8AAEFF'], ['Paars','#C5A0F0'],
  ['Oranje','#F0AA79'], ['Roze','#EAA7C3'], ['Groen','#8CDDB2'], ['IJsblauw','#A7E1F1']
];
function tekenAccentpresets() {
  const container = element('thema-accentpresets');
  if (!container || !themaConcept) return;
  container.replaceChildren();
  const huidige = (themaConcept.accentkleur || basispaletten[themaConcept.thema].accent).toUpperCase();
  for (const [naam, hex] of dashboardAccentPresets) {
    const knop = maakElement('button','thema-accentpreset');
    knop.type='button'; knop.title=naam; knop.setAttribute('aria-label',`Accentkleur ${naam}`);
    knop.setAttribute('aria-pressed',String(huidige === hex.toUpperCase()));
    knop.style.setProperty('--presetkleur',hex);
    knop.addEventListener('click',()=>{
      themaConcept.accentkleur=hex.toUpperCase();
      element('thema-accent').value=hex;
      bewerkThemaConceptMetVelden();
      tekenAccentpresets();
    });
    container.appendChild(knop);
  }
}

async function beginDashboard() {
  koppelPaginanavigatie();
  koppelAppAfsluiten();
  koppelSneltoetsenAanDashboard();
  koppelAlleKnoppen();
  koppelAlgemeenEffectvolume();
  koppelWeergaveKnoppen();
  koppelDashboardindelingen();
  koppelRecenteKnoppen();
  await Promise.allSettled([
    laadAppAfsluitmogelijkheid(),
    voerGebruikersactieUit("Audioapparaten ophalen", laadApparaten),
    voerGebruikersactieUit("Bibliotheek openen", laadBibliotheekOpnieuw),
    voerGebruikersactieUit("Weergave laden", laadPersoonlijkeWeergave),
    voerGebruikersactieUit("Dashboardindeling laden", laadDashboardvoorkeuren),
    voerGebruikersactieUit("Geluidsnormalisatie laden", laadGeluidsnormalisatie),
    voerGebruikersactieUit("Totaalvolume laden", laadAlgemeenEffectvolume),
    voerGebruikersactieUit("Piekbeveiliging laden", laadPiekbeveiliging),
    voerGebruikersactieUit("Stemprofiel laden", laadStemprofiel),
    voerGebruikersactieUit("Recent gebruikt laden", () => laadRecentGebruikt())
  ]);
  // Na de gewone apparaatlijst; vermijd gelijktijdige PortAudio-query's.
  await controleerVBCable();
  await vernieuwStatus();
  // Als er maar één microfoon is, start de app deze automatisch. Bij een
  // bestaande verbinding of meerdere apparaten gebeurt er niets.
  await voerGebruikersactieUit('Automatisch verbinden', verbindEnigeMicrofoonBijStart);
  startDeDirecteNiveaustroom();
  // Metingen lopen via één 30 Hz EventSource; volledige status hoeft slechts iedere 1,5 s.
  if (appAfsluitingAangevraagd) return;
  statusTimer = setInterval(() => { if (!document.hidden) vernieuwStatus(); }, 1500);
  // Eén rustige geschiedenis-update per 20 seconden, nooit per audioframe.
  recentTimer = setInterval(() => { if (!document.hidden) laadRecentGebruikt().catch(() => {}); }, 20000);
}

/*
  5.8: vijf recente groepen, lokale afspeelgeschiedenis en persoonlijke thema's.
  Dit is bewust alleen presentatielogica. De database en audiomixer blijven
  bij Python; een browserinstelling kan nooit rechtstreeks naar VB-CABLE schrijven.
*/
const basispaletten = {
  obsidian: { naam: "Obsidian", achtergrond: "#0A0D12", paneel: "#121820", paneel_hoog: "#1A242E", rand: "#293440", accent: "#78D6C5" },
  midnight: { naam: "Midnight", achtergrond: "#0B1221", paneel: "#151E31", paneel_hoog: "#1B2A42", rand: "#33435B", accent: "#8AAEFF" },
  amethyst: { naam: "Amethyst", achtergrond: "#130F1C", paneel: "#20182C", paneel_hoog: "#2C213B", rand: "#413650", accent: "#C5A0F0" },
  ember: { naam: "Ember", achtergrond: "#18110F", paneel: "#251B19", paneel_hoog: "#352522", rand: "#503935", accent: "#F0AA79" },
  monochrome: { naam: "Monochrome", achtergrond: "#101214", paneel: "#1C2024", paneel_hoog: "#282D32", rand: "#414850", accent: "#E4EBEE" }
};
let opgeslagenWeergave = null;
let eigenThemaprofielen = [];
let themaConcept = null;
let opmaakConcept = null;
let recenteGegevens = { groepen: [], geluiden: [] };
let recentTab = "groepen";

function luminantieVanKleur(hexkleur) {
  const rgb = [1, 3, 5].map((index) => {
    const component = parseInt(hexkleur.slice(index, index + 2), 16) / 255;
    return component <= .04045 ? component / 12.92 : ((component + .055) / 1.055) ** 2.4;
  });
  return .2126 * rgb[0] + .7152 * rgb[1] + .0722 * rgb[2];
}
function geefPassendeKnoptekst(accent) {
  // WCAG-contrast voor knoptekst: wit of donker kiezen op basis van de
  // echte contrastverhouding, niet op basis van een oppervlakkige helderheid.
  const licht = luminantieVanKleur(accent);
  return (1.05 / (licht + .05)) > ((licht + .05) / .05) ? "#FFFFFF" : "#10161D";
}
function pasSchermthemaToe(voorkeur) {
  if (!voorkeur || !basispaletten[voorkeur.thema]) return;
  const kleuren = basispaletten[voorkeur.thema];
  const accent = /^#[0-9a-fA-F]{6}$/.test(voorkeur.accentkleur || "")
    ? voorkeur.accentkleur : kleuren.accent;
  const root = document.documentElement;
  const nieuweWaarden = {
    "--achtergrond": kleuren.achtergrond, "--paneel": kleuren.paneel,
    "--paneel-hoog": kleuren.paneel_hoog, "--paneel-hover": kleuren.paneel_hoog,
    "--rand": kleuren.rand, "--rand-zacht": kleuren.rand,
    "--accent": accent, "--accent-tekst": geefPassendeKnoptekst(accent),
    "--gradient-niveau": ({ uit: "0%", subtiel: "8%", duidelijk: "19%" })[voorkeur.gradient] || "8%",
    "--gradient-x": voorkeur.gradientrichting === "linksboven" ? "9%" : voorkeur.gradientrichting === "onder" ? "55%" : "92%",
    "--gradient-y": voorkeur.gradientrichting === "onder" ? "98%" : "3%"
  };
  Object.entries(nieuweWaarden).forEach(([sleutel, waarde]) => root.style.setProperty(sleutel, waarde));
  root.dataset.thema = voorkeur.thema;
  document.body.classList.toggle("compacte-weergave", Boolean(voorkeur.compact));
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", kleuren.achtergrond);
}
function bewerkThemaConceptMetVelden() {
  if (!themaConcept) return;
  themaConcept.gradient = element("thema-gradient").value;
  themaConcept.gradientrichting = element("thema-richting").value;
  themaConcept.compact = element("thema-compact").checked;
  if (themaConcept.accentkleur !== null) themaConcept.accentkleur = element("thema-accent").value.toUpperCase();
  pasSchermthemaToe(themaConcept);
  tekenAccentpresets();
  element("thema-fout").hidden = true;
}
function toonThemaKeuzes() {
  const container = element("thema-keuzes");
  container.replaceChildren();
  for (const [sleutel, palet] of Object.entries(basispaletten)) {
    const knop = maakElement("button", "thema-keuze" + (themaConcept?.thema === sleutel ? " gekozen" : ""));
    knop.type = "button";
    knop.setAttribute("aria-pressed", String(themaConcept?.thema === sleutel));
    knop.appendChild(maakElement("span", "thema-stalen"));
    knop.firstChild.style.background = `linear-gradient(135deg, ${palet.achtergrond} 5%, ${palet.paneel} 58%, ${palet.accent} 58%)`;
    knop.appendChild(maakElement("span", "", palet.naam));
    knop.addEventListener("click", () => {
      themaConcept.thema = sleutel;
      // Een ander basisthema kiezen gebruikt de bijbehorende standaardaccentkleur.
      // Daarna kan de gebruiker opnieuw een eigen kleur kiezen.
      themaConcept.accentkleur = null;
      element("thema-accent").value = palet.accent;
      toonThemaKeuzes();
      bewerkThemaConceptMetVelden();
    });
    container.appendChild(knop);
  }
}
function vulThemaVelden() {
  element("thema-accent").value = themaConcept.accentkleur || basispaletten[themaConcept.thema].accent;
  element("thema-gradient").value = themaConcept.gradient;
  element("thema-richting").value = themaConcept.gradientrichting;
  element("thema-compact").checked = themaConcept.compact;
  element("thema-lettergrootte").value = opmaakConcept?.tekstgrootte || "normaal";
  element("thema-hoeken").value = opmaakConcept?.hoeken || "afgerond";
  tekenAccentpresets();
  element("thema-fout").hidden = true;
  toonThemaKeuzes();
}
function openThemaInstellingen() {
  themaConcept = { ...opgeslagenWeergave };
  opmaakConcept = { ...(opgeslagenDashboardvoorkeuren || dashboardStandaard) };
  vulThemaVelden();
  element("dialoog-weergave").showModal();
}
async function laadPersoonlijkeWeergave() {
  opgeslagenWeergave = await vraagAanPython("GET", "/api/instellingen/weergave");
  pasSchermthemaToe(opgeslagenWeergave);
}
async function laadEigenThemaprofielen() {
  const gegevens = await vraagAanPython("GET", "/api/instellingen/thema-profielen");
  eigenThemaprofielen = gegevens.profielen || [];
  const lijst = element("eigen-thema-lijst");
  lijst.replaceChildren();
  element("thema-profiel-aantal").textContent = String(eigenThemaprofielen.length);
  if (!eigenThemaprofielen.length) {
    lijst.appendChild(maakElement("span", "recent-leeg", "Nog geen eigen profielen bewaard."));
  }
  for (const profiel of eigenThemaprofielen) {
    const rij = maakElement("span", "eigen-thema-item");
    const kies = maakElement("button", "", profiel.naam);
    kies.type = "button";
    kies.title = `Laad het eigen thema ${profiel.naam}`;
    kies.addEventListener("click", () => {
      themaConcept = { ...profiel.instellingen };
      vulThemaVelden();
      pasSchermthemaToe(themaConcept);
    });
    const wis = maakElement("button", "thema-profiel-verwijder", "×");
    wis.type = "button";
    wis.title = `Verwijder opgeslagen thema ${profiel.naam}`;
    wis.addEventListener("click", () => voerGebruikersactieUit("Eigen thema verwijderen", async () => {
      if (!window.confirm(`Eigen thema '${profiel.naam}' verwijderen?`)) return;
      await vraagAanPython("DELETE", `/api/instellingen/thema-profielen/${profiel.id}`);
      await laadEigenThemaprofielen();
    }));
    rij.append(kies, wis);
    lijst.appendChild(rij);
  }
}

function koppelWeergaveKnoppen() {
  element("knop-weergave").addEventListener("click", () => voerGebruikersactieUit("Weergave openen", async () => {
    if (!opgeslagenWeergave) await laadPersoonlijkeWeergave();
    if (!opgeslagenDashboardvoorkeuren) await laadDashboardvoorkeuren();
    await laadEigenThemaprofielen();
    openThemaInstellingen();
  }));
  element("knop-eigen-thema-opslaan").addEventListener("click", () => voerGebruikersactieUit("Eigen thema bewaren", async () => {
    const naam = element("eigen-thema-naam").value.trim();
    if (!naam) throw new Error("Geef eerst een naam aan je eigen thema.");
    await vraagAanPython("POST", "/api/instellingen/thema-profielen", {
      naam, instellingen: {
        thema: themaConcept.thema, accentkleur: themaConcept.accentkleur,
        gradient: themaConcept.gradient, gradientrichting: themaConcept.gradientrichting,
        compact: themaConcept.compact
      }
    });
    await laadEigenThemaprofielen();
    toonMelding(`Thema '${naam}' bewaard.`);
  }));
  element("thema-accent").addEventListener("input", () => {
    themaConcept.accentkleur = element("thema-accent").value.toUpperCase();
    bewerkThemaConceptMetVelden();
  });
  element("knop-accent-standaard").addEventListener("click", () => {
    themaConcept.accentkleur = null;
    element("thema-accent").value = basispaletten[themaConcept.thema].accent;
    bewerkThemaConceptMetVelden();
  });
  for (const naam of ["thema-gradient", "thema-richting", "thema-compact"]) {
    element(naam).addEventListener("change", bewerkThemaConceptMetVelden);
  }
  for (const naam of ["thema-lettergrootte", "thema-hoeken"]) {
    element(naam).addEventListener("change", () => {
      opmaakConcept = {...opmaakConcept,
        tekstgrootte: element("thema-lettergrootte").value,
        hoeken: element("thema-hoeken").value};
      pasDashboardOpmaakToe(opmaakConcept);
    });
  }
  element("knop-thema-herstellen").addEventListener("click", () => {
    themaConcept = { thema: "obsidian", accentkleur: null, gradient: "subtiel", gradientrichting: "rechtsboven", compact: false };
    // De extra lettergrootte en kaartvorm horen ook bij Weergave.
    // De gekozen dashboardindeling hoort er bewust niet bij.
    opmaakConcept = {...(opgeslagenDashboardvoorkeuren || dashboardStandaard),
      tekstgrootte: "normaal", hoeken: "afgerond"};
    vulThemaVelden();
    pasSchermthemaToe(themaConcept);
    pasDashboardOpmaakToe(opmaakConcept);
  });
  element("knop-thema-opslaan").addEventListener("click", () => voerGebruikersactieUit("Weergave opslaan", async () => {
    try {
      const gegevens = {
        thema: themaConcept.thema, accentkleur: themaConcept.accentkleur,
        gradient: themaConcept.gradient, gradientrichting: themaConcept.gradientrichting,
        compact: themaConcept.compact
      };
      // Schrijf de dashboardopmaak eerst; de bestaande thema-opslag blijft ongewijzigd.
      // Beide antwoorden worden afzonderlijk gecontroleerd, zonder succes te claimen bij fout.
      const nieuweOpmaak = await vraagAanPython("POST", "/api/instellingen/dashboard", {
        tekstgrootte: opmaakConcept.tekstgrootte, hoeken: opmaakConcept.hoeken
      });
      opgeslagenDashboardvoorkeuren = nieuweOpmaak;
      opgeslagenWeergave = await vraagAanPython("POST", "/api/instellingen/weergave", gegevens);
      pasDashboardOpmaakToe(opgeslagenDashboardvoorkeuren);
      pasSchermthemaToe(opgeslagenWeergave);
      element("dialoog-weergave").close();
      toonMelding("Weergave opgeslagen.");
    } catch (fout) {
      element("thema-fout").textContent = fout.message;
      element("thema-fout").hidden = false;
      throw fout;
    }
  }));
  element("dialoog-weergave").addEventListener("close", () => {
    // Annuleren of X zet het vorige thema terug. Er blijven nooit half
    // toegepaste instellingen achter na het sluiten van een dialoog.
    pasSchermthemaToe(opgeslagenWeergave);
    pasDashboardOpmaakToe(opgeslagenDashboardvoorkeuren);
  });
}

function maakRecentGroepenZichtbaar() {
  const container = element("recent-groepen");
  container.replaceChildren();
  if (!recenteGegevens.groepen.length) {
    container.appendChild(maakElement("p", "recent-leeg", "Hier verschijnen je vijf laatst gebruikte groepen."));
    return;
  }
  for (const groep of recenteGegevens.groepen.slice(0, 5)) {
    const knop = maakElement("button", "recent-groepkaart");
    knop.type = "button";
    const markering = maakElement("span", "recent-groepmarkering");
    markering.setAttribute("aria-hidden", "true");
    knop.append(markering, maakElement("strong", "", groep.naam),
      maakElement("small", "", `${groep.aantal_geluiden} geluid${groep.aantal_geluiden === 1 ? "" : "en"}`));
    knop.addEventListener("click", () => {
      toestand.actieveGroep = groep.id;
      maakGroepenZichtbaar();
      maakBibliotheekZichtbaar();
      // Op een smal scherm is de bibliotheek onder het hoofdscherm geplaatst.
      document.querySelector(".zijbalk")?.scrollIntoView({ behavior: "smooth", block: "start" });
      registreerGroepsgebruik(groep.id);
    });
    container.appendChild(knop);
  }
}
function formatteerRecenteTijd(waarde) {
  const datum = new Date(waarde);
  if (Number.isNaN(datum.getTime())) return "Onbekend";
  const nu = new Date();
  const vandaag = new Date(nu.getFullYear(), nu.getMonth(), nu.getDate());
  const dagVanGebeurtenis = new Date(datum.getFullYear(), datum.getMonth(), datum.getDate());
  const verschil = Math.round((vandaag - dagVanGebeurtenis) / 86400000);
  const klok = datum.toLocaleTimeString("nl-NL", { hour: "2-digit", minute: "2-digit" });
  if (verschil === 0) return `Vandaag ${klok}`;
  if (verschil === 1) return `Gisteren ${klok}`;
  return datum.toLocaleDateString("nl-NL", { day: "numeric", month: "short" }) + ` om ${klok}`;
}
function maakRecenteGeluidenZichtbaar(geluiden, containerId) {
  const container = element(containerId);
  container.replaceChildren();
  if (!geluiden.length) {
    container.appendChild(maakElement("p", "recent-leeg", "Nog niets afgespeeld. Je geschiedenis begint bij de eerste Preview of uitzending."));
    return;
  }
  for (const geluid of geluiden) {
    const rij = maakElement("div", "recent-geluidrij");
    const icoon = maakElement("span", "recent-modusicoon", geluid.wijze === "gesprek" ? "↗" : "◉");
    icoon.setAttribute("aria-hidden", "true");
    const omschrijving = maakElement("div", "recent-geluidtekst");
    omschrijving.append(maakElement("strong", "", geluid.naam), maakElement("small", "", formatteerRecenteTijd(geluid.tijdstip_utc)));
    const modus = maakElement("span", "recent-modus " + (geluid.wijze === "gesprek" ? "naar-gesprek" : "lokaal"),
      geluid.wijze === "gesprek" ? "Uitgezonden" : "Preview");
    rij.append(icoon, omschrijving, modus);
    if (geluid.bestaat_nog && vindGeluid(geluid.id)) {
      const preview = maakElement("button", "recent-play", "Preview");
      preview.type = "button";
      preview.title = `Luister ${geluid.naam} lokaal`;
      preview.addEventListener("click", () => beginPreview(geluid.id));
      rij.appendChild(preview);
    }
    container.appendChild(rij);
  }
}
function tekenRecenteOverzicht() {
  maakRecentGroepenZichtbaar();
  maakRecenteGeluidenZichtbaar(recenteGegevens.geluiden.slice(0, 5), "recent-geluiden");
  if (element("dialoog-geschiedenis").open) {
    maakRecenteGeluidenZichtbaar(recenteGegevens.geluiden, "geschiedenis-volledig");
  }
}
async function laadRecentGebruikt(maximaal = 12) {
  recenteGegevens = await vraagAanPython("GET", `/api/recente-gebruik?maximaal=${maximaal}`);
  tekenRecenteOverzicht();
  if (dashboardAfspeelFilter === "recent") maakBibliotheekZichtbaar({ behoudPositie: true });
}
function registreerGroepsgebruik(groepId) {
  vraagAanPython("POST", "/api/groepen/recent", { groep_id: groepId })
    .then(() => laadRecentGebruikt().catch(() => {}))
    .catch((fout) => registreerBrowserfout(`Recente groep niet opgeslagen: ${fout.message}`, fout.stack || ""));
}
function activeerRecenteTab(naam) {
  recentTab = naam;
  for (const soort of ["groepen", "geluiden"]) {
    const actief = soort === naam;
    element(`recent-tab-${soort}`).classList.toggle("gekozen", actief);
    element(`recent-tab-${soort}`).setAttribute("aria-selected", String(actief));
    element(`recent-panel-${soort}`).hidden = !actief;
  }
}
function koppelRecenteKnoppen() {
  for (const soort of ["groepen", "geluiden"]) {
    element(`recent-tab-${soort}`).addEventListener("click", () => {
      activeerRecenteTab(soort);
      laadRecentGebruikt().catch(() => {});
    });
  }
  element("knop-geschiedenis").addEventListener("click", () => voerGebruikersactieUit("Geschiedenis openen", async () => {
    await laadRecentGebruikt(100);
    element("dialoog-geschiedenis").showModal();
    tekenRecenteOverzicht();
  }));
  element("knop-geschiedenis-wissen").addEventListener("click", () => voerGebruikersactieUit("Geschiedenis wissen", async () => {
    if (!window.confirm("Afspeelgeschiedenis en recente groepen wissen? Je geluiden blijven bewaard.")) return;
    await vraagAanPython("POST", "/api/recente-gebruik/wissen", {});
    await laadRecentGebruikt(100);
    toonMelding("Geschiedenis gewist.");
  }));
}


/* De toetsinvoer onthoudt uitsluitend bewust ingestelde combinaties.
   We luisteren NOOIT naar toetsen buiten het gefocuste configuratieveld. */
let aangepasteSneltoetsen = { ingeschakeld: false, combinaties: {} };
function vulSneltoetsenFormulier(gegevens) {
  aangepasteSneltoetsen = {ingeschakeld: !!gegevens.ingeschakeld, combinaties: {...gegevens.combinaties}};
  element("sneltoetsen-ingeschakeld").checked = aangepasteSneltoetsen.ingeschakeld;
  const lijst = element("sneltoetsen-lijst");
  lijst.replaceChildren();
  for (let nummer = 1; nummer <= 16; nummer++) {
    const actie = nummer === 16 ? "stop" : `favoriet_${nummer}`;
    const rij = maakElement("div", "sneltoetsen-rij");
    const label = maakElement("label", "", actie === "stop" ? "Alle geluiden stoppen" : `Favoriet ${nummer}`);
    const invoerveld = document.createElement("input");
    invoerveld.type = "text";
    invoerveld.readOnly = true;
    invoerveld.id = `sneltoets-${actie}`;
    label.htmlFor = invoerveld.id;
    invoerveld.value = aangepasteSneltoetsen.combinaties[actie] || "";
    invoerveld.placeholder = "Klik en druk je sneltoets";
    invoerveld.addEventListener("keydown", (event) => {
      if (event.key === "Tab" || event.key === "Escape") return;
      event.preventDefault();
      if (event.key === "Backspace" || event.key === "Delete") {
        delete aangepasteSneltoetsen.combinaties[actie];
        invoerveld.value = "";
        return;
      }
      if (!(event.ctrlKey && (event.altKey || event.shiftKey))) return;
      // event.key kan op een Nederlandse indeling met AltGr een symbool
      // geven in plaats van het cijfer. event.code bevat de fysieke toets.
      const toets = /^Digit[0-9]$/.test(event.code)
        ? event.code.slice(-1)
        : (/^F(?:[1-9]|1[0-9]|2[0-4])$/.test(event.code) ? event.code : "");
      if (!toets) return;
      const combinatie = `CTRL+${event.altKey ? "ALT+" : ""}${event.shiftKey ? "SHIFT+" : ""}${toets}`;
      for (const [andereActie, andereCombinatie] of Object.entries(aangepasteSneltoetsen.combinaties)) {
        if (andereActie !== actie && andereCombinatie === combinatie) {
          toonMelding("Deze combinatie is al aan een andere actie gekoppeld.", true);
          return;
        }
      }
      aangepasteSneltoetsen.combinaties[actie] = combinatie;
      invoerveld.value = combinatie;
    });
    rij.append(label, invoerveld);
    lijst.appendChild(rij);
  }
}
function koppelSneltoetsenAanDashboard() {
  element("knop-sneltoetsen").addEventListener("click", () => voerGebruikersactieUit("Sneltoetsen openen", async () => {
    const gegevens = await vraagAanPython("GET", "/api/sneltoetsen");
    if (!gegevens.ondersteund) {
      toonMelding("Start de desktopapp om sneltoetsen buiten de browser te gebruiken.", true);
      return;
    }
    vulSneltoetsenFormulier(gegevens);
    element("sneltoetsen-fout").hidden = true;
    element("dialoog-sneltoetsen").showModal();
  }));
  element("knop-sneltoetsen-standaard").addEventListener("click", () => {
    const combinaties = {};
    for (let nummer = 1; nummer <= 9; nummer++) combinaties[`favoriet_${nummer}`] = `CTRL+ALT+${nummer}`;
    combinaties.stop = "CTRL+ALT+0";
    vulSneltoetsenFormulier({ingeschakeld: false, combinaties});
  });
  element("knop-sneltoetsen-opslaan").addEventListener("click", () => voerGebruikersactieUit("Sneltoetsen bewaren", async () => {
    aangepasteSneltoetsen.ingeschakeld = element("sneltoetsen-ingeschakeld").checked;
    const antwoord = await vraagAanPython("POST", "/api/sneltoetsen", aangepasteSneltoetsen);
    vulSneltoetsenFormulier(antwoord);
    const conflicten = Object.values(antwoord.mislukte_registraties || {});
    if (conflicten.length) {
      element("sneltoetsen-fout").hidden = false;
      element("sneltoetsen-fout").textContent = "Niet geregistreerd: " + conflicten.join("; ");
      return;
    }
    element("dialoog-sneltoetsen").close();
    toonMelding("Sneltoetsinstellingen bewaard.");
  }));
}

beginDashboard();

function werkNatuurlijkeStemBij(data) {
  const vorigeKeuze = gekozenStemId();
  if (data) toestand.natuurlijkeStem = data;
  const status=toestand.natuurlijkeStem || {aan:false,beschikbaar:false,melding:'Karakterstem wordt gecontroleerd.'};
  const knop=element('knop-natuurlijke-stem');if(!knop)return;
  knop.textContent=stemkeuzeActief()?'Stemvervormer uitzetten':'Gekozen stem aanzetten';
  knop.setAttribute('aria-pressed',String(stemkeuzeActief()));
  knop.disabled=Boolean(toestand.stemkeuzeBezig || toestand.natuurlijkeStemBezig || toestand.stembeheerBezig || status.test_bezig ||
    (natuurlijkeStemGekozen() && !status.beschikbaar && !status.aan));
  const tekst=element('natuurlijke-stem-status');
  tekst.textContent=status.melding || (status.beschikbaar?'Karakterstem uit.':'Het stempakket ontbreekt.');
  const diagnose = element('stemdiagnose-inhoud');
  if (diagnose) diagnose.dataset.fout=String(status.toestand==='fout');
  werkStemcontroleBij(status);
  if (vorigeKeuze !== gekozenStemId()) stopVoorbeeldstem();
  werkStemprofielKaartenBij({parameters:vorigeKeuze !== gekozenStemId()});
  werkStemvoorbeeldKnopBij();
}

function werkStemcontroleBij(status) {
  const test = element('knop-stem-computertest');
  if (!test) return;
  const bezig = status.test_bezig === true;
  const verzoek = toestand.stembeheerBezig || toestand.natuurlijkeStemBezig;
  const verbinding = toestand.status?.toestand;
  const audioActief = (verbinding && verbinding !== 'verbroken') || Boolean(toestand.status?.stemvoorbeeld?.actief ?? toestand.stemvoorbeeldActief) || toestand.stemvoorbeeldBezig;
  test.textContent = bezig ? 'Test stoppen' : 'Computer testen';
  test.disabled = Boolean(verzoek || (!bezig && (status.aan || audioActief || !status.beschikbaar)));
  test.title = audioActief && !bezig ? 'Verbreek eerst de microfoonverbinding en stop de stempreview.' : '';
  const hulp = element('stem-computertest-hulp');
  hulp.textContent = audioActief && !bezig ? 'Verbreek eerst de microfoonverbinding en stop de stempreview om te testen of de buffer te wijzigen.'
    : status.aan && !bezig ? 'Zet de karakterstem uit om te testen of de buffer te wijzigen.' : '';
  hulp.hidden = !hulp.textContent;
  const buffer = element('stem-bufferprofiel');
  buffer.value = status.bufferprofiel || 'gebalanceerd';
  buffer.disabled = Boolean(verzoek || bezig || status.aan || audioActief);
  const result = element('stem-computertest-resultaat');
  const meting = status.computertest;
  result.dataset.oordeel = meting?.oordeel || 'onbekend';
  const ms = getal => typeof getal === 'number' && Number.isFinite(getal) ? `${getal.toLocaleString('nl-NL', {maximumFractionDigits: 1})} ms` : 'Nog geen meting';
  if (bezig || (status.toestand === 'laden' && status.test_voortgang)) {
    result.textContent = `Computer testen: ${Number(status.test_voortgang) || 0} procent. Er wordt niets opgenomen of uitgezonden.`;
  } else if (meting) {
    result.textContent = meting.geslaagd
      ? `Verwerking voldoende snel. Gemiddeld ${ms(meting.meting?.gemiddeld_ms)}, p95 ${ms(meting.meting?.p95_ms)} per 52 ms audio. Dit zegt niets over de stemkwaliteit of totale vertraging.`
      : 'De verwerking is te langzaam. Sluit zware programma’s en test opnieuw, of kies een effectstem.';
  } else {
    result.textContent = 'Nog geen computertest in deze sessie. Bij aanzetten wordt de snelheid ook gecontroleerd.';
  }
  element('knop-stem-testrapport').disabled = verzoek || (!meting && status.toestand !== 'fout');
  element('stem-verwerking-gemiddeld').textContent = ms(status.recente_verwerking?.gemiddeld_ms);
  element('stem-verwerking-p95').textContent = ms(status.recente_verwerking?.p95_ms);
  element('stem-onderbrekingen').textContent = String(status.onderbrekingen || 0);
  const pakketten = {
    gecontroleerd: 'De stembestanden zijn gecontroleerd.',
    bezig: 'Stembestanden controleren.',
    beschadigd: 'Een stembestand ontbreekt of is beschadigd. Bewaar het rapport en installeer de app opnieuw.'
  };
  element('stem-pakketstatus').textContent = pakketten[status.pakketcontrole] || 'Bestanden worden bij testen of aanzetten gecontroleerd.';
}

async function stuurStembeheer(gegevens) {
  if (toestand.stembeheerBezig || toestand.natuurlijkeStemBezig) return;
  toestand.stembeheerBezig = true;
  werkNatuurlijkeStemBij(toestand.natuurlijkeStem);
  try {
    const data = await vraagAanPython('POST', '/api/natuurlijke-stem/beheer', gegevens);
    werkNatuurlijkeStemBij(data);
  } finally {
    toestand.stembeheerBezig = false;
    werkNatuurlijkeStemBij(toestand.natuurlijkeStem);
  }
}

function koppelStemcontrole() {
  const test = element('knop-stem-computertest');
  if (!test || test.dataset.gekoppeld === 'true') return;
  test.dataset.gekoppeld = 'true';
  const openen = element('knop-stemdiagnose');
  const dialoog = element('dialoog-stemdiagnose');
  if (openen && dialoog) {
    openen.addEventListener('click', () => {
      werkStemcontroleBij(toestand.natuurlijkeStem || {});
      if (!dialoog.open) dialoog.showModal();
    });
  }
  test.addEventListener('click', () => voerGebruikersactieUit('Stemcontrole', () => stuurStembeheer({actie: toestand.natuurlijkeStem?.test_bezig ? 'stop_test' : 'test'})));
  element('stem-bufferprofiel').addEventListener('change', event => {
    const keuze = event.target.value;
    voerGebruikersactieUit('Stemcontrole', () => stuurStembeheer({actie: 'buffer', bufferprofiel: keuze}));
  });
  element('knop-stem-testrapport').addEventListener('click', () => voerGebruikersactieUit('Stemcontrole', async () => {
    const rapport = await vraagAanPython('GET', '/api/natuurlijke-stem/rapport');
    const blob = new Blob([JSON.stringify(rapport, null, 2)], {type: 'application/json'});
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url; link.download = 'DrostSoundboard_stemcontrole.json';
    document.body.appendChild(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    toonMelding('Rapport opgeslagen. Het bevat geen microfoonopname of logboek.');
  }));
}
