"use strict";
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const bron = fs.readFileSync(path.resolve(__dirname, '../../app/webinterface/statisch/dashboard.js'), 'utf8');

function slice(a,b) { const begin = bron.indexOf(a), einde = bron.indexOf(b,begin); assert(begin >= 0 && einde > begin, `${a}: niet gevonden`); return bron.slice(begin,einde); }
const elementen = new Map();
function element(id) {
  if (!elementen.has(id)) {
    const gebeurtenissen = new Map();
    elementen.set(id, {
      value:'0',textContent:'',style:{},hidden:false,disabled:false,attrs:{},
      classList:{ toggle(){} },
      setAttribute(key,val){this.attrs[key]=val},
      getAttribute(key){return this.attrs[key] ?? null},
      addEventListener(key,cb){gebeurtenissen.set(key,cb)},
      vuur(key){return gebeurtenissen.get(key)?.()},
    });
  }
  return elementen.get(id);
}
const requests=[];
const toestand = { preview:null, live:null, previewHerhalen:false, effectvolumePercentage:75,
  afspeelVolgnummer:0, gewensteSpelmodus:null };
const omgeving = vm.createContext({
  toestand, vindGeluid:()=>null, element, performance:{now:()=>1000}, cancelAnimationFrame(){}, requestAnimationFrame(){return 1},
  window:{ requestAnimationFrame(){ return 3}}, console, setTimeout, clearTimeout,
  netteTijd:n => `0:${String(Math.floor(n)).padStart(2,'0')}`,
  gebruikPreviewNormalisatie(){},werkEffectvolumeWeergaveBij(){},toonMelding(){},
  voerGebruikersactieUit:(_,fn)=>fn(),
  vraagAanPython:async (m,p,body)=>{requests.push({m,p,body});return {percentage:body?.percentage}} });
vm.runInContext(slice('function werkSpelerTijdBij(', 'function registreerPreviewBijPython('),omgeving);
vm.runInContext('this.koppel = koppelPreviewSpelerbediening',omgeving);
omgeving.koppel();
const live = { afspeelbeurt:'11111111-1111-1111-1111-111111111111', duur:20, duurt:20,
  bezigMetZoeken:false, verstreken:0, laatstOntvangen:1000, zoekTot:0, animatie:null,
  videobediening:{ synchroniseerMetAudio() {} }};
toestand.live=live;
const schuif = element('tijdlijn-schuif');
schuif.value='500';
schuif.vuur('pointerdown');
schuif.vuur('input');
assert.equal(element('tijdlijn-vulling').style.width,'50%');
assert.equal(element('tijdlijn-tijd').textContent,'0:10');
(async()=>{
  await schuif.vuur('change');
  const zoek = requests.find(x => x.p==='/api/speler/live' && x.body?.positie !== undefined);
  assert.equal(zoek.body.afspeelbeurt_id,live.afspeelbeurt);
  assert.equal(zoek.body.positie,.5);
  const herhaal = element('knop-preview-herhaal');
  await herhaal.vuur('click');
  const herhaalVerzoek = requests.find(x => x.p==='/api/speler/live' && x.body?.herhalen === true);
  assert.equal(herhaalVerzoek.body.afspeelbeurt_id, live.afspeelbeurt);
  const vol = element('speler-volume-schuif');
  vol.value='55';
  vol.vuur('input');
  assert.equal(element('speler-volume-waarde').textContent,'55%');
  vol.vuur('change');
  await new Promise(resolve => setTimeout(resolve, 100));
  assert.equal(requests.find(x=>x.p==='/api/instellingen/effectvolume').body.percentage,55);
  console.log('OK: live seek, herhalen en live soundboardvolume');
})().catch(e=>{console.error(e);process.exitCode=1});

// Apart testen: laatste gebruikersintentie wint; nooit twee starts tegelijk.
const serie = vm.createContext({
  toestand:{afspeelVolgnummer:0, gewensteSpelmodus:null},
  voerGebruikersactieUit:(_naam,cb)=>cb(),Promise,
});
vm.runInContext(slice('let wachtrijVanSpeleracties =', 'function beginPreview(')+'\nthis.plan=planExclusieveSpeleractie;',serie);
const volgorde=[];
Promise.all([
  serie.plan('oud','live',()=>volgorde.push('oud')),
  serie.plan('nieuw','preview',()=>volgorde.push('nieuw')),
]).then(()=>{
  assert.deepEqual(volgorde,['nieuw']);
  console.log('OK: nieuw afspeelverzoek heeft voorrang');
}).catch(e=>{console.error(e);process.exitCode=1});
