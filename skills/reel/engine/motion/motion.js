/* motion.js: Reel Room Motion v2 runtime (GSAP 3, HyperFrames-safe, deterministic).
 *
 * Loaded by every composition after gsap.min.js. Exposes window.RRM.
 * Rules that make it seek-safe in a frame-by-frame renderer:
 *   - every event lands ON a frame: RRM.q(t) puts it half a frame early (same rule as the engine's snap())
 *   - no Math.random, no Date: variation comes from RRM.prng(seed)
 *   - entrances are fromTo(..., {immediateRender:false}); hidden states are set at build time with gsap.set
 *   - camera and transitions are keyed per frame with tl.set (RRM.keys), never as overlapping tweens
 * Easing is named by intent (RRM.EASE). Templates use the names, not raw curve strings; QA lints raw ones.
 *
 * The overscan cover() and the out/in frame easing of the transition keys are adapted from reel-kit
 * (fx/camera-transitions/fx.js), Copyright (c) 2026 Justyn Berkovits, MIT License. The full licence text is in
 * THIRD_PARTY_NOTICES.md at the repository root. Everything else here is Reel Room's own.
 */
(function (root) {
  'use strict';
  var FPS = 30, W = 1080, H = 1920;

  // ---- 1. intent-named eases -------------------------------------------------------------------
  var EASE = {
    snap: 'expo.out',            // anything arriving: fast in, long settle (the default entrance)
    glide: 'power4.out',         // big type and panels gliding into place
    land: 'back.out(1.4)',       // heavier cards landing with a small overshoot
    pop: 'back.out(2.2)',        // small pills, icons, stickers: overshoot ~10%
    stamp: 'power4.out',         // stamped words from oversize
    drift: 'sine.inOut',         // idle float, breathing
    camera: 'power2.inOut',      // focus pushes and pulls
    settle: 'power2.out',        // camera settling after a cut
    whip: 'expo.inOut',          // reveals and wipes
    draw: 'power2.inOut',        // strokes drawing on
    exit: 'power3.in',           // leaving: accelerate away
    fall: 'power2.in',           // gravity
    wobble: 'elastic.out(1,0.45)', // post-impact wobble
    push: 'none'                 // slow linear camera push (camera only, never an entrance)
  };
  // ---- 2. timing tokens (seconds; at 30 fps 0.1 s = 3 frames) ----------------------------------
  var DUR = { micro: 4 / 30, fast: 7 / 30, base: 12 / 30, slow: 24 / 30, camera: 27 / 30 };
  // visuals land a frame or two BEFORE the word they belong to
  var LEAD = { visual: 0.04, stamp: 0.03, push: 0.02, type: 0.05, none: 0 };

  // +1e-3 keeps it idempotent: a time already on a half frame ((f-0.5)/30, rounded to 5 decimals) stays on frame f
  function q(t) { return Math.max(0, (Math.round(t * FPS + 1e-3) - 0.5) / FPS); }
  function prng(seed) { var s = (seed >>> 0) || 1; return function () { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; }; }
  function $(s) { return typeof s === 'string' ? document.querySelector(s) : s; }
  function $$(s) { return typeof s === 'string' ? Array.prototype.slice.call(document.querySelectorAll(s)) : (s.length !== undefined ? Array.prototype.slice.call(s) : [s]); }
  var EVENTS = [];
  function log(t, kind, what) { EVENTS.push({ t: Math.round(t * 1000) / 1000, kind: kind, what: what || '' }); }

  // ---- 3. word-anchored timing: ordered search + named leads -----------------------------------
  var WORDS = [];   // [[start, end, text], ...] cut time
  function norm(s) { return String(s).toLowerCase().replace(/[’]/g, "'").replace(/[^a-z0-9%$']/g, ''); }
  function setWords(list) { WORDS = (list || []).map(function (w) { return Array.isArray(w) ? w : [w.start, w.end, w.text]; }); }
  function wordAt(text, after) {      // start of the first matching word at/after `after`, or null
    var want = norm(text), from = after || 0;
    for (var i = 0; i < WORDS.length; i++) if (WORDS[i][0] >= from - 0.001 && norm(WORDS[i][2]) === want) return WORDS[i][0];
    for (i = 0; i < WORDS.length; i++) if (WORDS[i][0] >= from - 0.001 && norm(WORDS[i][2]).indexOf(want) === 0) return WORDS[i][0];
    return null;
  }
  function wordSpan(text, after) {
    var t = wordAt(text, after);
    if (t === null) return null;
    for (var i = 0; i < WORDS.length; i++) if (Math.abs(WORDS[i][0] - t) < 0.0005) return [WORDS[i][0], WORDS[i][1]];
    return null;
  }
  // a cursor that walks the words in order: each beat searches from the previous one; a missing word falls back
  function cursor(start, lead) {
    var at = start || 0;
    return function (text, fallback, leadName) {
      var t = text ? wordAt(text, at) : null;
      if (t === null) t = (fallback !== undefined ? fallback : at);
      at = t + 0.001;
      return Math.max(0, t - LEAD[leadName || lead || 'visual']);
    };
  }

  // ---- 4. text helpers: split, masks, fit after fonts load ---------------------------------------
  function split(el, mode) {          // mode 'chars' (default) | 'words'; returns the spans
    el = $(el);
    if (el.dataset.rrmSplit) return $$(el.querySelectorAll(mode === 'words' ? '.rw' : '.rc'));
    var txt = el.textContent, out = [];
    el.textContent = '';
    if (mode === 'words') {
      txt.split(/(\s+)/).forEach(function (w) {
        if (!w) return;
        if (/^\s+$/.test(w)) { el.appendChild(document.createTextNode(' ')); return; }
        var s = document.createElement('span'); s.className = 'rw'; s.textContent = w; el.appendChild(s); out.push(s);
      });
    } else {
      Array.prototype.forEach.call(txt, function (c) {
        var s = document.createElement('span'); s.className = 'rc'; s.textContent = c === ' ' ? ' ' : c; el.appendChild(s); out.push(s);
      });
    }
    el.dataset.rrmSplit = mode || 'chars';
    return out;
  }
  function mask(el) {                 // wrap an element's content in an em-sized mask: lines push through it
    el = $(el);
    if (el.querySelector(':scope > .rm-mask')) return el.querySelector('.rm-in');
    var inner = document.createElement('span'); inner.className = 'rm-in';
    while (el.firstChild) inner.appendChild(el.firstChild);
    var m = document.createElement('span'); m.className = 'rm-mask'; m.appendChild(inner); el.appendChild(m);
    return inner;
  }
  function fit(el, maxW, minPx) {     // font-size in CSS is a MAX: only ever shrink to fit maxW
    el = $(el);
    if (!el.dataset.rrmMax) el.dataset.rrmMax = parseFloat(getComputedStyle(el).fontSize);
    var max = +el.dataset.rrmMax; el.style.fontSize = max + 'px';
    var r = document.createRange(); r.selectNodeContents(el);
    var w = r.getBoundingClientRect().width;
    if (w > maxW) el.style.fontSize = Math.max(minPx || 18, max * maxW / w * 0.995) + 'px';
  }
  function fitAll() { $$('[data-mfit]').forEach(function (el) { fit(el, +el.dataset.mfit); }); }

  // ---- 5. entrance / exit vocabulary -------------------------------------------------------------
  // Every entrance: fromTo, immediateRender false, at least two of {blur, scale, offset} for hero objects.
  function ft(tl, el, from, to, t) { to.immediateRender = false; tl.fromTo(el, from, to, q(t)); return t + (to.duration || 0); }
  var ENTER = {
    rise: function (tl, el, t, o) { o = o || {};      // up from below with blur
      return ft(tl, el, { autoAlpha: 0, y: o.y || 60, filter: 'blur(' + (o.blur || 10) + 'px)' },
        { autoAlpha: 1, y: 0, filter: 'blur(0px)', duration: o.dur || 0.36, ease: o.ease || EASE.snap }, t); },
    blurIn: function (tl, el, t, o) { o = o || {};    // the general "pro" entrance: blur + scale + offset
      return ft(tl, el, { autoAlpha: 0, x: o.x || 0, y: o.y === undefined ? 40 : o.y, scale: o.scale || 0.92, filter: 'blur(' + (o.blur || 14) + 'px)' },
        { autoAlpha: 1, x: 0, y: 0, scale: 1, filter: 'blur(0px)', duration: o.dur || 0.42, ease: o.ease || EASE.snap }, t); },
    pop: function (tl, el, t, o) { o = o || {};       // scale-pop with overshoot
      return ft(tl, el, { autoAlpha: 0, scale: o.from || 0.55, filter: 'blur(' + (o.blur || 6) + 'px)' },
        { autoAlpha: 1, scale: 1, filter: 'blur(0px)', duration: o.dur || 0.34, ease: o.ease || EASE.pop }, t); },
    stamp: function (tl, el, t, o) { o = o || {};     // slam in from oversize
      return ft(tl, el, { autoAlpha: 0, scale: o.from || 2.0, rotation: o.rot0 || 0, filter: 'blur(' + (o.blur || 20) + 'px)' },
        { autoAlpha: 1, scale: 1, rotation: o.rot || 0, filter: 'blur(0px)', duration: o.dur || 0.2, ease: o.ease || EASE.stamp }, t); },
    trackIn: function (tl, el, t, o) { o = o || {};   // tracks in from wide (scaleX, never letter-spacing)
      return ft(tl, el, { autoAlpha: 0, scaleX: o.from || 1.45, filter: 'blur(' + (o.blur || 6) + 'px)' },
        { autoAlpha: 1, scaleX: 1, filter: 'blur(0px)', duration: o.dur || 0.26, ease: o.ease || EASE.snap }, t); },
    wipe: function (tl, el, t, o) { o = o || {};      // clip wipe from one side
      var from = { left: 'inset(0 100% 0 0)', right: 'inset(0 0 0 100%)', up: 'inset(100% 0 0 0)', down: 'inset(0 0 100% 0)' }[o.dir || 'left'];
      tl.set(el, { autoAlpha: 1 }, q(t));
      return ft(tl, el, { clipPath: from }, { clipPath: 'inset(0% 0% 0% 0%)', duration: o.dur || 0.34, ease: o.ease || EASE.glide }, t); },
    drawOn: function (tl, el, t, o) { o = o || {};    // SVG stroke draws on (path needs pathLength="1")
      tl.set(el, { autoAlpha: 1, strokeDasharray: 1 }, q(t));
      return ft(tl, el, { strokeDashoffset: 1 }, { strokeDashoffset: 0, duration: o.dur || 0.5, ease: o.ease || EASE.draw }, t); },
    smear: function (tl, el, t, o) { o = o || {};     // fast horizontal smear in, 3-5 frames
      return ft(tl, el, { autoAlpha: 0, x: o.x || 140, filter: 'blur(' + (o.blur || 24) + 'px)' },
        { autoAlpha: 1, x: 0, filter: 'blur(0px)', duration: o.dur || 0.14, ease: o.ease || EASE.snap }, t); },
    drop: function (tl, el, t, o) { o = o || {};      // falls in, squashes on landing, wobbles to rest
      var fall = o.dur || 0.16;
      ft(tl, el, { autoAlpha: 0, y: o.y || -520, rotation: o.rot || -10, scaleX: 0.9, scaleY: 1.18, filter: 'blur(8px)' },
        { autoAlpha: 1, y: 0, rotation: (o.rot || -10) * 0.25, scaleX: 1, scaleY: 1, filter: 'blur(0px)', duration: fall, ease: EASE.fall }, t);
      tl.to(el, { scaleY: 0.8, scaleX: 1.14, transformOrigin: '50% 100%', duration: 0.06, ease: 'power1.out' }, q(t + fall));
      tl.to(el, { scaleY: 1, scaleX: 1, rotation: 0, duration: 0.34, ease: EASE.wobble }, q(t + fall + 0.06));
      return t + fall + 0.4; },
    maskPush: function (tl, el, t, o) { o = o || {};  // the line pushes up through its em mask
      var inner = mask(el); tl.set(el, { autoAlpha: 1 }, q(t));
      return ft(tl, inner, { yPercent: 110 }, { yPercent: 0, duration: o.dur || 0.32, ease: o.ease || EASE.snap }, t); },
    letters: function (tl, el, t, o) { o = o || {};   // letters rise out of a mask, staggered
      var chars = split(el, 'chars'); mask(el); tl.set(el, { autoAlpha: 1 }, q(t));
      ft(tl, chars, { yPercent: o.from || 110, rotation: o.rot || 6, filter: 'blur(' + (o.blur || 8) + 'px)' },
        { yPercent: 0, rotation: 0, filter: 'blur(0px)', duration: o.dur || 0.42, ease: o.ease || EASE.snap, stagger: o.stagger || 0.03 }, t);
      return t + (o.dur || 0.42) + chars.length * (o.stagger || 0.03); },
    letterStamp: function (tl, el, t, o) { o = o || {}; // each letter stamps from 1.38x, 2 frames apart
      var chars = split(el, 'chars'); tl.set(el, { autoAlpha: 1 }, q(t));
      ft(tl, chars, { autoAlpha: 0, scale: o.from || 1.38, yPercent: -6, transformOrigin: '50% 85%' },
        { autoAlpha: 1, scale: 1, yPercent: 0, duration: o.dur || 0.2, ease: EASE.stamp, stagger: o.stagger || 2 / 30 }, t);
      return t + (o.dur || 0.2) + chars.length * (o.stagger || 2 / 30); },
    grow: function (tl, el, t, o) { o = o || {};      // a caption grows into a headline (giant-caption growth)
      return ft(tl, el, { autoAlpha: 0, scale: o.from || 0.42, rotation: o.rot || 4, filter: 'blur(4px)' },
        { autoAlpha: 1, scale: 1, rotation: 0, filter: 'blur(0px)', duration: o.dur || 0.34, ease: o.ease || EASE.glide }, t); }
  };
  var EXIT = {
    cutOut: function (tl, el, t) { tl.set(el, { autoAlpha: 0 }, q(t)); return t; },
    sink: function (tl, el, t, o) { o = o || {};
      var inner = el.querySelector ? (el.querySelector('.rm-in') || el) : el;
      tl.to(inner, { yPercent: -110, duration: o.dur || 0.16, ease: EASE.exit }, q(t)); tl.set(el, { autoAlpha: 0 }, q(t + (o.dur || 0.16))); return t + (o.dur || 0.16); },
    scaleOut: function (tl, el, t, o) { o = o || {};
      tl.to(el, { scaleY: 0, duration: o.dur || 0.14, ease: EASE.exit }, q(t)); tl.set(el, { autoAlpha: 0 }, q(t + (o.dur || 0.14))); return t + (o.dur || 0.14); },
    fall: function (tl, el, t, o) { o = o || {};
      tl.to(el, { y: '-=40', duration: 0.08, ease: 'power2.out' }, q(t));
      tl.to(el, { y: 1500, rotation: o.rot || 24, duration: o.dur || 0.42, ease: EASE.fall }, q(t + 0.08)); return t + 0.5; },
    blurOut: function (tl, el, t, o) { o = o || {};
      tl.to(el, { autoAlpha: 0, scale: 1.06, filter: 'blur(10px)', duration: o.dur || 0.16, ease: EASE.exit }, q(t)); return t + (o.dur || 0.16); }
  };
  function enter(name, tl, el, t, o) { if (!ENTER[name]) throw new Error('RRM: unknown entrance ' + name); log(t, 'enter:' + name); return ENTER[name](tl, el, t, o); }
  function exit(name, tl, el, t, o) { if (!EXIT[name]) throw new Error('RRM: unknown exit ' + name); return EXIT[name](tl, el, t, o); }

  // caption entrance (kinetic captions): 'rise' for most words, 'stamp' for the payoff word, 'grow' for giant
  function capIn(tl, sel, t, kind) {
    var el = $(sel); if (!el) return;
    if (kind === 'stamp') return ft(tl, el, { scale: 1.42, y: 0, filter: 'blur(10px)' }, { scale: 1, filter: 'blur(0px)', duration: 0.2, ease: EASE.stamp }, t);
    if (kind === 'grow') return ft(tl, el, { scale: 0.5, rotation: 3, filter: 'blur(4px)' }, { scale: 1, rotation: 0, filter: 'blur(0px)', duration: 0.3, ease: EASE.glide }, t);
    return ft(tl, el, { y: 22, scale: 1.05, filter: 'blur(5px)' }, { y: 0, scale: 1, filter: 'blur(0px)', duration: 0.16, ease: EASE.snap }, t);
  }

  // ---- 6. per-frame keys (camera rig + transitions are planned in Python, applied here) ---------
  // rows: [[frame, v0, v1, ...], ...] for `fields`; only frames where something changes are listed.
  // fields understood: scale, x, y, rotation, blur (CSS blur px), bx/by (SVG directional blur on #mvMB),
  // r (iris radius px, with cx/cy), o (opacity)
  function keys(tl, sel, fields, rows, opt) {
    opt = opt || {};
    var el = $$(sel); if (!el.length) return;     // several layers can share one camera ('#mvCam,#mvCamB')
    rows.forEach(function (r) {
      var t = (r[0] - 0.5) / FPS, v = {}, bx = null, by = null;
      if (t < 0) t = 0;
      for (var i = 0; i < fields.length; i++) {
        var f = fields[i], val = r[i + 1];
        if (f === 'bx') bx = val; else if (f === 'by') by = val;
        else if (f === 'blur') v.filter = val > 0.3 ? 'blur(' + val.toFixed(1) + 'px)' : 'none';
        else if (f === 'o') v.autoAlpha = val;
        else if (f === 'r') { var cx = r[i + 2], cy = r[i + 3]; v.width = 2 * val; v.height = 2 * val; v.left = cx - val; v.top = cy - val; i += 2; }
        else v[f] = val;
      }
      if (bx !== null || by !== null) {
        var on = (bx || 0) > 0.3 || (by || 0) > 0.3;
        v.filter = on ? 'url(#' + (opt.filter || 'mvMB') + ')' : 'none';
        if (on) tl.set('#' + (opt.filter || 'mvMB') + 'g', { attr: { stdDeviation: (bx || 0).toFixed(1) + ' ' + (by || 0).toFixed(1) } }, t);
      }
      tl.set(el, v, t);
    });
  }

  // overscan: the smallest scale at which a frame moved by (x, y, rotation r deg) about (ox, oy) still covers a
  // w x h canvas (half a pixel of bleed). Adapted from reel-kit camera-transitions (MIT).
  function cover(x, y, r, ox, oy, w, h) {
    w = w || W; h = h || H;
    if (Math.abs(x) < 0.01 && Math.abs(y) < 0.01 && Math.abs(r || 0) < 0.001) return 1;
    var a = (r || 0) * Math.PI / 180, c = Math.cos(a), n = Math.sin(a), need = 1;
    [[-0.5, -0.5], [w + 0.5, -0.5], [-0.5, h + 0.5], [w + 0.5, h + 0.5]].forEach(function (p) {
      var dx = p[0] - ox - x, dy = p[1] - oy - y, u = c * dx + n * dy, v = -n * dx + c * dy;
      need = Math.max(need, u > 0 ? u / (w - ox) : -u / ox, v > 0 ? v / (h - oy) : -v / oy);
    });
    return need;
  }

  // ---- 7. physics + polish helpers ---------------------------------------------------------------
  function shake(tl, el, t, o) {      // seeded, decaying
    o = o || {}; var r = prng(o.seed || 7), n = o.steps || 6, amp = o.amp || 10, step = (o.dur || 0.24) / n;
    for (var i = 0; i < n; i++) { var k = 1 - i / n;
      tl.set(el, { x: (r() - 0.5) * 2 * amp * k, y: (r() - 0.5) * 2 * amp * k, rotation: (r() - 0.5) * (o.rot || 0.8) * k }, q(t + i * step)); }
    tl.set(el, { x: 0, y: 0, rotation: 0 }, q(t + n * step));
  }
  function squash(tl, el, t, o) {     // overshoot / squash settle on landing
    o = o || {};
    tl.to(el, { scaleY: o.k || 0.84, scaleX: 2 - (o.k || 0.84), transformOrigin: o.origin || '50% 100%', duration: 0.06, ease: 'power1.out' }, q(t));
    tl.to(el, { scaleY: 1, scaleX: 1, duration: 0.36, ease: EASE.wobble }, q(t + 0.06));
  }
  function flash(tl, t, o) {          // white (or brand) flash layer #mvFlash
    o = o || {}; var el = $(o.sel || '#mvFlash'); if (!el) return;
    tl.set(el, { autoAlpha: o.k || 0.85 }, q(t));
    tl.to(el, { autoAlpha: 0, duration: o.dur || 0.2, ease: 'power2.out' }, q(t + 1 / FPS));
  }
  function grain(tl, el, t0, t1, seed, every) {   // opt-in only (Reel Room default is no grain)
    var r = prng(seed || 9), step = (every || 2) / FPS;
    for (var t = t0; t < t1; t += step) tl.set(el, { backgroundPosition: Math.floor(r() * 320) + 'px ' + Math.floor(r() * 320) + 'px' }, q(t));
  }
  function glow(el, color) { el = $(el); if (el) el.style.textShadow = '0 0 22px ' + (color || 'currentColor') + ', 0 0 4px ' + (color || 'currentColor'); }

  root.RRM = {
    FPS: FPS, EASE: EASE, DUR: DUR, LEAD: LEAD, q: q, prng: prng, events: EVENTS, log: log,
    setWords: setWords, wordAt: wordAt, wordSpan: wordSpan, cursor: cursor,
    split: split, mask: mask, fit: fit, fitAll: fitAll,
    ENTER: ENTER, EXIT: EXIT, enter: enter, exit: exit, capIn: capIn,
    keys: keys, cover: cover, shake: shake, squash: squash, flash: flash, grain: grain, glow: glow
  };
})(window);
