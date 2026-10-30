"use strict";
// Bekijk alleen de kleine UI-functies. Geen browser of echte audio nodig.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const bron = fs.readFileSync('app/webinterface/statisch/dashboard.js', 'utf8');
const begin = bron.indexOf('function berekenSoundboardDempingDb(');
const eind = bron.indexOf('async function laadAlgemeenEffectvolume(', begin);
assert(begin >= 0 && eind > begin, 'volumefuncties ontbreken');
const velden = new Map([
  ['effectvolume-live', {textContent: ''}],
  ['effectvolume-hint', {textContent: ''}],
  ['effectvolume-demping', {textContent: ''}],
  ['algemeen-effectvolume-waarde', {textContent: ''}],
]);
const omgeving = { element: id => {assert(velden.has(id), `onbekend element ${id}`); return velden.get(id)} };
vm.createContext(omgeving);
vm.runInContext(bron.slice(begin, eind), omgeving);
vm.runInContext('werkEffectvolumeWeergaveBij(75)', omgeving);
assert.match(velden.get('effectvolume-demping').textContent, /2,5 dB/);
vm.runInContext('werkEffectvolumeWeergaveBij(0)', omgeving);
assert.match(velden.get('effectvolume-demping').textContent, /volledig stil/);
vm.runInContext('werkEffectvolumeWeergaveBij(100)', omgeving);
assert.match(velden.get('effectvolume-demping').textContent, /0,0 dB/);
vm.runInContext('toonLiveSoundboardniveau({effect_actief: true, effect_rms_voor: 0.3, effect_rms_na: 0.225}, true)', omgeving);
assert.match(velden.get('effectvolume-live').textContent, /Effect vóór:.*Na volume:/);
assert.match(velden.get('effectvolume-live').textContent, /-10,5 dBFS/);
assert.match(velden.get('effectvolume-live').textContent, /-13,0 dBFS/);
vm.runInContext('toonLiveSoundboardniveau({effect_actief: false}, true)', omgeving);
assert.match(velden.get('effectvolume-live').textContent, /Speel een geluid af/);
console.log('Beta 4.4: gemeten niveau en dB-demping OK');
