"use strict";

// Beta 5.1: echte JavaScript-functies testen met een kleine nep-DOM.
// Geen browser, netwerk of Windows-audiostroom nodig.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const bron = fs.readFileSync(path.join(__dirname, "../../app/webinterface/statisch/dashboard.js"), "utf8");

function haalFunctieUitBron(naam) {
  let start = bron.indexOf(`function ${naam}(`);
  if (start > 6 && bron.slice(start - 6, start) === "async ") start -= 6;
  assert.ok(start >= 0, `Functie ontbreekt: ${naam}`);
  let diepte = 0;
  let begonnen = false;
  for (let i = start; i < bron.length; i++) {
    if (bron[i] === "{") { begonnen = true; diepte++; }
    if (bron[i] === "}") { diepte--; if (begonnen && diepte === 0) return bron.slice(start, i + 1); }
  }
  throw new Error(`Functie niet afgesloten: ${naam}`);
}

function maakKnooppunt() {
  const attributen = {};
  const klassen = new Set();
  return {
    disabled: false, hidden: false, value: "", textContent: "", href: "", style: {},
    attributes: attributen, classes: klassen,
    setAttribute(naam, waarde) { attributen[naam] = waarde; if (naam === "href") this.href = waarde; },
    getAttribute(naam) { return attributen[naam]; },
    removeAttribute(naam) { delete attributen[naam]; },
    classList: {
      toggle(naam, actief) { if (actief) klassen.add(naam); else klassen.delete(naam); }
    },
    scrollIntoView() {}, focus() {}
  };
}

