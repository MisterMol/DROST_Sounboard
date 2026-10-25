"use strict";

/*
  Dit bestand regelt alleen de webinterface. Python doet de echte audiomix.
  Een preview blijft in de browser; afspelen voor het gesprek gaat via Python.
  We tonen video en GIF alleen zolang de bijbehorende audio actief is.
*/
const beveiligingscode = document.querySelector('meta[name="drost-token"]').content;
const element = (id) => document.getElementById(id);
const toestand = {
  geluiden: [], favorieten: Array(15).fill(null), status: null,
  gekozenGeluid: null, gekozenPlek: null, bezetteStatusaanvraag: false,
  bezigMetImport: false, laatsteAudiofout: null,
  preview: null, live: null, verwachtGeluid: null,
  laatstGekozenMonitor: null, groepen: [], actieveGroep: "alle",
  editorVoorbeeld: null, editorGolfvormWachttijd: null, golfvormVolgnummer: 0,
  editorAfspeelpositie: 0, editorIsAanHetSlepen: false,
  editorAfspeelAnimatie: null, editorGolfvormData: null,
  laatstGemetenPieken: [null, null],
  editorVensterBegin: 0, editorVensterDuur: 120,
  editorKniprand: null, editorLangVasthouden: null,
  editorLaatstePointerX: 0,
  beheerGeselecteerd: new Set(), beheerZichtbaarAantal: 60,
  bibliotheekZichtbaarAantal: 60
};

function maakElement(soort, klasse = "", tekst = undefined) {
  const gemaakt = document.createElement(soort);
  if (klasse) gemaakt.className = klasse;
  if (tekst !== undefined) gemaakt.textContent = String(tekst);
  return gemaakt;
}

async function vraagAanPython(methode, pad, gegevens = undefined, bestand = undefined) {
  const koppen = {};
  const opties = { method: methode, headers: koppen, cache: "no-store" };
  if (methode !== "GET") koppen["X-Drost-Token"] = beveiligingscode;
  if (bestand) {
    koppen["X-Bestandsnaam"] = encodeURIComponent(bestand.name);
    koppen["Content-Type"] = "application/octet-stream";
    opties.body = bestand;
  } else if (methode === "POST") {
    koppen["Content-Type"] = "application/json";
    opties.body = JSON.stringify(gegevens ?? {});
  }
  const antwoord = await fetch(pad, opties);
  let inhoud;
  try { inhoud = await antwoord.json(); }
  catch { throw new Error(`Python gaf geen geldige JSON terug (HTTP ${antwoord.status}).`); }
  if (!antwoord.ok) {
    // De server gebruikt één foutformaat. Bewaar codes en referentie zodat
    // een gebruiker dezelfde fout later in software.jsonl kan terugvinden.
    const referentie = inhoud.referentie && antwoord.status >= 500
      ? ` (logreferentie ${inhoud.referentie})` : "";
    const fout = new Error(`${inhoud.fout || `HTTP ${antwoord.status}`}${referentie}`);
    fout.foutcode = inhoud.oorzaakcode || inhoud.foutcode || null;
    fout.logreferentie = inhoud.referentie || null;
    throw fout;
  }
  return inhoud;
}

function toonMelding(tekst, fout = false) {
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

function registreerBrowserfout(melding, stapel = "") {
  // JS heeft geen Python traceback. Schrijf de browserstack naar dezelfde
  // softwarelogging zodat een fout later alsnog terug te vinden is.
  vraagAanPython("POST", "/api/frontendfout", {
    melding: String(melding).slice(0, 1000), stapel: String(stapel).slice(0, 8000)
  }).catch(() => {});
}
// Alleen dubbele, gelijktijdige verzoeken voor dezelfde schakelaar
// negeren. Andere acties, vooral Stop, mogen direct blijven werken.
const actiesZonderDubbeleAanvraag = new Set([
  "Verbinden", "Verbreken", "Soundboard schakelen", "Meeluisteren instellen",
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
  if (element("dialoog-bibliotheek").open) maakGroteBibliotheekZichtbaar();
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
      const aanpassen = maakElement("button", "bewerk-vak", "···");
      aanpassen.type = "button";
      aanpassen.title = `Favoriet ${plek} vervangen of leegmaken`;
      aanpassen.addEventListener("click", (e) => { e.stopPropagation(); openFavorietKiezer(plek); });
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
      ? `${geluid.formaat.toUpperCase()} · ${netteTijd(geluid.fragmentduur)} ` : "Klik om te kiezen"));
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
  document.querySelectorAll(".lijst-previewknop[data-geluid-id]").forEach((knop) => {
    const bezig = wordtGeluidMomenteelAfgespeeld(knop.dataset.geluidId);
    knop.textContent = bezig ? "■ Stop" : "Preview";
    knop.classList.toggle("preview-stop-actief", bezig);
    knop.setAttribute("aria-label", bezig
      ? "Dit geluid stoppen" : "Dit volledige ingestelde fragment lokaal beluisteren");
    knop.setAttribute("aria-pressed", String(bezig));
  });
}

function schakelPreviewOfStopVanGeluid(geluidId) {
  if (toestand.preview?.geluidId === geluidId) {
    stopPreview("stop_vanuit_bibliotheek");
  } else if (toestand.live?.geluidId === geluidId || toestand.verwachtGeluid?.id === geluidId) {
    voerGebruikersactieUit("Geluid stoppen", async () => {
      await vraagAanPython("POST", "/api/stop", {});
      toestand.verwachtGeluid = null;
      // De status bevestigt wanneer de audiocallback daadwerkelijk stopt.
      // We tonen hier meteen de aangevraagde stop, maar stoppen geen microfoon.
      await vernieuwStatus();
    });
  } else {
    beginPreview(geluidId);
  }
}


