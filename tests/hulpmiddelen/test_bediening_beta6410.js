'use strict';
// Uitvoering van de echte hulpfuncties, met nagebootste API en DOM-rand.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.resolve(__dirname,'../../app/webinterface/statisch/dashboard.js'),'utf8');
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
function slice(a,b) {const i=source.indexOf(a),j=source.indexOf(b,i);assert(i>=0&&j>i);return source.slice(i,j);}
function make(api=async(_m,_p,b)=>({percentage:b?.percentage})) {
  const elements=new Map(), notices=[];
  function element(id) {
    if(!elements.has(id)) elements.set(id,{value:'75',textContent:'',hidden:false,disabled:false,attrs:{},events:{},
      classList:{toggle(){}},setAttribute(k,v){this.attrs[k]=v;},addEventListener(k,fn){this.events[k]=fn;}});
    return elements.get(id);
  }
  const state={effectvolumePercentage:75,preview:null,live:null,editorVoorbeeld:null,previewHerhalen:false,
    herhaalVolgnummer:0,herhaalVerzoek:null,laatsteAfspeelkeuze:null};
  const calls=[];
  const scope={toestand:state,element,performance,setTimeout,clearTimeout,console,
    toonMelding:(...x)=>notices.push(x),werkEffectvolumeWeergaveBij(){},gebruikPreviewNormalisatie(){},
    vindGeluid:id=>id==='a'?{id,bestand_gevonden:true}:null,
    geefDoorzoekbareTekstVanGeluid:g=>[g.naam,g.beschrijving].filter(Boolean).join(' '),
    vraagAanPython:api,voerGebruikersactieUit:(_n,fn)=>fn(),werkSpelerTijdBij(){},
    beginGeluidAfspelen:(...x)=>calls.push(['live',...x]),beginPreview:(...x)=>calls.push(['preview',...x]),
    zoekInPreview:(...x)=>calls.push(['seek',...x])};
  vm.createContext(scope);
  vm.runInContext(slice('// Beta 4.10: herstarten','function koppelPreviewSpelerbediening()')+
    '\nthis.volumeState=volumeBediening;',scope);
  return {scope,state,element,notices,calls};
}
(async()=>{
  let completed=0;
  const ok=msg=>{completed++;console.log('OK: '+msg);};
  {
    const sent=[], pending=[];
    const {scope,state}=make((m,p,b)=>{sent.push({p,b});return new Promise((resolve,reject)=>pending.push({resolve,reject}));});
    scope.planSoundboardvolume(20);await delay(90);assert.equal(sent.length,1);
    scope.planSoundboardvolume(35);scope.planSoundboardvolume(85,true);
    assert.equal(state.effectvolumePercentage,85);assert.equal(sent.length,1);
    pending[0].resolve({percentage:20});await delay(30);
    assert.equal(sent.length,2);assert.equal(sent[1].p,'/api/instellingen/effectvolume');
    assert.equal(sent[1].b.percentage,85);assert.equal(state.effectvolumePercentage,85);
    pending[1].resolve({percentage:85});await delay(5);
    assert.equal(scope.volumeState.gewenst,null);assert.equal(scope.volumeState.bezig,false);
    ok('Snelle volumewijzigingen worden serieel samengevoegd; laatste loslaatwaarde gaat niet verloren');
  }
  {
    const {scope,state,notices}=make(async()=>{throw new Error('API niet bereikbaar');});
    scope.planSoundboardvolume(20,true);await delay(25);
    assert.equal(state.effectvolumePercentage,75);assert.equal(scope.volumeState.bezig,false);
    assert(notices[0][0].includes('niet opgeslagen'));
    ok('Volumefout geeft melding, herstelt bevestigde stand en blokkeert schuif niet blijvend');
  }
  {
    const {scope,state}=make();
    for(const value of [-1,201,NaN,'30',true,35.5]) scope.planSoundboardvolume(value,true);
    assert.equal(state.effectvolumePercentage,75);assert.equal(scope.volumeState.gewenst,null);
    ok('Ongeldige volumewaarden worden niet verstuurd');
  }
  {
    const {scope,state,element}=make();state.live={afspeelbeurt:'run',bevestigdHerhalen:false};state.previewHerhalen=true;
    scope.werkHerhalenUitStatusBij({afspeelbeurt_id:'run',live_herhalen:false});
    assert.equal(state.previewHerhalen,false);assert.equal(element('knop-preview-herhaal').attrs['aria-pressed'],'false');
    ok('Herhalen toont werkelijke serverstand in plaats van een oude lokale keuze');
    await scope.stelHerhalenIn(true);
    scope.werkHerhalenUitStatusBij({afspeelbeurt_id:'run',live_herhalen:false});assert.equal(state.previewHerhalen,true);
    scope.werkHerhalenUitStatusBij({afspeelbeurt_id:'run',live_herhalen:true});assert.equal(state.herhaalVerzoek,null);
    scope.werkHerhalenUitStatusBij({afspeelbeurt_id:'run',live_herhalen:false});assert.equal(state.previewHerhalen,false);
    ok('Herhaalwijziging wacht op bevestiging en volgt daarna externe wijzigingen');
    await scope.stelHerhalenIn(true);state.herhaalVerzoek.geldigTot=0;
    scope.werkHerhalenUitStatusBij({afspeelbeurt_id:'run',live_herhalen:false});assert.equal(state.previewHerhalen,false);
    ok('Uitblijvende herhaalbevestiging blijft niet oneindig als ingeschakeld staan');
  }
  {
    const {scope,state,calls}=make();state.laatsteAfspeelkeuze={geluidId:'a',modus:'live',tijdelijkeSelectie:{beginpositie:3,maximale_duur:2,volume:.5}};
    scope.speelOpnieuwAf();assert.equal(calls[0][0],'live');assert.equal(calls[0][2].beginpositie,3);
    state.laatsteAfspeelkeuze.modus='preview';scope.speelOpnieuwAf();assert.equal(calls[1][0],'preview');
    state.laatsteAfspeelkeuze.geluidId='missing';scope.speelOpnieuwAf();assert.equal(calls.length,2);
    ok('Opnieuw na einde behoudt afspeelroute en tijdelijke fragmentinstellingen; ontbrekend bestand niet gestart');
  }
  {
    const {scope}=make();
    assert(scope.pastBijZoekopdracht({naam:'Café avond',beschrijving:'Goedemorgen allemaal'},'avond CAFE'));
    assert(scope.pastBijZoekopdracht({naam:'A',beschrijving:'Goedemorgen allemaal'},'allemaal goedemorgen'));
    assert(!scope.pastBijZoekopdracht({naam:'Café avond'},'cafe onbekend'));
    ok('Zoekwoorden mogen in willekeurige volgorde, zonder accent, over meerdere metadatawaarden staan');
  }
  {
    const {scope,state,element}=make();const requests=[];let reads=0;
    Object.assign(state,{automatischeVerbindingGeprobeerd:false,automatischEenMicrofoon:'4',microfoonHandmatigGekozen:false,
      status:{toestand:'verbroken'},vbCable:{status:'gereed',bruikbaar:true},verbindingInBehandeling:false});
    element('microfoonkeuze').value='4';
    Object.assign(scope,{window:{sessionStorage:{getItem:()=>null,setItem(){},removeItem(){}}},werkVerbindingsknopBij(){},
      vernieuwStatus:async()=>{},stopPreview(){},vraagAanPython:async(m,p)=>{
        requests.push(p);return p==='/api/status'?{toestand:++reads===1?'verbroken':'verbonden'}:{};
      }});
    vm.runInContext(slice('function magAutomatischVerbinden()', '// 6.1 Beta 2: pictogrammen'),scope);
    await scope.verbindEnigeMicrofoonBijStart();assert.equal(reads,2);
    assert(!requests.includes('/api/verbreken'));assert(!requests.includes('/api/verbinden'));
    ok('Automatisch verbinden verbreekt nooit een verbinding die een andere tab inmiddels heeft gemaakt');
  }
  console.log(completed+' gerichte JavaScript-scenarios geslaagd');
})().catch(error=>{console.error(error);process.exitCode=1;});