async function main() {
  const knooppunten = new Map();
  const element = (id) => {
    if (!knooppunten.has(id)) knooppunten.set(id, maakKnooppunt());
    return knooppunten.get(id);
  };
  const toestand = { status: null, verbindingInBehandeling: false, vbCable: null };
  const window = { location: { hash: "" }, addEventListener() {} };
  const document = { title: "DrostSoundboard" };
  let serverStatus = { toestand: "verbroken" };
  let aanvragen = [];
  let previewsGestopt = 0;
  let statusverversingen = 0;
  let vertraagdeAanvraag = null;
  let foutNaGeaccepteerdeVerbinding = false;
  const meldingen = [];
  const context = {
    element, toestand, window, document, Number,
    vraagAanPython: async (methode, route, gegevens) => {
      aanvragen.push({ methode, route, gegevens });
      if (methode === "GET" && route === "/api/status") return serverStatus;
      if (methode === "POST" && route === "/api/verbinden") {
        if (vertraagdeAanvraag) return vertraagdeAanvraag;
        serverStatus = foutNaGeaccepteerdeVerbinding
          ? { toestand: "fout", fout: "Windows kan Razer en VB-CABLE niet openen." }
          : { toestand: "verbonden" };
      }
      if (methode === "POST" && route === "/api/verbreken") serverStatus = { toestand: "verbroken" };
      return {};
    },
    stopPreview: () => { previewsGestopt++; },
    toonMelding: (melding) => meldingen.push(melding),
    markeerHandmatigVerbroken: () => {},
    // Dit is geen menutest. De echte router sluit dat menu bij navigatie.
    sluitFavorietActiemenu: () => {},
    vernieuwStatus: async () => { statusverversingen++; }
  };
  vm.createContext(context);
  for (const naam of ["toonGekozenPagina", "koppelPaginanavigatie", "toonMicrofoonVerbindingsfout", "werkVerbindingsknopBij", "wachtOpBevestigdeMicrofoonverbinding", "schakelMicrofoonverbinding"]) {
    vm.runInContext(haalFunctieUitBron(naam), context);
  }
  // De DOM heeft in productie vaste labels; de nep-DOM krijgt dezelfde startlabels.
  element("knop-instellingen").textContent = "Instellingen";
  element("knop-instellingen").href = "#instellingen";
  element("knop-bibliotheek-pagina").textContent = "Bibliotheek";
  element("knop-dashboard-pagina").textContent = "Dashboard";
  // Navigeren wijzigt alleen zichtbaarheid en pagina, niet de server.
  context.toonGekozenPagina();
  assert.equal(element("dashboard").hidden, false);
  assert.equal(element("instellingen-pagina").hidden, true);
  assert.equal(element("knop-instellingen").textContent, "Instellingen");
  window.location.hash = "#instellingen";
  context.toonGekozenPagina();
  assert.equal(element("dashboard").hidden, true);
  assert.equal(element("instellingen-pagina").hidden, false);
  assert.equal(element("knop-instellingen").href, "#instellingen");
  assert.equal(element("knop-instellingen").getAttribute("aria-current"), "page");
  assert.equal(element("knop-dashboard-pagina").getAttribute("aria-current"), undefined);
  window.location.hash = "#dashboard";
  context.toonGekozenPagina();
  assert.equal(element("dashboard").hidden, false);
  assert.equal(element("instellingen-pagina").hidden, true);
  assert.equal(document.title, "DrostSoundboard");
  assert.equal(element("knop-dashboard-pagina").getAttribute("aria-current"), "page");
  assert.equal(aanvragen.length, 0);

  // Eén knop is actief bij verbinden en verbreken, maar niet tijdens overgangen.
  element("microfoonkeuze").value = "24";
  context.werkVerbindingsknopBij({ toestand: "verbroken" });
  assert.equal(element("verbindingsknop-tekst").textContent, "Verbinden");
  assert.equal(element("knop-verbinden").disabled, false);
  assert.equal(element("knop-verbinden").getAttribute("aria-label"), "Microfoon verbinden");
  context.werkVerbindingsknopBij({ toestand: "verbonden" });
  assert.equal(element("verbindingsknop-tekst").textContent, "Verbreken");
  assert.equal(element("knop-verbinden").disabled, false);
  assert.equal(element("knop-verbinden").getAttribute("aria-label"), "Microfoonverbinding verbreken");
  context.werkVerbindingsknopBij({ toestand: "wordt_verbroken" });
  assert.equal(element("knop-verbinden").disabled, true);
  context.werkVerbindingsknopBij({ toestand: "wordt_verbonden" });
  assert.equal(element("knop-verbinden").disabled, true);
  element("microfoonkeuze").value = "";
  context.werkVerbindingsknopBij({ toestand: "verbroken" });
  assert.equal(element("knop-verbinden").disabled, true);
  element("microfoonkeuze").value = "24";

  // Verbinden haalt eerst de actuele status op en verstuurt één verzoek.
  serverStatus = { toestand: "verbroken" };
  await context.schakelMicrofoonverbinding();
  assert.deepEqual(aanvragen.map(a => `${a.methode} ${a.route}`),
    ["GET /api/status", "POST /api/verbinden", "GET /api/status"]);
  assert.equal(aanvragen[1].gegevens.microfoonnummer, 24);
  assert.ok(meldingen.includes("Microfoon is verbonden."));
  assert.ok(!meldingen.includes("De microfoon wordt verbonden."));
  assert.equal(toestand.verbindingInBehandeling, false);
  aanvragen = [];

  // Verbreken stopt de preview maar zet geen nieuw microfoonsignaal op.
  serverStatus = { toestand: "verbonden" };
  await context.schakelMicrofoonverbinding();
  assert.deepEqual(aanvragen.map(a => `${a.methode} ${a.route}`), ["GET /api/status", "POST /api/verbreken"]);
  assert.equal(previewsGestopt, 1);
  aanvragen = [];

  // Tussentijdse servertoestanden veroorzaken geen tweede aanroep.
  serverStatus = { toestand: "wordt_verbonden" };
  await context.schakelMicrofoonverbinding();
  assert.deepEqual(aanvragen.map(a => `${a.methode} ${a.route}`), ["GET /api/status"]);
  aanvragen = [];

  // Twee snelle klikken mogen nooit twee verbindingsverzoeken starten.
  serverStatus = { toestand: "verbroken" };
  let los;
  vertraagdeAanvraag = new Promise((resolve) => { los = resolve; });
  const eerste = context.schakelMicrofoonverbinding();
  // De tweede komt binnen terwijl de eerste wacht op de server.
  await context.schakelMicrofoonverbinding();
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(aanvragen.filter(a => a.route === "/api/verbinden").length, 1);
  serverStatus = { toestand: "verbonden" };
  los({});
  await eerste;
  assert.equal(toestand.verbindingInBehandeling, false);
  vertraagdeAanvraag = null;
  aanvragen = [];

  // De VB-CABLE-waarschuwing blijft alleen een verbinding blokkeren.
  serverStatus = { toestand: "verbroken" };
  toestand.vbCable = { status: "ontbreekt" };
  await context.schakelMicrofoonverbinding();
  assert.equal(aanvragen.filter(a => a.methode === "POST").length, 0);
  toestand.vbCable = null;

  // Een HTTP 202 betekent nog geen geluid. De fout moet direct onder
  // de verbindingsknop zichtbaar blijven en mag niet als succes tellen.
  serverStatus = { toestand: "verbroken" };
  foutNaGeaccepteerdeVerbinding = true;
  await assert.rejects(context.schakelMicrofoonverbinding(), /Razer en VB-CABLE/);
  const foutVak = element("microfoon-verbinding-fout");
  assert.equal(foutVak.hidden, false);
  assert.match(foutVak.textContent, /Windows kan Razer en VB-CABLE niet openen/);
  assert.equal(element("verbindingsknop-tekst").textContent, "Verbinden");
  assert.equal(toestand.verbindingInBehandeling, false);
  assert.ok(!meldingen.includes("Enige microfoon automatisch verbonden."));

  // Pas na een echte nieuwe succesvolle verbinding verdwijnt de fout.
  foutNaGeaccepteerdeVerbinding = false;
  serverStatus = { toestand: "verbroken" };
  await context.schakelMicrofoonverbinding();
  assert.equal(element("microfoon-verbinding-fout").hidden, true);

  assert.ok(statusverversingen >= 7);
  console.log("OK: pagina navigatie, echte verbindingsbevestiging, blijvende foutmelding, dubbelklikbescherming en VB-CABLE.");
}
main().catch((fout) => { console.error(fout); process.exitCode = 1; });
