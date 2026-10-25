"use strict";

// Deze test gebruikt nepmedia om precies de ongewenste seek en dubbele start
// te controleren. Er zijn geen MP4-bestanden of audiostuurprogramma's nodig.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

class NepKlassen {
  constructor() { this.klassen = new Set(); }
  add(...namen) { namen.forEach(n => this.klassen.add(n)); }
  remove(...namen) { namen.forEach(n => this.klassen.delete(n)); }
  contains(naam) { return this.klassen.has(naam); }
}

class NepElement {
  constructor(tagName) {
    this.tagName = tagName.toUpperCase();
    this.children = [];
    this.classList = new NepKlassen();
    this.events = new Map();
    this.dataset = {};
    this.currentTimeValue = 0;
    this.duration = 29;
    this.readyState = 4;
    this.paused = true;
    this.seeking = false;
    this.playbackRate = 1;
    this.aantalZoekopdrachten = 0;
    this.aantalStarten = 0;
  }
  set className(waarde) {
    this.classList.klassen = new Set(String(waarde).split(/\s+/).filter(Boolean));
  }
  get className() { return [...this.classList.klassen].join(" "); }
  appendChild(k) { this.children.push(k); }
  addEventListener(n, fn) { this.events.set(n, [...(this.events.get(n) || []), fn]); }
  removeEventListener(n, fn) { this.events.set(n, (this.events.get(n) || []).filter(f => f !== fn)); }
  zend(n) { for (const cb of this.events.get(n) || []) cb(); }
  get currentTime() { return this.currentTimeValue; }
  set currentTime(waarde) { this.aantalZoekopdrachten++; this.currentTimeValue = waarde; this.seeking = true; }
  async play() { this.aantalStarten++; this.paused = false; }
  pause() { this.paused = true; }
  load() { }
  removeAttribute() { }
  requestVideoFrameCallback(cb) { this.eersteFrame = cb; return 101; }
  cancelVideoFrameCallback() { this.eersteFrame = null; }
}

const venster = {};
const sandbox = {
  window: venster,
  document: { createElement: soort => new NepElement(soort) },
  setTimeout, clearTimeout,
  requestAnimationFrame: fn => fn(),
  Date, console
};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(path.resolve(__dirname, '../../app/webinterface/statisch/video_synchronisatie.js'), 'utf8'), sandbox);

const volgendeMicrotaak = () => new Promise(resolve => setImmediate(resolve));

(async () => {
  const fouten = [];
  const speler = venster.DrostVideoSynchronisatie.maakLiveVideospeler({
    bron: '/media/11111111-1111-1111-1111-111111111111',
    stilstaandBeeld: '/afbeeldingen/foto.png',
    beginpositie: 2.0,
    bijFout: f => fouten.push(f)
  });
  const video = speler.video;
  assert.equal(video.autoplay, false);
  assert.equal(video.loop, false);
  assert.equal(video.muted, true);
  assert.equal(speler.element.children.length, 2);
  assert.equal(video.aantalStarten, 0);

  // Tijdens het laden loopt de audio al een kwart seconde: begin op 2,25.
  speler.synchroniseerMetAudio({afgespeelde_seconden: .25, beginpositie_seconden: 2});
  video.zend('loadedmetadata');
  assert.equal(video.aantalZoekopdrachten, 1);
  assert.equal(video.currentTime, 2.25);
  assert.equal(video.aantalStarten, 0, 'video mag niet vóór de seek starten');
  assert.equal(video.classList.contains('video-wacht-op-beeld'), true);
  video.seeking = false;
  video.zend('seeked');
  await volgendeMicrotaak();
  assert.equal(video.aantalStarten, 1);
  assert.equal(video.classList.contains('video-zichtbaar'), false);
  video.eersteFrame();
  assert.equal(video.classList.contains('video-zichtbaar'), true);

  // Veel serverstatussen rond de werkelijke positie mogen niet steeds seeken.
  for (let i = 0; i < 60; i++) {
    video.currentTimeValue = 2.25 + i * .1;
    speler.synchroniseerMetAudio({afgespeelde_seconden: .25 + i * .1 + .10, beginpositie_seconden: 2});
  }
  assert.equal(video.aantalZoekopdrachten, 1);
  assert.equal(video.playbackRate, 1);

  // Kleiner structureel verschil vraagt alleen lichte snelheidsaanpassing.
  video.currentTimeValue = 8;
  speler.synchroniseerMetAudio({afgespeelde_seconden: 6.5, beginpositie_seconden: 2});
  assert.equal(video.playbackRate, 1.03);
  assert.equal(video.aantalZoekopdrachten, 1);

  speler.stop();
  assert.equal(video.paused, true);
  assert.equal(video.aantalZoekopdrachten, 1);
  speler.stop(); // idempotent
  assert.equal(fouten.length, 0);
  console.log('Video controller OK');
})().catch(fout => { console.error(fout); process.exitCode = 1; });
