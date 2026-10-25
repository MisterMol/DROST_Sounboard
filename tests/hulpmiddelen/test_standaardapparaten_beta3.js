"use strict";
// Test de echte functie uit dashboard.js met lichte vervangingen voor browserobjecten.
// Hiervoor is geen browser, netwerk of geluidsapparaat nodig.
const assert = require('assert').strict;
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const bron = fs.readFileSync(path.join(__dirname, '..', '..', 'app', 'webinterface', 'statisch', 'dashboard.js'), 'utf8');
const functie = bron.match(/async function laadApparaten\(\) \{[\s\S]*?\n\}/)?.[0];
assert.ok(functie, 'De apparatenfunctie is niet gevonden');

class Keuze {
  constructor(text, value) { this.text = text; this.value = String(value); }
}
class Selectie {
  constructor() { this.options = []; this.geselecteerd = ''; }
  replaceChildren(...opties) {
    this.options = opties;
    this.geselecteerd = opties[0]?.value || '';
  }
  appendChild(optie) { this.options.push(optie); }
  get value() { return this.geselecteerd; }
  set value(nieuw) { this.geselecteerd = this.options.some(x => x.value === String(nieuw)) ? String(nieuw) : ''; }
}

(async () => {
  const elementen = { 'microfoonkeuze': new Selectie(), 'monitor-uitvoer': new Selectie() };
  const toestand = { microfoonHandmatigGekozen: false, laatstGekozenMonitor: null };
  const antwoord = {
    standaard_microfoonnummer: 2,
    microfoons: [{ nummer: 5, naam: 'Microfoon (Razer)' },
                 { nummer: 2, naam: 'Microfoon (Logitech)' },
                 { nummer: 3, naam: 'Microfoon (HyperX)' }],
    uitvoerapparaten: [{ nummer: 8, naam: 'Luidsprekers (Realtek)' }],
  };
  const context = vm.createContext({
    toestand, Option: Keuze, element: naam => elementen[naam],
    vraagAanPython: async () => antwoord, toonMelding: () => {},
  });
  vm.runInContext(functie + '\nthis.__laad = laadApparaten;', context);
  const laad = context.__laad;
  await laad();
  assert.equal(elementen.microfoonkeuze.value, '2');
  assert.match(elementen.microfoonkeuze.options[2].text, /Windows-standaard/);
  assert.equal(elementen['monitor-uitvoer'].options[0].text, 'Automatisch (Windows-standaard)');

  antwoord.standaard_microfoonnummer = 3;
  await laad();
  assert.equal(elementen.microfoonkeuze.value, '3', 'Automatisch moet een veranderde Windows-standaard volgen');

  toestand.microfoonHandmatigGekozen = true;
  elementen.microfoonkeuze.value = '5';
  antwoord.standaard_microfoonnummer = 2;
  await laad();
  assert.equal(elementen.microfoonkeuze.value, '5', 'Handmatig gekozen microfoon moet blijven staan');

  toestand.microfoonHandmatigGekozen = false;
  antwoord.standaard_microfoonnummer = null;
  await laad();
  assert.equal(elementen.microfoonkeuze.value, '', 'Zonder standaard niet de eerste microfoon kiezen');
  assert.equal(elementen.microfoonkeuze.options[0].text, 'Kies een microfoon');
  console.log('OK: vier apparaatkeuze-situaties');
})().catch(fout => { console.error(fout); process.exitCode = 1; });