function maakBibliotheekZichtbaar() {
  sluitGeluidActiemenu();
  const lijst = element("bibliotheek-lijst");
  lijst.replaceChildren();
  const zoeken = element("zoeken").value.trim().toLocaleLowerCase("nl-NL");
  const gevonden = toestand.geluiden.filter((geluid) => {
    const kloptGroep = toestand.actieveGroep === "alle" ||
      (toestand.actieveGroep === "zonder" ? !(geluid.groep_ids || []).length :
        (geluid.groep_ids || []).includes(toestand.actieveGroep));
    return kloptGroep && geefDoorzoekbareTekstVanGeluid(geluid).includes(zoeken);
  });
  if (!gevonden.length) {
    lijst.appendChild(maakElement("p", "lege-lijst", toestand.geluiden.length
      ? "Geen geluiden gevonden." : "Nog geen geluiden. Voeg je eerste MP3, WAV of MP4 toe."));
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
    tekst.appendChild(maakElement("small", "", `${geluid.formaat.toUpperCase()} · ${geluid.fragmentduur === null ? "Duur onbekend" : netteTijd(geluid.fragmentduur)}${geluid.bestand_gevonden ? "" : " · ontbreekt"}`));
    const luisteren = maakPreviewknopVoorGeluid(geluid);
    const meer = maakElement("button", "icoonknop bibliotheek-acties-knop", "···");
    meer.type = "button";
    meer.setAttribute("aria-label", `Meer acties voor ${geluid.naam}`);
    meer.setAttribute("aria-haspopup", "menu");
    meer.setAttribute("aria-expanded", "false");
    meer.addEventListener("click", (gebeurtenis) => {
      gebeurtenis.stopPropagation();
      toonGeluidActiemenu(geluid.id, meer);
    });
    kaart.append(kunst, tekst, luisteren, meer);
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
      maakBibliotheekZichtbaar();
    });
    lijst.appendChild(verder);
  }
  werkPreviewEnStopknoppenBij();
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
  // Een open dialog ligt in de browser-toplaag. Een menu buiten die dialog
  // zou onzichtbaar achter het beheerformulier komen te staan.
  const beheerdialoog = element("dialoog-bibliotheek");
  if (beheerdialoog.open) beheerdialoog.appendChild(menu);
  else document.body.appendChild(menu);
  menu.hidden = false;
  const positie = knop.getBoundingClientRect();
  const breedte = menu.offsetWidth || 220;
  const hoogte = menu.offsetHeight || 260;
  let links = Math.max(10, Math.min(window.innerWidth - breedte - 10, positie.right - breedte));
  let boven = positie.bottom + 8;
  if (boven + hoogte > window.innerHeight - 12) boven = Math.max(8, positie.top - hoogte - 8);
  if (beheerdialoog.open) {
    const oorsprong = beheerdialoog.getBoundingClientRect();
    // De positie is binnen de gescrolde beheer-dialoog. Dit voorkomt dat
    // het menu van de laatste rij buiten beeld of achter het venster valt.
    links = links - oorsprong.left + beheerdialoog.scrollLeft;
    boven = boven - oorsprong.top + beheerdialoog.scrollTop;
  }
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
    if (element("dialoog-bibliotheek").open) openEditorVanuitBeheer(geluidId);
    else openBewerkvenster(geluidId);
  }, "menu-bewerken");
  voegActieToeAanMenu(menu, "Afspelen in gesprek", () => beginGeluidAfspelen(geluidId));
  voegActieToeAanMenu(menu, "Preview", () => schakelPreviewOfStopVanGeluid(geluidId));
  const formaten = Array.isArray(geluid.exportformaten) ? geluid.exportformaten : [];
  if (formaten.length) {
    menu.appendChild(maakElement("div", "geluid-menu-tussenkop", "Download"));
    for (const formaat of ["mp3", "mp4", "afbeelding", "gif"]) {
      if (!formaten.includes(formaat)) continue;
      const label = { mp3: "MP3 · audio", mp4: "MP4 · video + audio",
        afbeelding: "Afbeelding", gif: "GIF · animatie" }[formaat];
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
}

function toonStilMediascherm() {
  const scherm = element("actieve-media");
  scherm.replaceChildren();
  const basis = maakElement("div", "player-placeholder");
  basis.appendChild(maakGolfIcoon());
  basis.appendChild(maakElement("small", "", "GEEN FRAGMENT ACTIEF"));
  scherm.appendChild(basis);
  element("nu-actief-titel").textContent = "Nog niets actief";
  element("huidige-uitleg").textContent = "Klik op een kaart om te spelen, of kies Preview om eerst te luisteren.";
  element("huidige-afspeelstand").textContent = "SPELER";
  element("tijdlijn-vulling").style.width = "0%";
  element("tijdlijn-tijd").textContent = "0:00";
  element("tijdlijn-totaal").textContent = "0:00";
  element("knop-preview-stop").disabled = true;
  stelSpelerActiefIn(false);
}

function werkSpelerTijdBij(verstreken, totaal) {
  const percentage = totaal > 0 ? Math.min(100, Math.max(0, verstreken / totaal * 100)) : 0;
  element("tijdlijn-vulling").style.width = `${percentage}%`;
  element("tijdlijn-tijd").textContent = netteTijd(verstreken);
  element("tijdlijn-totaal").textContent = netteTijd(totaal);
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
  const afspeeltijd = Math.max(0, (lopend.media.currentTime || lopend.start) - lopend.start);
  lopend.media.pause();
  lopend.media.removeAttribute("src");
  lopend.media.load();
  registreerPreviewBijPython(lopend.geluidId, "gestopt", Math.min(afspeeltijd, lopend.duur), reden, lopend.afspeelbeurt);
  werkActieveKaartenBij();
  if (!toestand.live) toonStilMediascherm();
}

function beginPreview(geluidId) {
  voerGebruikersactieUit("Preview starten", async () => {
    const geluid = vindGeluid(geluidId);
    if (!geluid?.mediabron || !geluid.bestand_gevonden) {
      throw new Error("Het bronbestand ontbreekt. Importeer het geluid via de webpagina.");
    }
    stopPreview("vervangen");
    // Preview wordt toegestaan terwijl DrostSoundboard niet met Discord verbonden is.
    const start = Number(geluid.beginpositie) || 0;
    const duur = Number(geluid.fragmentduur ?? geluid.maximale_duur) || 0.1;
    const speler = geluid.is_video ? document.createElement("video") : new Audio();
    speler.preload = "metadata";
    speler.playsInline = true;
    speler.autoplay = false;
    speler.controls = false;
    speler.src = geluid.mediabron;
    speler.muted = true;
    // 100% betekent de oorspronkelijke bronsterkte. Browservolume kan
    // maximaal 100%; een eventuele boost boven 100% werkt in de live-mixer.
    speler.volume = Math.max(0, Math.min(1, Number(geluid.volume ?? 1)));
    const preview = { geluidId, media: speler, start, duur, interval: null, gestart: false, afspeelbeurt: crypto.randomUUID() };
    toestand.preview = preview;
    toestand.live = null;
    toonMediascherm(geluid, true, start, speler);
    element("huidige-afspeelstand").textContent = "PREVIEW · ALLEEN JIJ";
    element("nu-actief-titel").textContent = geluid.naam;
    element("huidige-uitleg").textContent = "Dit geluid gaat niet naar Discord of VB-CABLE.";
    element("knop-preview-stop").disabled = false;
    stelSpelerActiefIn(true);
    werkSpelerTijdBij(0, duur);
    werkActieveKaartenBij();
    const beginMetAfspelen = async () => {
      if (toestand.preview !== preview) return;
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
        speler.muted = false;
        await speler.play();
        if (toestand.preview !== preview) return;
        if (geluid.is_video) {
          // Pas tonen als werkelijk een frame van de geselecteerde positie klaar is.
          window.DrostVideoSynchronisatie.toonPreviewNaEersteFrame(speler);
        }
        preview.gestart = true;
        registreerPreviewBijPython(geluidId, "gestart", 0, "start", preview.afspeelbeurt);
      } catch (fout) {
        stopPreview("browserfout");
        toonMelding(`Preview kon niet afspelen: ${fout.message}`, true);
      }
    };
    speler.addEventListener("loadedmetadata", beginMetAfspelen, { once: true });
    speler.addEventListener("ended", () => {
      if (toestand.preview === preview) stopPreview("klaar");
    });
    // Een browser kan afspelen pas na interactie toestaan. Start daarom al
    // tijdens de klik gedempt. Na het zoeken schakelen we het geluid in.
    speler.play().catch(() => {});
    preview.interval = setInterval(() => {
      if (toestand.preview !== preview) return;
      const gespeeld = Math.max(0, speler.currentTime - start);
      werkSpelerTijdBij(Math.min(gespeeld, duur), duur);
      if (gespeeld >= duur - .05) stopPreview("maximale_duur");
    }, 100);
  });
}

