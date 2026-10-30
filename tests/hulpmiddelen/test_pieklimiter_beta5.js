"use strict";
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');
const bron = fs.readFileSync(path.join(__dirname, '..', '..', 'app', 'webinterface', 'statisch', 'dashboard.js'), 'utf8');
const start = bron.indexOf('function toonLimiterReductie(');
const stop = bron.indexOf('\nfunction toonNieuweMeetwaarden(', start);
assert(start !== -1 && stop > start, 'Verwacht limiterweergave in dashboard.js');
const html = fs.readFileSync(path.join(__dirname, '..', '..', 'app', 'webinterface', 'statisch', 'dashboard.html'), 'utf8');
assert(html.includes('id="knop-limiter"'));
assert(html.includes('id="limiter-reductie"'));
assert(bron.includes('"/api/instellingen/pieklimiter"'));
const elementen = {
  'limiter-reductie': { textContent: '' },
  'limiter-balk': { style: { width: '' } },
};
const context = { toestand: { limiterAan: true }, element: (id) => elementen[id] };
vm.createContext(context);
vm.runInContext(bron.slice(start, stop), context);
context.toonLimiterReductie(8.4, true);
assert.strictEqual(elementen['limiter-reductie'].textContent, 'Piekreductie: 8,4 dB');
assert(parseFloat(elementen['limiter-balk'].style.width) > 40);
context.toonLimiterReductie(8.4, false);
assert.strictEqual(elementen['limiter-reductie'].textContent, 'Piekreductie: 0,0 dB');
context.toestand.limiterAan = false;
context.toonLimiterReductie(9.2, true);
assert.strictEqual(elementen['limiter-reductie'].textContent, 'Piekreductie: 0,0 dB');
console.log('OK: limiterstatus, dB-meter, uitstand en dashboardinstelling');
