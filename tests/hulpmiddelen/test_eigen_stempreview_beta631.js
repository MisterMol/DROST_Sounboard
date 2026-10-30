'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const bron = fs.readFileSync(path.join(__dirname, '../../app/webinterface/statisch/dashboard.js'),'utf8');
const code=bron.slice(bron.indexOf('async function speelVoorbeeldstemAf()'),bron.indexOf('function stopVoorbeeldstem()'));
const status=[];
const context={
  toestand:{stemvoorbeeldActief:true,stemvoorbeeldBezig:false},
  element:(id)=>{ assert.equal(id,'stem-demo-status');return {set textContent(s){status.push(s)}};},
  fetch:()=>{ throw Error('Onterecht Bob/Elise opgevraagd tijdens microfoontest')},
};
vm.createContext(context);
vm.runInContext(code,context);
context.speelVoorbeeldstemAf().then(()=>{
 assert.ok(status.some(x=>x.includes('eigen stem')));
 console.log('OK: tijdens eigen microfoontest geen Bob/Elise-verzoek');
},e=>{ console.error(e);process.exitCode=1 });
