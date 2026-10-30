'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const js = fs.readFileSync(path.resolve(__dirname, '../../app/webinterface/statisch/dashboard.js'), 'utf8');
const html = fs.readFileSync(path.resolve(__dirname, '../../app/webinterface/statisch/dashboard.html'), 'utf8');
const knip = (begin, eind) => {
  const a = js.indexOf(begin), b = js.indexOf(eind, a);
  assert(a >= 0 && b > a, `Kan ${begin} niet isoleren`);
  return js.slice(a, b);
};
class Elem {
  constructor(tag='div') { this.tag=tag; this.children=[]; this.value=''; this.style={}; this.events={}; this.checked=false; this.textContent=''; this.title=''; }
  replaceChildren(...elements) { this.children=[...elements]; }
  append(...elements) { this.children.push(...elements); }
  appendChild(element) { this.children.push(element); }
  addEventListener(event,handler) {this.events[event]=handler;}
  vuur(event) {return this.events[event]?.();}
}
const elementen = new Map();
const element = id => {if (!elementen.has(id)) elementen.set(id, new Elem()); return elementen.get(id);};
const maakElement = (tag, cls='', tekst) => {const el = new Elem(tag); el.className=cls; if (tekst !== undefined) el.textContent=String(tekst); return el;};
const groepen=Array.from({length:120},(_,i)=>({id:String(i), naam:`Map ${i+1}`, diepte:i%3===0?0:1, ouder_id:i%3===0?null:String(i-i%3)}));
const toestand = {groepen,editorGroepenKeuze:new Set()};
const omgeving = vm.createContext({toestand,element,maakElement,Set,Map, console,
  getoondeGroepenAlsBoom:()=>groepen});
vm.runInContext(knip('function toonDoorzoekbareGroepenInEditor()', 'function toonMediaInEditor('),omgeving);
const start=vm.runInContext('vulGroepskeuzesInDeEditor({groep_ids:["0","110"]})',omgeving);
assert.equal(element('groepen-in-editor').children.length,120);
assert.equal(toestand.editorGroepenKeuze.size,2);
element('editor-groepen-zoeken').value='Map 101';
vm.runInContext('toonDoorzoekbareGroepenInEditor()',omgeving);
assert(element('groepen-in-editor').children.length>=1);
assert.equal(toestand.editorGroepenKeuze.size,2, 'zoeken mag niet-afgebeelde vinkjes nooit wissen');
element('editor-groepen-zoeken').value='';
vm.runInContext('toonDoorzoekbareGroepenInEditor()',omgeving);
const checkbox=element('groepen-in-editor').children[15].children[0];
checkbox.checked=true; checkbox.vuur('change');
assert.equal(toestand.editorGroepenKeuze.size,3);
assert.equal(element('editor-groepen-teller').textContent,'3 van 120 mappen gekozen');
assert(html.includes('id="knop-editor-uitzenden"'));
assert(html.includes('id="knop-beheer-losmaak-groep"'));
assert(!html.includes('Bijvoorbeeld South Park'));
assert(!html.includes('meme, quote, cartman'));
// Een nog niet opgeslagen editorselectie moet expliciet meegestuurd worden.
const acties=[];
const weergave=vm.createContext({ toestand:{gekozenGeluid:'gekozen'}, geefEditorSelectie:()=>({begin:1.5,einde:2.8,duur:1.3}),
  element:id=>({value:'160'}), stopEditorPreview:()=>{}, beginGeluidAfspelen:(id,instellingen)=>acties.push({id,instellingen}),
});
vm.runInContext(knip('function startEditorUitzenden()', 'function stopEditorGeluid()')+'\nstartEditorUitzenden()',weergave);
assert.equal(acties[0].id,'gekozen');
assert.equal(acties[0].instellingen.volume,1.6);
assert.equal(acties[0].instellingen.beginpositie,1.5);
assert.equal(acties[0].instellingen.maximale_duur,1.3);
console.log('OK: editor, 120 mappen, selectie bij zoeken en uitzending met tijdelijke waarden');

// Controleren dat uitzenden de lopende lokale preview vervangt en niet opslaat.
(async()=>{
  const gebeurtenissen=[];
  const acties=[];
  const toestand2={status:{toestand:'verbonden',effecten_aan:true},editorUitzendGeluidId:null,
    verwachtGeluid:null,effectvolumePercentage:75};
  const omgeving2=vm.createContext({
    toestand:toestand2,
    applicatieVerbinding:{bereikbaar:true,nieuweSessie:false}, planExclusieveSpeleractie:(_n,_m,cb)=>cb(),
    vindGeluid:()=>({bestand_gevonden:true,id:'clip',naam:'Geluid'}),
    stopPreview:()=>gebeurtenissen.push('kaart-preview-stopt'),
    stopEditorPreview:()=>gebeurtenissen.push('editor-preview-stopt'),
    vraagAanPython:async (m,p,payload)=>{acties.push({m,p,payload});},
    stelSpelerActiefIn:()=>{},element:()=>({textContent:'',setAttribute(){},classList:{toggle(){}}}),toonVoorbereidingZonderVideo:()=>{},toonMelding:()=>{},
    werkActieveKaartenBij:()=>{},
    werkEditorKnoppenBij:()=>{},
  });
  vm.runInContext(knip('async function beginGeluidAfspelen(', 'function toonVBCableStatus(')+'\nthis.speel=beginGeluidAfspelen',omgeving2);
  await omgeving2.speel('clip',{beginpositie:1,maximale_duur:2,volume:1.3});
  assert.deepEqual(gebeurtenissen,['kaart-preview-stopt','editor-preview-stopt']);
  assert.equal(acties[0].p,'/api/geluiden/clip/afspelen');
  assert.equal(acties[0].payload.volume,1.3);
  assert.equal(toestand2.editorUitzendGeluidId,'clip');
  console.log('OK: uitzenden vervangt preview met tijdelijke editorinstellingen');
})().catch(e=>{console.error(e);process.exitCode=1});
