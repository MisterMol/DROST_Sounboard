'use strict';
// Voer de echte requestfuncties uit. Alleen fetch en de DOM-rand zijn nagebootst.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const assert=require('node:assert/strict');
const source=fs.readFileSync(path.resolve(__dirname,'../../app/webinterface/statisch/dashboard.js'),'utf8');
const start=source.indexOf('// Bereikbaarheid van de app'),end=source.indexOf('\nfunction toonMelding(',start);
assert(start>=0&&end>start);
function make(fetchImpl,fastTimeout=false){
  const nodes=new Map();const element=id=>{
    if(!nodes.has(id))nodes.set(id,{hidden:true,textContent:'',classList:{remove(){}},querySelector(){return {textContent:''}}});
    return nodes.get(id);
  };
  const c={element,fetch:fetchImpl,AbortController,Response,Error,TypeError,DOMException,
    beveiligingscode:'test-only',setTimeout:(f,n)=>setTimeout(f,fastTimeout?Math.min(n,10):n),clearTimeout};
  vm.createContext(c);vm.runInContext(source.slice(start,end)+'\nthis.verbindingsstatus=applicatieVerbinding;',c);
  return {c,element};
}
(async()=>{
 let count=0;const ok=s=>{count++;console.log('OK: '+s)};
 {
  const calls=[];const {c}=make(async(p,o)=>{calls.push([p,o]);return new Response('{"ok":true}',{status:200})});
  const value=await c.vraagAanPython('POST','/api/stop',{test:1});
  assert.equal(value.ok,true);assert.equal(calls.length,1);assert.equal(calls[0][1].headers['X-Drost-Token'],'test-only');
  assert.equal(JSON.parse(calls[0][1].body).test,1);assert.equal(c.verbindingsstatus.bereikbaar,true);
  ok('Verzoek bereikt fetch exact eenmaal, met token en ongewijzigde JSON-inhoud');
 }
 {
  let calls=0;const {c,element}=make(async()=>{calls++;throw new TypeError('Failed to fetch')});
  await assert.rejects(c.vraagAanPython('POST','/api/stop',{}),e=>e.foutcode==='APP-OFFLINE'&&e.message.includes('Staat de applicatie aan?'));
  assert.equal(calls,1);assert.equal(element('app-verbinding-melding').hidden,false);
  ok('Netwerkfout krijgt Nederlandse melding, geen automatische herhaling van schrijfverzoek');
 }
 {
  const {c}=make(async()=>new Response('{"fout":"De gekozen microfoon is niet beschikbaar.","oorzaakcode":"WEB-002"}',{status:400}));
  await assert.rejects(c.vraagAanPython('POST','/api/verbinden',{}),e=>e.foutcode==='WEB-002'&&e.message.includes('microfoon'));
  assert.equal(c.verbindingsstatus.bereikbaar,true);ok('HTTP-invoerfout is geen verbindingsfout');
 }
 {
  const {c}=make(async()=>new Response('{"fout":"ongeldig token","oorzaakcode":"WEB-022"}',{status:403}));
  await assert.rejects(c.vraagAanPython('POST','/api/stop',{}),e=>e.message.includes('eerdere sessie'));
  assert.equal(c.verbindingsstatus.nieuweSessie,true);ok('Verlopen sessie vraagt vernieuwen, geen stil opnieuw sturen');
 }
 {
  const {c}=make(async()=>new Response('{"fout":"Traceback Python /tmp/geheim","referentie":"aabbcc112233"}',{status:500}));
  await assert.rejects(c.vraagAanPython('GET','/api/status'),e=>!e.message.includes('Traceback')&&!e.message.includes('/tmp')&&e.message.includes('aabbcc112233'));
  ok('Onverwachte serverfout houdt referentie maar toont geen Python-traceback');
 }
 {
  const {c}=make(async()=>new Response('geen JSON',{status:200}));
  await assert.rejects(c.vraagAanPython('GET','/api/status'),e=>e.message.includes('niet gelukt')&&!e.message.includes('JSON'));
  ok('Beschadigd antwoord geeft bruikbare melding in plaats van JSON-parsefout');
 }
 {
  const {c}=make((p,o)=>new Promise((resolve,reject)=>o.signal.addEventListener('abort',()=>reject(new DOMException('Aborted','AbortError')))),true);
  await assert.rejects(c.vraagAanPython('POST','/api/stop',{}),e=>e.foutcode==='APP-TIMEOUT'&&e.message.includes('mogelijk al uitgevoerd'));
  ok('Time-out meldt dat de handeling al uitgevoerd kan zijn');
 }
 {
  const {c}=make((p,o)=>new Promise((resolve,reject)=>o.signal.addEventListener('abort',()=>reject(new DOMException('Aborted','AbortError')))));
  const controller=new AbortController();const waiting=c.haalBijApplicatie('/api/test',{signal:controller.signal});controller.abort();
  await assert.rejects(waiting,e=>e.name==='AbortError');assert.equal(c.verbindingsstatus.bereikbaar,null);
  ok('Bewust geannuleerd verzoek noemt de app niet onbereikbaar');
 }
 {
  const {c}=make(async()=>new Response('{}'));
  for(const raw of ['Failed to fetch','NetworkError when attempting to fetch resource','Load failed'])
    assert(c.leesbareBrowsermelding(raw).includes('Staat de applicatie aan?'));
  assert(c.leesbareBrowsermelding('NotAllowedError').includes('browser'));
  ok('Bekende browsermeldingen worden Nederlandse gebruikerstekst');
 }
 console.log(count+' request- en meldingenscenarios geslaagd');
})().catch(e=>{console.error(e);process.exitCode=1});