/*
  De live-speler volgt de werkelijk gemengde frames uit Python.
  Een MP4 wordt hier muted afgespeeld om dubbele audio te voorkomen.
*/
function werkLiveGeluidBij(status) {
  const id = status.huidig_geluid_id;
  if (id) {
    if (toestand.preview) stopPreview("live_gestart");
    const geluid = vindGeluid(id);
    if (!geluid) return;
    if (!toestand.live || toestand.live.afspeelbeurt !== status.afspeelbeurt_id) {
      // Nieuwe afspeelbeurt: de oude controller ruimt zijn videobuffer op.
      toestand.live?.videobediening?.stop();
      toestand.live = { geluidId: id, afspeelbeurt: status.afspeelbeurt_id, videobediening: null };
      laadRecentGebruikt().catch(() => {});
      toestand.verwachtGeluid = null;
      toestand.live.videobediening = toonMediascherm(
        geluid, false, Number(status.beginpositie_seconden) || 0
      );
      element("nu-actief-titel").textContent = geluid.naam;
      element("huidige-afspeelstand").textContent = "LIVE · NAAR VB-CABLE";
      element("huidige-uitleg").textContent = status.meeluisteren_aan
        ? "De ander hoort het via VB-CABLE. Het effect hoor je ook via je headset."
        : "Dit geluid wordt naar VB-CABLE gestuurd. Meeluisteren staat uit.";
      element("knop-preview-stop").disabled = true;
      stelSpelerActiefIn(true);
      werkActieveKaartenBij();
    }
    const afgespeeld = Number(status.afgespeelde_seconden) || 0;
    werkSpelerTijdBij(afgespeeld, Number(geluid.fragmentduur ?? geluid.maximale_duur) || 0.1);
    toestand.live.videobediening?.synchroniseerMetAudio(status);
  } else if (toestand.live) {
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

async function beginGeluidAfspelen(geluidId) {
  await voerGebruikersactieUit("Geluid naar gesprek sturen", async () => {
    const status = toestand.status;
    if (status?.toestand !== "verbonden") throw new Error("Klik eerst op Verbinden.");
    if (!status.effecten_aan) throw new Error("Zet Soundboard eerst aan.");
    const geluid = vindGeluid(geluidId);
    if (!geluid?.bestand_gevonden) throw new Error("Het bronbestand ontbreekt. Importeer het opnieuw.");
    stopPreview("live_aangevraagd");
    await vraagAanPython("POST", `/api/geluiden/${geluidId}/afspelen`, {});
    toestand.verwachtGeluid = { id: geluidId, gestart: Date.now() };
    stelSpelerActiefIn(true);
    element("nu-actief-titel").textContent = geluid.naam;
    element("huidige-afspeelstand").textContent = "LIVE · WORDT VOORBEREID";
    element("huidige-uitleg").textContent = "Python decodeert het fragment en start daarna de audiomixer.";
    toonVoorbereidingZonderVideo(geluid);
    toonMelding(`${geluid.naam} wordt naar VB-CABLE gestuurd.`);
  });
}

async function laadApparaten() {
  const antwoord = await vraagAanPython("GET", "/api/apparaten");
  const menu = element("microfoonkeuze");
  const eerder = menu.value;
  menu.replaceChildren();
  for (const apparaat of antwoord.microfoons || []) {
    const keuze = new Option(apparaat.naam, String(apparaat.nummer));
    menu.appendChild(keuze);
  }
  menu.value = [...menu.options].some((keuze) => keuze.value === eerder) ? eerder :
    ([...menu.options].find((x) => x.text.toLowerCase().includes("razer"))?.value || menu.options[0]?.value || "");
  const luistermenu = element("monitor-uitvoer");
  const gekozen = toestand.laatstGekozenMonitor ?? luistermenu.value;
  luistermenu.replaceChildren(new Option("Automatisch (Razer als beschikbaar)", ""));
  for (const apparaat of antwoord.uitvoerapparaten || []) {
    luistermenu.appendChild(new Option(apparaat.naam, String(apparaat.nummer)));
  }
  luistermenu.value = [...luistermenu.options].some((keuze) => keuze.value === gekozen) ? gekozen : "";
  if (!menu.options.length) toonMelding("Geen microfoon gevonden. Controleer Windows-microfoonrechten.", true);
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

function toonNieuweMeetwaarden(waarden, gemeten) {
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
  if (document.hidden || stroomVanEchteNiveaus || typeof EventSource === "undefined") return;
  const stroom = new EventSource("/api/niveaus/live");
  stroomVanEchteNiveaus = stroom;
  stroom.addEventListener("niveau", (gebeurtenis) => {
    if (document.hidden) return;
    try {
      const gegevens = JSON.parse(gebeurtenis.data);
      // Geen verzonnen audio: de browser tekent alleen de waarden die
      // Python tijdens de audiocallback daadwerkelijk heeft gemeten.
      streamingIsBeschikbaar = true;
      laatsteOntvangstVanNiveaus = performance.now();
      toonNieuweMeetwaarden(gegevens, Boolean(gegevens.gemeten));
    } catch (fout) {
      console.warn("Metergegevens waren ongeldig", fout);
    }
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
  vorigeMeterFrameTijd = null;
  if (document.hidden) {
    stopDeDirecteNiveaustroom();
  } else {
    startDeDirecteNiveaustroom();
    startMeterAnimatie();
  }
});

async function vernieuwStatus() {
  if (toestand.bezetteStatusaanvraag) return;
  toestand.bezetteStatusaanvraag = true;
  try {
    const status = await vraagAanPython("GET", "/api/status");
    toestand.status = status;
    const verbonden = status.toestand === "verbonden";
    const bezig = ["wordt_verbonden", "wordt_verbroken"].includes(status.toestand);
    const omschrijving = status.toestand === "wordt_verbonden" ? "Bezig met verbinden" :
      status.toestand === "wordt_verbroken" ? "Bezig met verbreken" :
      status.toestand === "fout" ? "Audiostoring" :
      verbonden ? (status.effecten_aan ? "Verbonden · Effecten aan" : "Verbonden · Alleen microfoon") : "Niet verbonden";
    element("kleine-status").querySelector("span").textContent = " " + omschrijving;
    element("kleine-status").classList.toggle("actief", verbonden);
    element("badge-status").textContent = omschrijving;
    element("badge-status").classList.toggle("actief", verbonden);
    element("knop-verbinden").disabled = verbonden || bezig || !element("microfoonkeuze").value;
    element("knop-verbreken").disabled = !verbonden && !bezig;
    element("microfoonkeuze").disabled = verbonden || bezig;
    element("knop-vernieuw").disabled = verbonden || bezig;
    element("knop-effecten").disabled = !verbonden;
    element("knop-effecten").setAttribute("aria-checked", String(Boolean(status.effecten_aan)));
    element("knop-monitor").setAttribute("aria-checked", String(Boolean(status.meeluisteren_aan)));
    const gemeten = Boolean(status.is_signaal_gemeten && verbonden);
    // De statusroute is een fallback. Een frisse 30 Hz-meting mag nooit
    // door een 200 ms oude statuswaarde worden teruggezet.
    if (!streamingIsBeschikbaar || performance.now() - laatsteOntvangstVanNiveaus > 250) {
      toonNieuweMeetwaarden(status, gemeten);
    }
    element("buffer-status").textContent = `Bufferproblemen: ${status.bufferproblemen}`;
    element("monitor-melding").textContent = status.meeluisterfout
      ? `Monitorfout: ${status.meeluisterfout}` : status.meeluisteruitvoer || "Eigen geluidsuitvoer";
    let extra = "Kies je microfoon en klik op Verbinden.";
    if (verbonden) extra = status.geluid_voorbereiden
      ? `Geluid wordt voorbereid: ${status.geluid_voorbereiden}`
      : (status.huidig_geluid ? `Speelt: ${status.huidig_geluid}` : `Verbonden met ${status.microfoon}`);
    if (bezig) extra = status.toestand === "wordt_verbonden"
      ? `Audiostream starten, poging ${status.startpoging} van ${status.maximale_startpogingen}`
      : "Verbinding wordt afgesloten.";
    if (status.toestand === "fout") extra = `Audiofout: ${status.fout || "Zie software.jsonl"}`;
    element("extra-status").textContent = extra;
    if (status.laatste_afspeelfout && status.laatste_afspeelfout !== toestand.laatsteAudiofout) {
      toestand.laatsteAudiofout = status.laatste_afspeelfout;
      toonMelding(`Afspeelfout: ${status.laatste_afspeelfout}`, true);
    }
    werkLiveGeluidBij(status);
  } catch (fout) {
    // Een losse statusfout mag een werkende snelle niveaustroom niet wissen.
    if (!streamingIsBeschikbaar || performance.now() - laatsteOntvangstVanNiveaus > 250) {
      toonNieuweMeetwaarden({}, false);
    }
    element("extra-status").textContent = "Python is onbereikbaar. Laat het terminalvenster open.";
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
        element("knop-importeer").textContent = `Importeren ${goed + mislukt + 1}/${bestanden.length}`;
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
    element("knop-importeer").textContent = "＋ Geluiden toevoegen";
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
function maakGroepenZichtbaar() {
  const lijst = element("groepen-lijst");
  lijst.replaceChildren();
  const voegFilterToe = (naam, id, aantal, beheerbaar = false) => {
    const rij = maakElement("div", "groep-filterrij");
    const knop = maakElement("button", `groep-filter${toestand.actieveGroep === id ? " gekozen" : ""}`);
    knop.type = "button";
    knop.append(maakElement("span", "groep-filternaam", naam),
                maakElement("span", "groep-aantal", String(aantal)));
    knop.addEventListener("click", () => {
      toestand.actieveGroep = id;
      if (beheerbaar) registreerGroepsgebruik(id);
      maakGroepenZichtbaar();
      maakBibliotheekZichtbaar();
    });
    if (beheerbaar) {
      knop.addEventListener("dragover", (event) => event.preventDefault());
      knop.addEventListener("drop", (event) => {
        event.preventDefault();
        voerGebruikersactieUit("Aan groep toevoegen", async () => {
          const item = JSON.parse(event.dataTransfer.getData("text/plain"));
          const geluidId = item.soort === "bibliotheek" ? item.id : toestand.favorieten[item.plek - 1];
          if (!geluidId) return;
          await vraagAanPython("POST", `/api/groepen/${id}/geluiden`, { geluid_id: geluidId });
          await laadBibliotheekOpnieuw();
        });
      });
    }
    rij.appendChild(knop);
    if (beheerbaar) {
      const menu = maakElement("button", "groep-acties", "···");
      menu.type = "button";
      menu.title = `Groep ${naam} hernoemen of verwijderen`;
      menu.addEventListener("click", () => voerGebruikersactieUit("Groep beheren", async () => {
        const keuze = window.prompt(`Groep: ${naam}\nVoer een nieuwe naam in, of laat leeg om de groep te verwijderen.`, naam);
        if (keuze === null) return;
        if (!keuze.trim()) {
          if (!window.confirm(`Groep '${naam}' verwijderen? De geluiden blijven bewaard.`)) return;
          await vraagAanPython("DELETE", `/api/groepen/${id}`);
        } else if (keuze.trim() !== naam) {
          await vraagAanPython("POST", `/api/groepen/${id}`, { naam: keuze.trim() });
        }
        await laadBibliotheekOpnieuw();
      }));
      rij.appendChild(menu);
    }
    lijst.appendChild(rij);
  };
  voegFilterToe("Alle geluiden", "alle", toestand.geluiden.length);
  voegFilterToe("Zonder groep", "zonder", toestand.geluiden.filter((geluid) => !(geluid.groep_ids || []).length).length);
  for (const groep of toestand.groepen) voegFilterToe(groep.naam, groep.id, groep.aantal_geluiden, true);
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

function vulGroepskeuzesInDeEditor(geluid) {
  const lijst = element("groepen-in-editor");
  lijst.replaceChildren();
  if (!toestand.groepen.length) {
    lijst.appendChild(maakElement("span", "geen-groep-hint", "Nog geen groepen. Maak een groep in de bibliotheek."));
    return;
  }
  for (const groep of toestand.groepen) {
    const label = maakElement("label", "groep-keuze");
    const vakje = maakElement("input");
    vakje.type = "checkbox"; vakje.value = groep.id;
    vakje.checked = (geluid.groep_ids || []).includes(groep.id);
    label.append(vakje, maakElement("span", "", groep.naam));
    lijst.appendChild(label);
  }
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
  element("knop-editor-preview").textContent = laden ? "Laden…" : speelt ? "❚❚ Pauzeren" : "▶ Afspelen";
  element("knop-editor-preview").disabled = laden;
  element("knop-editor-stop").disabled = !voorbeeld && toestand.editorAfspeelpositie <= Number(element("trim-begin").value);
  element("editor-speelstatus").textContent = tekst;
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
    speler.volume = .75;
    speler.src = geluid.mediabron;
    const voorbeeld = {
      speler, geluidId: geluid.id, speelt: false, laden: false,
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
    await wachtTotMediabestandBruikbaarIs(voorbeeld.speler);
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
      ? !(geluid.groep_ids || []).length : (geluid.groep_ids || []).includes(groep));
    const formaatKlopt = formaat === "alle" || geluid.formaat === formaat;
    return groepKlopt && formaatKlopt && geefDoorzoekbareTekstVanGeluid(geluid).includes(zoekterm);
  });
  const sortering = element("beheer-sortering").value;
  const opNaam = (a, b) => a.naam.localeCompare(b.naam, "nl", { numeric: true, sensitivity: "base" });
  zichtbaar.sort((a, b) => {
    if (sortering === "naam-terug") return -opNaam(a, b);
    if (sortering === "duur-kort") return (a.fragmentduur ?? Infinity) - (b.fragmentduur ?? Infinity) || opNaam(a, b);
    if (sortering === "duur-lang") return (b.fragmentduur ?? -1) - (a.fragmentduur ?? -1) || opNaam(a, b);
    if (sortering === "formaat") return a.formaat.localeCompare(b.formaat) || opNaam(a, b);
    return opNaam(a, b);
  });
  return zichtbaar;
}

function tekenGroepenoverzichtInBeheer() {
  const overzicht = element("beheer-groepkaarten");
  overzicht.replaceChildren();
  const huidigeGroep = element("beheer-groep").value;
  const opties = [
    { id: "alle", naam: "Alle geluiden", aantal: toestand.geluiden.length },
    { id: "zonder", naam: "Zonder groep", aantal: toestand.geluiden.filter((geluid) => !(geluid.groep_ids || []).length).length },
    ...toestand.groepen.map((groep) => ({ id: groep.id, naam: groep.naam,
      aantal: toestand.geluiden.filter((geluid) => (geluid.groep_ids || []).includes(groep.id)).length }))
  ];
  for (const optie of opties) {
    const knop = maakElement("button", "beheer-groepkaart", optie.naam);
    knop.type = "button";
    knop.appendChild(maakElement("span", "beheer-groepteller", optie.aantal));
    const actief = optie.id === huidigeGroep;
    knop.classList.toggle("actief", actief);
    knop.setAttribute("aria-pressed", String(actief));
    knop.addEventListener("click", () => {
      element("beheer-groep").value = optie.id;
      toestand.beheerZichtbaarAantal = 60;
      maakGroteBibliotheekZichtbaar();
    });
    overzicht.appendChild(knop);
  }
}

function vernieuwBeheerselectieTeller() {
  const aantal = toestand.beheerGeselecteerd.size;
  element("beheer-selectie-teller").textContent = `${aantal} geselecteerd`;
  element("knop-beheer-exporteer").disabled = aantal === 0;
  element("knop-beheer-koppel-groep").disabled = aantal === 0;
  element("knop-beheer-verwijderen").disabled = aantal === 0;
  element("knop-beheer-volume").disabled = aantal === 0;
}

function maakGroteBibliotheekZichtbaar() {
  sluitGeluidActiemenu();
  const groepmenu = element("beheer-groep");
  const vorigeGroep = groepmenu.value || "alle";
  groepmenu.replaceChildren();
  for (const [nummer, naam] of [["alle", "Alle groepen"], ["zonder", "Zonder groep"],
    ...toestand.groepen.map((groep) => [groep.id, groep.naam])]) {
    const optie = document.createElement("option"); optie.value = nummer; optie.textContent = naam;
    groepmenu.appendChild(optie);
  }
  groepmenu.value = [...groepmenu.options].some((optie) => optie.value === vorigeGroep) ? vorigeGroep : "alle";
  tekenGroepenoverzichtInBeheer();
  const groepskeuze = element("beheer-groep-toevoegen");
  const geselecteerdeGroep = groepskeuze.value;
  groepskeuze.replaceChildren(new Option("Groep kiezen", ""));
  for (const groep of toestand.groepen) groepskeuze.appendChild(new Option(groep.naam, groep.id));
  groepskeuze.value = toestand.groepen.some((groep) => groep.id === geselecteerdeGroep) ? geselecteerdeGroep : "";

  const zichtbaar = geefZichtbareBeheergeluiden();
  const lijst = element("beheer-lijst");
  lijst.replaceChildren();
  for (const geluid of zichtbaar.slice(0, toestand.beheerZichtbaarAantal)) {
    const rij = maakElement("div", "beheer-rij");
    rij.dataset.geluidId = geluid.id;
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
    const duur = maakElement("span", "beheer-rij-duur", `${geluid.formaat.toUpperCase()} · ${netteTijd(geluid.fragmentduur)}`);
    const preview = maakPreviewknopVoorGeluid(geluid);
    const bewerken = maakElement("button", "knop knop-ghost beheer-bewerken", "Bewerken");
    bewerken.type = "button";
    bewerken.addEventListener("click", () => openEditorVanuitBeheer(geluid.id));
    const meer = maakElement("button", "icoonknop bibliotheek-acties-knop", "···");
    meer.type = "button";
    meer.setAttribute("aria-label", `Meer acties voor ${geluid.naam}`);
    meer.setAttribute("aria-haspopup", "menu");
    meer.setAttribute("aria-expanded", "false");
    meer.addEventListener("click", (gebeurtenis) => {
      gebeurtenis.stopPropagation();
      toonGeluidActiemenu(geluid.id, meer);
    });
    rij.append(selectie, kunst, titel, duur, preview, bewerken, meer);
    lijst.appendChild(rij);
  }
  if (!zichtbaar.length) lijst.appendChild(maakElement("p", "lege-lijst", "Geen geluiden gevonden."));
  element("beheer-aantal-zichtbaar").textContent = `${zichtbaar.length} gevonden · ${toestand.geluiden.length} totaal`;
  element("knop-beheer-meer").hidden = zichtbaar.length <= toestand.beheerZichtbaarAantal;
  vernieuwBeheerselectieTeller();
  werkPreviewEnStopknoppenBij();
}

function openEditorVanuitBeheer(geluidId) {
  // Na het bewerken komen we terug in dezelfde gefilterde lijst.
  // Dat scheelt onnodig opnieuw zoeken wanneer je tientallen clips beheert.
  toestand.terugNaarBibliotheekbeheer = true;
  element("dialoog-bibliotheek").close();
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
    const antwoord = await fetch(`/api/geluiden/${keuzeVoorLosseExport.geluidId}/exporteer`, {
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
      let foutmelding = `Export mislukt met HTTP ${antwoord.status}.`;
      try { foutmelding = (await antwoord.json()).fout || foutmelding; } catch { /* De softwarelog bevat de oorzaak. */ }
      throw new Error(foutmelding);
    }
    const inhoudstype = {
      mp3: ["audio/mpeg"], mp4: ["video/mp4"], gif: ["image/gif"],
      afbeelding: ["image/png", "image/jpeg", "image/webp"]
    }[formaat];
    if (!inhoudstype?.some((soort) => antwoord.headers.get("Content-Type")?.startsWith(soort))) {
      throw new Error("Python stuurde geen geldig bestand van het gekozen formaat terug.");
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
  if (nummers.length > 250) { toonMelding("Exporteer maximaal 250 geluiden tegelijk.", true); return; }
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

async function importeerBibliotheekZip(bestand) {
  if (!bestand) return;
  if (!bestand.name.toLowerCase().endsWith(".zip") || bestand.size > 512 * 1024 * 1024) {
    throw new Error("Gebruik een DrostSoundboard ZIP van maximaal 512 MiB.");
  }
  toonMelding("Bibliotheek wordt geïmporteerd. Laat de pagina open.");
  const resultaat = await vraagAanPython("POST", "/api/bibliotheek/importeer", undefined, bestand);
  toestand.beheerGeselecteerd.clear();
  await laadBibliotheekOpnieuw();
  toonMelding(resultaat.melding || "Bibliotheek geïmporteerd.");
}

function koppelBibliotheekbeheer() {
  element("knop-bibliotheek-groot").addEventListener("click", () => {
    toestand.beheerZichtbaarAantal = 60;
    element("dialoog-bibliotheek").showModal();
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
  element("knop-beheer-nieuwe-groep").addEventListener("click", () => element("knop-nieuwe-groep").click());
  element("dialoog-bewerken").addEventListener("close", () => {
    if (!toestand.terugNaarBibliotheekbeheer) return;
    toestand.terugNaarBibliotheekbeheer = false;
    element("dialoog-bibliotheek").showModal();
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
    const bestand = gebeurtenis.target.files?.[0];
    voerGebruikersactieUit("Bibliotheek-ZIP importeren", async () => {
      try { await importeerBibliotheekZip(bestand); }
      finally { element("archiefkiezer").value = ""; }
    });
  });
}

function koppelAlleKnoppen() {
  document.addEventListener("pointerdown", (gebeurtenis) => {
    if (!gebeurtenis.target.closest("#geluid-actiemenu, .bibliotheek-acties-knop")) sluitGeluidActiemenu();
  });
  window.addEventListener("resize", sluitGeluidActiemenu);
  window.addEventListener("scroll", (gebeurtenis) => {
    if (!element("geluid-actiemenu").contains(gebeurtenis.target)) sluitGeluidActiemenu();
  }, true);
  document.addEventListener("keydown", (gebeurtenis) => {
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
  element("knop-vernieuw").addEventListener("click", () => voerGebruikersactieUit("Apparaten vernieuwen", laadApparaten));
  element("knop-verbinden").addEventListener("click", () => voerGebruikersactieUit("Verbinden", async () => {
    await vraagAanPython("POST", "/api/verbinden", { microfoonnummer: Number(element("microfoonkeuze").value) });
    toonMelding("De microfoon wordt verbonden."); await vernieuwStatus();
  }));
  element("knop-verbreken").addEventListener("click", () => voerGebruikersactieUit("Verbreken", async () => {
    stopPreview();
    await vraagAanPython("POST", "/api/verbreken", {});
    toonMelding("Verbinding wordt verbroken."); await vernieuwStatus();
  }));
  element("knop-effecten").addEventListener("click", () => voerGebruikersactieUit("Soundboard schakelen", async () => {
    await vraagAanPython("POST", "/api/effecten", { aan: !toestand.status?.effecten_aan });
    await vernieuwStatus();
  }));
  const monitorAanpassen = () => voerGebruikersactieUit("Meeluisteren instellen", async () => {
    const aan = element("knop-monitor").getAttribute("aria-checked") !== "true";
    const nummer = element("monitor-uitvoer").value;
    toestand.laatstGekozenMonitor = nummer;
    await vraagAanPython("POST", "/api/monitor", { aan, uitvoernummer: nummer ? Number(nummer) : null });
    await vernieuwStatus();
  });
  element("knop-monitor").addEventListener("click", monitorAanpassen);
  element("monitor-uitvoer").addEventListener("change", () => voerGebruikersactieUit("Luisterapparaat aanpassen", async () => {
    const nummer = element("monitor-uitvoer").value;
    toestand.laatstGekozenMonitor = nummer;
    await vraagAanPython("POST", "/api/monitor", {
      aan: Boolean(toestand.status?.meeluisteren_aan), uitvoernummer: nummer ? Number(nummer) : null
    });
    await vernieuwStatus();
  }));
  element("knop-stop").addEventListener("click", () => voerGebruikersactieUit("Geluid stoppen", async () => {
    if (element("knop-stop").disabled) return;
    stopPreview();
    await vraagAanPython("POST", "/api/stop", {});
    toestand.live = null; toestand.verwachtGeluid = null;
    werkActieveKaartenBij(); toonStilMediascherm();
    toonMelding("Geluid en animatie gestopt. Je microfoon blijft verbonden.");
  }));
  element("knop-preview-stop").addEventListener("click", () => stopPreview());
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !element("knop-stop").disabled && !document.querySelector("dialog[open]")) {
      e.preventDefault(); element("knop-stop").click();
    }
  });
  element("knop-nieuwe-groep").addEventListener("click", () => {
    element("nieuwe-groepsnaam").value = "";
    element("dialoog-groep").showModal();
    element("nieuwe-groepsnaam").focus();
  });
  element("formulier-groep").addEventListener("submit", (event) => {
    event.preventDefault();
    voerGebruikersactieUit("Groep maken", async () => {
      const antwoord = await vraagAanPython("POST", "/api/groepen", { naam: element("nieuwe-groepsnaam").value.trim() });
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
  element("knop-editor-preview").addEventListener("click", () =>
    voerGebruikersactieUit("Preview afspelen of pauzeren", speelEditorSelectieLokaal));
  element("knop-editor-stop").addEventListener("click", () => stopEditorPreview("editor_gestopt", true));
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
    voerGebruikersactieUit("Editorpreview met spatie", speelEditorSelectieLokaal);
  });
  element("dialoog-bewerken").addEventListener("close", () => {
    stopEditorPreview("editor_gesloten");
    toestand.editorIsAanHetSlepen = false;
    if (toestand.editorGolfvormWachttijd) clearTimeout(toestand.editorGolfvormWachttijd);
    toestand.golfvormVolgnummer++;
  });
  koppelBibliotheekbeheer();
  element("knop-importeer").addEventListener("click", () => element("bestandkiezer").click());
  element("bestandkiezer").addEventListener("change", (e) => voerGebruikersactieUit("Importeren", () =>
    importeerGekozenBestanden(Array.from(e.target.files || []))));
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
  element("bewerken-volume").addEventListener("input", () =>
    element("volume-uitleg").textContent = `${element("bewerken-volume").value}%`);
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
      const nieuweGroepen = Array.from(element("groepen-in-editor").querySelectorAll("input:checked"), (vak) => vak.value);
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

async function beginDashboard() {
  koppelSneltoetsenAanDashboard();
  koppelAlleKnoppen();
  koppelWeergaveKnoppen();
  koppelRecenteKnoppen();
  await Promise.allSettled([
    voerGebruikersactieUit("Audioapparaten ophalen", laadApparaten),
    voerGebruikersactieUit("Bibliotheek openen", laadBibliotheekOpnieuw),
    voerGebruikersactieUit("Weergave laden", laadPersoonlijkeWeergave),
    voerGebruikersactieUit("Recent gebruikt laden", () => laadRecentGebruikt())
  ]);
  await vernieuwStatus();
  startDeDirecteNiveaustroom();
  setInterval(vernieuwStatus, 200);
  // Eén rustige geschiedenis-update per 20 seconden, nooit per audioframe.
  setInterval(() => { if (!document.hidden) laadRecentGebruikt().catch(() => {}); }, 20000);
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
  element("thema-fout").hidden = true;
  toonThemaKeuzes();
}
function openThemaInstellingen() {
  themaConcept = { ...opgeslagenWeergave };
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
  element("knop-thema-herstellen").addEventListener("click", () => {
    themaConcept = { thema: "obsidian", accentkleur: null, gradient: "subtiel", gradientrichting: "rechtsboven", compact: false };
    vulThemaVelden();
    pasSchermthemaToe(themaConcept);
  });
  element("knop-thema-opslaan").addEventListener("click", () => voerGebruikersactieUit("Weergave opslaan", async () => {
    try {
      const gegevens = {
        thema: themaConcept.thema, accentkleur: themaConcept.accentkleur,
        gradient: themaConcept.gradient, gradientrichting: themaConcept.gradientrichting,
        compact: themaConcept.compact
      };
      opgeslagenWeergave = await vraagAanPython("POST", "/api/instellingen/weergave", gegevens);
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
  return datum.toLocaleDateString("nl-NL", { day: "numeric", month: "short" }) + ` · ${klok}`;
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
      geluid.wijze === "gesprek" ? "Naar call" : "Preview");
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
      toonMelding("Start DrostSoundboard via de nieuwe desktopstarter om globale toetsen te gebruiken.", true);
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
