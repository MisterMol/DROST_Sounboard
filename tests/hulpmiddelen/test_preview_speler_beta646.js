"use strict";
// Een mock van de browserbediening. Geen netwerk, microfoon of echte media nodig.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const bron = fs.readFileSync(path.join(__dirname, "../../app/webinterface/statisch/dashboard.js"), "utf8");
const begin = bron.indexOf("function toonStilMediascherm() {");
const eind = bron.indexOf("function registreerPreviewBijPython(", begin);
assert(begin !== -1 && eind > begin);
const elementen = new Map();
function elem(id) {
  if (!elementen.has(id)) {
    const evt = {};
    elementen.set(id, {
      style: {}, hidden: false, disabled: false, textContent: "", value: "0", attrs: {},
      classList: { toggle() {} },
      addEventListener(name, cb) { evt[name] = cb; },
      vuur(name, extra = {}) { return evt[name]?.(extra); },
      setAttribute(name, value) { this.attrs[name] = value; }
    });
  }
  return elementen.get(id);
}
let aantalGeloopt = 0;
let alleenPreviewGestopt = 0;
let bewaardVolume = null;
let herhaaldeBeelden = 0;
let analogeGains = 0;
const toestand = { preview: null, previewHerhalen: false, effectvolumePercentage: 75 };
const omgeving = {
  toestand, vindGeluid:()=>null, element: elem, setTimeout, clearTimeout, performance,
  netteTijd: n => `${Math.floor(n / 60)}:${String(Math.floor(n % 60)).padStart(2, "0")}`,
  maakElement: () => ({ appendChild() {} }), maakGolfIcoon: () => ({}),
  stelSpelerActiefIn: () => {},
  toonMediascherm: () => { herhaaldeBeelden++; },
  stopPreview: () => { alleenPreviewGestopt++; toestand.preview = null; },
  toonMelding: () => {},
  gebruikPreviewNormalisatie: () => { analogeGains++; },
  werkEffectvolumeWeergaveBij: () => {},
  voerGebruikersactieUit: (_name, cb) => cb(),
  vraagAanPython: async (_method, _path, gegevens) => { bewaardVolume = gegevens.percentage; return { percentage: gegevens.percentage }; },
  window: { requestAnimationFrame: () => 12 }
};
vm.createContext(omgeving);
vm.runInContext(bron.slice(begin,eind), omgeving);
const media = { currentTime: 5, duration: 30, ended: false, play() { aantalGeloopt++; return Promise.resolve(); } };
const preview = { media, start: 5, duur: 20, geluid: {is_video:true}, gestart:true, bezigMetZoeken:false, eindeBezig:false };
toestand.preview = preview;
const ga = vm.runInContext("zoekInPreview", omgeving);
const eindeFunctie = vm.runInContext("eindigPreviewFragment", omgeving);
const werk = vm.runInContext("werkPreviewTijdBij", omgeving);
ga(preview, .5);
assert.equal(media.currentTime,15,"zoeken is relatief aan het fragmentbegin, niet bronbegin");
assert.equal(elem("tijdlijn-tijd").textContent,"0:10");
assert.equal(elem("tijdlijn-vulling").style.width,"50%");
ga(preview, 1);
assert(media.currentTime < media.duration);
assert(Math.abs(media.currentTime - 25)<1e-6,"zoekpositie hoort aan het einde van geselecteerde fragment te stoppen");
toestand.previewHerhalen=true;
werk(preview);
assert.equal(media.currentTime,5,"herhalen begint bij de ingestelde beginpositie");
assert.equal(aantalGeloopt,1,"herhalen gebruikt bestaande bron zonder extra media-element");
// GIF-frame voor een willekeurig tijdstip kan niet nauwkeurig worden gezocht.
preview.geluid = { afbeelding:"/media/test.gif", is_video:false };
ga(preview,.5);
assert.equal(herhaaldeBeelden,0,"GIF niet willekeurig opnieuw opstarten tijdens zoeken");
ga(preview,0);
assert.equal(herhaaldeBeelden,1,"GIF herstart wanneer het fragment weer vooraan begint");
// Herhalen uit houdt het normale stoppad over.
toestand.previewHerhalen=false;
preview.eindeBezig=false; // eerder gestarte play() is in de browser inmiddels bevestigd.
eindeFunctie(preview);
assert.equal(alleenPreviewGestopt,1);
// Nieuw voorbeeld voor de bediening van de inputvelden.
toestand.preview = { media, start: 5, duur:20, geluid:{is_video:true}, gestart:true,
  bezigMetZoeken:false, normalisatieData:{}, tijdelijkVolume:null };
vm.runInContext("koppelPreviewSpelerbediening", omgeving)();
const slider = elem("tijdlijn-schuif");
slider.value="750";
slider.vuur("input");
assert.equal(media.currentTime,20,"met toetsenbord kan direct worden gesprongen");
slider.vuur("pointerdown");
slider.value="250";
slider.vuur("input");
assert.equal(media.currentTime,20,"slepen triggert geen reeks dure video-seeks");
slider.vuur("change");
assert.equal(media.currentTime,10,"bij loslaten wordt naar de juiste positie gesprongen");
const herhalenKnop = elem("knop-preview-herhaal");
herhalenKnop.vuur("click");
assert.equal(toestand.previewHerhalen,true);
assert.equal(herhalenKnop.attrs["aria-pressed"],"true");
const volumeknop = elem("speler-volume-schuif");
volumeknop.value = "55";
volumeknop.vuur("input");
assert.equal(toestand.effectvolumePercentage,55,"preview reageert direct via het gedeelde mastervolume");
assert(analogeGains>0);
(async () => {
  volumeknop.vuur("change");
  await new Promise(resolve => setTimeout(resolve, 100));
  assert.equal(bewaardVolume,55,"eenmalig opslaan na loslaten");
  assert.equal(toestand.effectvolumePercentage,55);
  assert.equal(elem("algemeen-effectvolume").value,"55");
  console.log("OK: fragment zoeken, MP4-synchronisatie, GIF-terugspoelen, loop, toetsenbord en volume");
})().catch(e=>{console.error(e);process.exitCode=1;});
