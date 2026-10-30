"use strict";
// Test echte gain-router uit dashboard.js zonder browser of fysieke microfoon.
const assert = require("assert");
const fs = require("fs");
const vm = require("vm");
const path = require("path");
const code = fs.readFileSync(path.join(__dirname, "../../app/webinterface/statisch/dashboard.js"), "utf8");
const begin = code.indexOf('// Een Web Audio GainNode is noodzakelijk');
const einde = code.indexOf('function maakElement(soort', begin);
assert(begin > 0 && einde > begin);
const els = {};
const getElement = (id) => els[id] ?? (els[id] = { textContent: "" });
let sourceCalls = 0;
let gainChanges = [];
class NepContext {
  constructor() { this.destination = {}; this.currentTime = 42; }
  createMediaElementSource(element) { sourceCalls++; return { connect() {} }; }
  createGain() { return { gain: { value: 0, setTargetAtTime(value) { gainChanges.push(value); } }, connect() {} }; }
  resume() { return Promise.resolve(); }
}
const toestand = { normalisatiestand: "uit", preview: null, editorVoorbeeld: null };
const context = {
  window: { AudioContext: NepContext },
  WeakMap, Error, Number, Math,
  toestand, element: getElement,
  vraagAanPython: async () => ({})
};
vm.createContext(context);
vm.runInContext(code.slice(begin, einde), context);
const audio = {};
const a = vm.runInContext('maakPreviewAudioBus', context)(audio);
const b = vm.runInContext('maakPreviewAudioBus', context)(audio);
assert.strictEqual(a.bus, b.bus, "zelfde media-element krijgt geen tweede output");
assert.strictEqual(sourceCalls, 1, "geen dubbele audioverbinding");
const preview = {
  audioBus: a.bus,
  normalisatieData: {
    versterkingen: { uit: 1.2, subtiel: 0.91, normaal: 0.7, sterk: 0.45 },
    correcties_db: { uit: 0, subtiel: -2.4, normaal: -4.7, sterk: -8.5 }
  }
};
toestand.preview = preview;
const toepassing = vm.runInContext('gebruikPreviewNormalisatie', context);
toepassing(preview, true);
assert.strictEqual(gainChanges.at(-1), 1.2);
assert(getElement('normalisatie-preview-resultaat').textContent.includes('Uit'));
toestand.normalisatiestand = 'sterk';
toepassing(preview, true);
assert.strictEqual(gainChanges.at(-1), 0.45, 'wijziging hoorbaar zonder herstart');
// Algemeen effectvolume werkt ook op een al spelende preview.
toestand.effectvolumePercentage = 60;
toepassing(preview, true);
assert(Math.abs(gainChanges.at(-1) - 0.27) < 1e-6, '60% maakt ook preview 40% zachter');
assert(getElement('normalisatie-preview-resultaat').textContent.includes('60%'));
toestand.effectvolumePercentage = 100;
toepassing(preview, true);
assert.strictEqual(gainChanges.at(-1), 0.45, '100% herstelt de oorspronkelijke preview');
assert(getElement('normalisatie-preview-resultaat').textContent.includes('-8.5 dB'));
assert(getElement('huidige-uitleg').textContent.includes('alleen lokaal'));
assert(code.includes('await preview.normalisatieVerzoek'), 'preview wacht op analyse');
assert(code.includes('speler.pause();'), 'gedempte speler wordt tijdens analyse gestopt');
assert(code.includes('leesPreviewNormalisatie(geluid.id, selectie.begin'), 'editor preview gebruikt selectie');
console.log('OK: gain, wisselen tijdens preview, geen dubbel geluid en editorselectie');
