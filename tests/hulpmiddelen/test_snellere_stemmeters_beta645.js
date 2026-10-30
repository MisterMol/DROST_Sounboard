'use strict';
// Simuleer alleen de echte meterfuncties; geen browser, audio- of HTTP-toegang.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const bron = fs.readFileSync('app/webinterface/statisch/dashboard.js', 'utf8');
const html = fs.readFileSync('app/webinterface/statisch/dashboard.html', 'utf8');
const begin = bron.indexOf('function meterStemDb(');
const einde = bron.indexOf('function werkStemvoorbeeldKnopBij(', begin);
const vanafStream = bron.indexOf('function toonNieuweMeetwaarden(');
const totStream = bron.indexOf('function startDeDirecteNiveaustroom(', vanafStream);
assert(begin >= 0 && einde > begin && vanafStream > 0 && totStream > vanafStream);
const ids = ['stemmeters-in', 'stemmeters-in-db', 'stemmeters-uit', 'stemmeters-uit-db', 'stemmeters-status', 'tekst-microfoon', 'tekst-uitvoer', 'tekst-microfoon-piek', 'tekst-uitvoer-piek'];
const onderdelen = Object.fromEntries(ids.map(id => [id, {style:{width:'0%'},textContent:''}]));
const context = {
  element: (id) => { assert.ok(onderdelen[id], id); return onderdelen[id]; },
  toonLiveSoundboardniveau: () => {},
  toonLimiterReductie: () => {},
  zetNieuweNiveausInMeters: () => {},
  toonRms: () => '0',
  toonVastgehoudenPiek: () => '0',
};
vm.createContext(context);
vm.runInContext(bron.slice(begin, einde), context);
vm.runInContext(bron.slice(vanafStream, totStream), context);
// Een preview levert samples, ook als de liveverbinding verbroken is.
context.toonNieuweMeetwaarden({
  toestand:'verbroken', is_signaal_gemeten:false,
  stemvoorbeeld:{actief:true, gemeten:true, microfoon_rms:0.15, stem_rms:0.07, driverproblemen:0}
}, false);
assert.match(onderdelen['stemmeters-in-db'].textContent, /−?16,5 dBFS/);
assert.match(onderdelen['stemmeters-uit-db'].textContent, /−?23,1 dBFS/);
assert.ok(parseFloat(onderdelen['stemmeters-in'].style.width) > 40);
assert.match(onderdelen['stemmeters-status'].textContent, /ontvangen/);
// Vervolgens komt dezelfde stem uit de live mixer.
context.toonNieuweMeetwaarden({
  toestand:'verbonden', is_signaal_gemeten:true, microfoon_rms:0.2,
  stem_rms:0.1, bufferproblemen:0, stemvoorbeeld:{actief:false, gemeten:false}
}, true);
assert.match(onderdelen['stemmeters-in-db'].textContent, /−?14,0 dBFS/);
assert.match(onderdelen['stemmeters-uit-db'].textContent, /−?20,0 dBFS/);
// Zacht geluid mag nooit als precies -60 dBFS worden voorgesteld.
context.toonNieuweMeetwaarden({
  toestand:'verbonden', is_signaal_gemeten:true, microfoon_rms:0.0004,
  stem_rms:0.0004, stemvoorbeeld:{actief:false, gemeten:false}
}, true);
assert.match(onderdelen['stemmeters-in-db'].textContent, /−?68,0 dBFS/);
assert.ok(parseFloat(onderdelen['stemmeters-in'].style.width) > 0);
// Een haperende preview krijgt geen oude waarden mee.
context.toonNieuweMeetwaarden({
  toestand:'verbroken', is_signaal_gemeten:false,
  stemvoorbeeld:{actief:true, gemeten:false, microfoon_rms:0, stem_rms:0}
}, false);
assert.equal(onderdelen['stemmeters-in-db'].textContent, '— dBFS');
assert.equal(onderdelen['stemmeters-in'].style.width, '0%');
assert.match(onderdelen['stemmeters-status'].textContent, /Wachten/);
// Extra statusverzoeken mogen de streamingmeter niet onnodig overschrijven.
assert.doesNotMatch(bron, /werkVerbindingsknopBij\(status\);\s*werkStemmetersBij\(status\)/);
assert.match(html, /−72 dBFS/);
console.log('OK: eigen microfoonpreview en live stemmeters vernieuwen met snelle stroom.');
