'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const bron = fs.readFileSync(path.resolve(__dirname,'../../app/webinterface/statisch/dashboard.js'),'utf8');
const html = fs.readFileSync(path.resolve(__dirname,'../../app/webinterface/statisch/dashboard.html'),'utf8');
const css = fs.readFileSync(path.resolve(__dirname,'../../app/webinterface/statisch/stijl.css'),'utf8');
function tussen(a,b){const i=bron.indexOf(a);const j=bron.indexOf(b,i);assert(i>=0&&j>i,`Kon niet lezen: ${a}`);return bron.slice(i,j);}
class E {
  constructor(){this.value='';this.textContent='';this.disabled=false;this.hidden=false;this.dataset={};this.style={};this.attrs={};this.events={};this.classList={toggle:()=>{}};}
  setAttribute(k,v){this.attrs[k]=v;}
  addEventListener(k,f){this.events[k]=f;}
  click(){return this.events.click?.();}
}
const items = new Map(); const el = id => {if(!items.has(id))items.set(id,new E());return items.get(id)};
const events=[];
const state={preview:null,live:null,verwachtGeluid:null};
const context=vm.createContext({toestand:state,element:el,maakElement:(tag,cls,label)=>{const e=new E();e.textContent=label;e.className=cls;return e;},
  beginGeluidAfspelen:id=>events.push(`uitzenden:${id}`),stopPreview:()=>events.push('preview:stop'),beginPreview:id=>events.push(`preview:${id}`),
  document:{querySelectorAll:sel=>sel.includes('lijst-uitzendknop')?[uitzend]:sel.includes('lijst-previewknop')?[preview]:[]},console});
let uitzend;
vm.runInContext(tussen('function maakUitzendknopVoorGeluid(', 'function maakBibliotheekZichtbaar(')+'this.maakUitzend = maakUitzendknopVoorGeluid;',context);
uitzend=context.maakUitzend({id:'a',naam:'Geluid A'});
const preview=new E();preview.dataset.geluidId='a';
vm.runInContext(tussen('function werkPreviewEnStopknoppenBij()', 'function maakUitzendknopVoorGeluid(')+'this.werkKnoppen = werkPreviewEnStopknoppenBij;',context);
uitzend.click();assert.deepEqual(events,['uitzenden:a']);
assert.equal(uitzend.textContent,'Uitzenden');
state.verwachtGeluid={id:'a'};
context.werkKnoppen();assert.equal(uitzend.textContent,'Stop');assert.equal(uitzend.attrs['aria-pressed'],'true');
// Stop gebruikt bewust de bestaande centrale Stop-actie.
el('knop-stop').events.click=()=>events.push('uitzenden:stop');
uitzend.click();assert.deepEqual(events,['uitzenden:a','uitzenden:stop']);
state.verwachtGeluid=null;
state.preview={geluidId:'a'};
context.werkKnoppen();assert.equal(preview.textContent,'Stop');assert.equal(uitzend.textContent,'Uitzenden');
assert(html.includes('id="zoeken"'));assert(html.includes('id="knop-preview-herhaal"'));
assert(!html.includes('id="knop-preview-herhaal" class="knop knop-ghost knop-klein" type="button" aria-pressed="false" title="Herhaal het huidige fragment" hidden'));
assert(css.includes('.lijst-uitzendknop'));assert(css.includes('max-width:540px'));
console.log('OK: direct uitzenden, actie Stop, previewstatus, responsieve bediening en zichtbaar Herhalen');

// Automatische verbinding mag alleen bij één microfoon en een werkende kabel,
// nooit nadat iemand handmatig heeft verbroken.
let verzoeken=[];
const selectie=new E(); selectie.value='4';
const toestand={automatischeVerbindingGeprobeerd:false,automatischEenMicrofoon:'4',microfoonHandmatigGekozen:false,status:{toestand:'verbroken'},
  vbCable:{status:'gereed',bruikbaar:true},verbindingInBehandeling:false};
const ctx=vm.createContext({toestand,element:id=>id==='microfoonkeuze'?selectie:new E(),
  window:{sessionStorage:{getItem:()=>null,setItem:()=>{},removeItem:()=>{}}},
  vraagAanPython:async(m,p,args)=>{verzoeken.push([m,p,args]);return p==='/api/status'?{toestand:'verbroken'}:{}},
  werkVerbindingsknopBij:()=>{},vernieuwStatus:async()=>{},toonMelding:()=>{},stopPreview:()=>{}});
vm.runInContext(tussen('function magAutomatischVerbinden()', '// Wisselt op basis van actuele serverstatus.')+
  tussen('async function schakelMicrofoonverbinding()', '// 6.1 Beta 2: pictogrammen')+
  'this.start = verbindEnigeMicrofoonBijStart;this.mag = magAutomatischVerbinden;',ctx);
(async()=>{
  assert.equal(ctx.mag(),true);
  await ctx.start();
  assert.equal(toestand.automatischeVerbindingGeprobeerd,true);
  assert.deepEqual(verzoeken.map(x=>x[1]),['/api/status','/api/status','/api/verbinden']);
  verzoeken=[]; await ctx.start();assert.equal(verzoeken.length,0,'geen tweede automatische start');
  toestand.automatischeVerbindingGeprobeerd=false;toestand.automatischEenMicrofoon=null;
  assert.equal(ctx.mag(),false,'meerdere microfoons zonder unieke selectie');
  toestand.automatischEenMicrofoon='4'; toestand.vbCable={status:'ontbreekt',bruikbaar:false};
  assert.equal(ctx.mag(),false,'zonder kabel niet verbinden');
  toestand.vbCable={status:'gereed',bruikbaar:true};
  toestand.microfoonHandmatigGekozen=true;
  assert.equal(ctx.mag(),false,'handmatige instelling blijft voorgaan');
  console.log('OK: één microfoon automatisch, geen tweede start, geen kabel en handmatige keuze');
})().catch(e=>{console.error(e);process.exitCode=1});
