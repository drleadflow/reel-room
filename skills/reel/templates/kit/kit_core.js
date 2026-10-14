/* kit_core.js: Reel Room component kit runtime (window.RRK), shared helpers. Loaded once per page by rrkit.mount().
 *
 * Seek-safe rules (same as engine/motion/motion.js):
 *   - hidden states are set once at build (gsap.set), never on the timeline
 *   - every event goes through Q() (half a frame early, so frame N sees it)
 *   - entrances are fromTo(..., immediateRender:false); per-frame values (counters, wipes) are one tl.set per frame
 *   - eases are intent tokens (RRM.EASE); this file carries the same table as a fallback when the motion layer is off
 *   - no Math.random / Date; variation comes from a seeded generator
 */
(function (root) {
  'use strict';
  if (root.RRK && root.RRK.__core) return;
  var FPS = 30;
  var EASE0 = { snap: 'expo.out', glide: 'power4.out', land: 'back.out(1.4)', pop: 'back.out(2.2)', stamp: 'power4.out',
    drift: 'sine.inOut', camera: 'power2.inOut', settle: 'power2.out', whip: 'expo.inOut', draw: 'power2.inOut',
    exit: 'power3.in', fall: 'power2.in', wobble: 'elastic.out(1,0.45)', push: 'none' };
  function E(n) { var r = root.RRM; var v = (r && r.EASE && r.EASE[n]) || EASE0[n]; if (!v) throw new Error('RRK: unknown ease token ' + n); return v; }
  function Q(t) { return Math.max(0, (Math.round(t * FPS + 1e-3) - 0.5) / FPS); }
  function F(t) { return Math.round(t * FPS); }
  function prng(seed) { var s = (seed >>> 0) || 1; return function () { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; }; }
  function curve(n) { return gsap.parseEase(E(n)); }
  function one(r, s) { return r.querySelector(s); }
  function all(r, s) { return Array.prototype.slice.call(r.querySelectorAll(s)); }

  // fromTo that never shows its from-state before its frame
  function ft(tl, el, from, to, t) { to.immediateRender = false; tl.fromTo(el, from, to, Q(t)); }

  // the piece root: hidden at build, on at t_in, off at t_out (after its exit)
  function life(tl, el, t0, t1) {
    gsap.set(el, { autoAlpha: 0 });
    tl.set(el, { autoAlpha: 1 }, Q(t0));
    if (t1 !== null && t1 !== undefined) tl.set(el, { autoAlpha: 0 }, Q(t1));
  }

  // hero entrance: blur + scale + offset (at least two, per the Motion v2 rule)
  function heroIn(tl, el, t, o) {
    o = o || {};
    ft(tl, el, { y: o.y === undefined ? 44 : o.y, x: o.x || 0, scale: o.scale || 0.93, rotation: o.rot || 0, filter: 'blur(' + (o.blur || 12) + 'px)' },
      { y: 0, x: 0, scale: 1, rotation: 0, filter: 'blur(0px)', duration: o.dur || 0.44, ease: E(o.ease || 'snap') }, t);
  }
  // exits: about twice as fast as entrances; returns the time the piece is fully gone
  function heroOut(tl, el, t, style) {
    style = style || 'blur';
    if (style === 'cut') return t;
    if (style === 'fold') { tl.to(el, { scaleY: 0, autoAlpha: 0, duration: 0.16, ease: E('exit') }, Q(t)); return t + 0.17; }
    if (style === 'fall') {
      tl.to(el, { y: '-=30', duration: 0.08, ease: E('settle') }, Q(t));
      tl.to(el, { y: 1500, rotation: 18, duration: 0.42, ease: E('fall') }, Q(t + 0.08)); return t + 0.5;
    }
    if (style === 'lift') { tl.to(el, { y: -40, autoAlpha: 0, filter: 'blur(8px)', duration: 0.18, ease: E('exit') }, Q(t)); return t + 0.19; }
    tl.to(el, { autoAlpha: 0, scale: 0.96, filter: 'blur(10px)', duration: 0.18, ease: E('exit') }, Q(t)); return t + 0.19;
  }
  // a stroke (path with pathLength="1") draws on
  function draw(tl, el, t, dur, ease) {
    gsap.set(el, { strokeDasharray: 1, strokeDashoffset: 1 });
    ft(tl, el, { strokeDashoffset: 1 }, { strokeDashoffset: 0, duration: dur || 0.4, ease: E(ease || 'draw') }, t);
  }
  // per-frame number: v(p) from a -> b over dur with an intent ease, written as text once per frame
  function count(tl, el, t, dur, a, b, fmt, easeName) {
    var ez = curve(easeName || 'glide'), n = Math.max(1, F(dur));
    for (var i = 0; i <= n; i++) {
      var v = a + (b - a) * ez(i / n);
      tl.set(el, { innerHTML: fmt(v, i === n) }, Q(t + i / FPS));
    }
  }
  function fmtNum(dec, sep) {
    return function (v, last) {
      var s = (last ? v : v).toFixed(dec || 0);
      if (sep !== false) { var p = s.split('.'); p[0] = p[0].replace(/\B(?=(\d{3})+(?!\d))/g, ','); s = p.join('.'); }
      return s;
    };
  }
  // small seeded decaying shake
  function shake(tl, el, t, amp, steps, seed) {
    var r = prng(seed || 7), n = steps || 5, d = 0.2 / n;
    for (var i = 0; i < n; i++) { var k = 1 - i / n; tl.set(el, { x: (r() - 0.5) * 2 * amp * k, y: (r() - 0.5) * 2 * amp * k }, Q(t + i * d)); }
    tl.set(el, { x: 0, y: 0 }, Q(t + n * d));
  }
  // caret blink between a and b (2 frames on / ... ) as discrete sets
  function blink(tl, el, a, b, on) {
    var v = on ? 1 : 0;
    for (var t = a; t < b - 0.05; t += 0.27, v = 1 - v) tl.set(el, { opacity: v }, Q(t));
  }
  // the whole page's camera can be pushed slowly while a hero holds (drift, never an entrance)
  function hold(tl, el, t0, t1, k) {
    if (t1 - t0 < 0.4) return;
    ft(tl, el, { scale: 1 }, { scale: k || 1.025, duration: t1 - t0, ease: E('drift') }, t0);
  }

  root.RRK = { __core: true, FPS: FPS, E: E, Q: Q, F: F, prng: prng, curve: curve, one: one, all: all, ft: ft, life: life,
    heroIn: heroIn, heroOut: heroOut, draw: draw, count: count, fmtNum: fmtNum, shake: shake, blink: blink, hold: hold };
})(window);
