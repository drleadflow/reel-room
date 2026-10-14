/* kit_fx.js: comment -> DM, stepper, annotate, phone, before/after, spotlight (RRK animators). Markup: comps_fx.py.
 * The comment field flow (types the keyword on the word, posts, heart) is adapted from reel-kit fx/comment-cta
 * (Copyright (c) 2026 Justyn Berkovits, MIT License, see THIRD_PARTY_NOTICES.md). */
(function (K) {
  'use strict';
  var E = K.E, Q = K.Q, ft = K.ft, one = K.one, all = K.all, FPS = K.FPS;
  function tok(r, n) { return getComputedStyle(r).getPropertyValue(n).trim(); }

  // ---- 7. comment -> DM
  K.comment = function (tl, sel, c) {
    var r = document.querySelector(sel); if (!r) return;
    var field = one(r, '.cm-field'), dm = one(r, '.cm-dm'), dots = all(r, '.cm-dots i');
    K.life(tl, r, c.t_in, c.out + 0.2);
    gsap.set(all(r, '.cm-typed .c'), { display: 'none' });
    gsap.set([one(r, '.cm-meta'), one(r, '.cm-post'), one(r, '.cm-heart'), dm, one(r, '.cm-dots'), one(r, '.cm-bub'),
      one(r, '.cm-link'), one(r, '.cm-seen'), one(r, '.cm-caret')], { autoAlpha: 0 });
    K.heroIn(tl, field, c.t_in, { y: 46, scale: 0.94, blur: 12 });
    ft(tl, one(r, '.cm-ph'), { x: 14, autoAlpha: 0 }, { x: 0, autoAlpha: 1, duration: 0.3, ease: E('snap') }, c.t_in + 0.1);
    K.blink(tl, one(r, '.cm-caret'), c.t_in + 0.2, c.ty0, true);
    tl.set(one(r, '.cm-ph'), { autoAlpha: 0 }, Q(c.ty0));
    tl.set(one(r, '.cm-caret'), { autoAlpha: 1, opacity: 1 }, Q(c.ty0));
    var ch = all(r, '.cm-typed .c'), dt = (c.ty1 - c.ty0) / Math.max(1, ch.length);
    for (var i = 0; i < ch.length; i++) tl.set(ch[i], { display: 'inline' }, Q(c.ty0 + i * dt));
    ft(tl, one(r, '.cm-post'), { autoAlpha: 0, x: 16 }, { autoAlpha: 1, x: 0, duration: 0.24, ease: E('snap') }, c.ty0 + 0.05);
    // post: the button presses and goes, the comment settles, a heart pops
    tl.to(one(r, '.cm-post'), { scale: 0.86, duration: 0.07, ease: E('exit') }, Q(c.post));
    tl.to(one(r, '.cm-post'), { autoAlpha: 0, scale: 0.6, duration: 0.14, ease: E('exit') }, Q(c.post + 0.08));
    tl.set(one(r, '.cm-caret'), { autoAlpha: 0 }, Q(c.post));
    ft(tl, one(r, '.cm-txt'), { y: 0 }, { y: 14, duration: 0.3, ease: E('snap') }, c.post + 0.06);
    ft(tl, one(r, '.cm-meta'), { autoAlpha: 0, y: -10 }, { autoAlpha: 1, y: 0, duration: 0.3, ease: E('snap') }, c.post + 0.06);
    ft(tl, one(r, '.cm-heart'), { autoAlpha: 0, scale: 0.3 }, { autoAlpha: 1, scale: 1, duration: 0.36, ease: E('pop') }, c.post + 0.2);
    tl.to(one(r, '.cm-hl'), { fill: tok(r, '--k-acc'), stroke: tok(r, '--k-acc'), duration: 0.12, ease: E('settle') }, Q(c.post + 0.34));
    ft(tl, one(r, '.cm-heart'), { scale: 1.4 }, { scale: 1, duration: 0.3, ease: E('pop') }, c.post + 0.34);
    // the DM card lands, typing dots bounce, the message and the link card pop in
    tl.to(field, { scale: 0.94, y: -10, opacity: 0.55, duration: 0.3, ease: E('camera') }, Q(c.dm));
    ft(tl, dm, { autoAlpha: 0, y: 120, scale: 0.92, filter: 'blur(14px)' }, { autoAlpha: 1, y: 0, scale: 1, filter: 'blur(0px)', duration: 0.46, ease: E('land') }, c.dm);
    tl.set(one(r, '.cm-dots'), { autoAlpha: 1 }, Q(c.dm + 0.2));
    dots.forEach(function (d, j) {
      for (var t = c.dm + 0.2 + j * 0.07; t < c.msg - 0.08; t += 0.28) {
        tl.to(d, { y: -9, duration: 0.12, ease: E('settle') }, Q(t));
        tl.to(d, { y: 0, duration: 0.12, ease: E('drift') }, Q(t + 0.13));
      }
    });
    tl.set(one(r, '.cm-dots'), { autoAlpha: 0 }, Q(c.msg));
    ft(tl, one(r, '.cm-bub'), { autoAlpha: 0, scale: 0.6, x: -30 }, { autoAlpha: 1, scale: 1, x: 0, duration: 0.36, ease: E('pop') }, c.msg);
    ft(tl, one(r, '.cm-link'), { autoAlpha: 0, scale: 0.7, y: 24 }, { autoAlpha: 1, scale: 1, y: 0, duration: 0.4, ease: E('land') }, c.link);
    ft(tl, one(r, '.cm-kw'), { scale: 1.6, filter: 'blur(8px)' }, { scale: 1, filter: 'blur(0px)', duration: 0.24, ease: E('stamp') }, c.link + 0.16);
    ft(tl, one(r, '.cm-seen'), { autoAlpha: 0, y: 8 }, { autoAlpha: 1, y: 0, duration: 0.3, ease: E('snap') }, c.link + 0.55);
    K.heroOut(tl, field, c.out, c.exit);
    K.heroOut(tl, dm, c.out + 0.05, c.exit);
  };

  // ---- 8. stepper: list (side column) or bar (segmented HUD)
  K.stepper = function (tl, sel, c) {
    var r = document.querySelector(sel); if (!r) return;
    var onacc = tok(r, '--k-onacc'), sub = tok(r, '--k-sub'), ink = tok(r, '--k-on');
    K.life(tl, r, c.t_in, c.out + 0.2);
    if (c.layout === 'bar') {
      var bar = one(r, '.st-bar'), segs = all(r, '.st-seg i'), labs = all(r, '.st-cur'), roll = one(r, '.st-roll');
      var em = one(r, '.st-n').getBoundingClientRect().height;
      gsap.set(segs, { scaleX: 0 });
      gsap.set(labs, { autoAlpha: 0 });
      K.heroIn(tl, bar, c.t_in, { y: -30, scale: 0.96, blur: 10 });
      ft(tl, all(r, '.st-seg'), { scaleX: 0 }, { scaleX: 1, duration: 0.36, ease: E('glide'), stagger: 0.05 }, c.t_in + 0.1);
      var prev = -1;
      c.acts.forEach(function (t, i) {
        if (t === null) return;
        ft(tl, segs[i], { scaleX: 0 }, { scaleX: 1, duration: 0.5, ease: E('glide') }, t);
        if (prev >= 0) {
          tl.to(labs[prev], { autoAlpha: 0, yPercent: -80, duration: 0.14, ease: E('exit') }, Q(t));
          tl.to(segs[prev], { opacity: 0.38, duration: 0.2, ease: E('settle') }, Q(t));
        }
        ft(tl, labs[i], { autoAlpha: 0, yPercent: 90, filter: 'blur(6px)' }, { autoAlpha: 1, yPercent: 0, filter: 'blur(0px)', duration: 0.36, ease: E('snap') }, t + 0.04);
        ft(tl, roll, { y: -Math.max(0, prev) * em }, { y: -i * em, duration: 0.4, ease: E('snap') }, t);
        prev = i;
      });
      K.heroOut(tl, bar, c.out, c.exit);
      return;
    }
    var rows = all(r, '.st-row');
    gsap.set(all(r, '.st-bg'), { scaleX: 0 });
    gsap.set(all(r, '.st-num svg path'), { strokeDasharray: 1, strokeDashoffset: 1 });
    var card = one(r, '.st-card'), ttl = one(r, '.st-ttl'), r0 = c.t_in;
    if (card) { K.heroIn(tl, card, c.t_in, { x: -50, y: 0, scale: 0.95, blur: 12 }); r0 = c.t_in + 0.1; }
    if (ttl) ft(tl, ttl, { autoAlpha: 0, yPercent: 60 }, { autoAlpha: 1, yPercent: 0, duration: 0.34, ease: E('snap') }, c.t_in + 0.08);
    ft(tl, rows, { autoAlpha: 0, x: -70, filter: 'blur(10px)' }, { autoAlpha: 1, x: 0, filter: 'blur(0px)', duration: 0.46, ease: E('snap'), stagger: 0.07 }, r0);
    var last = -1;
    c.acts.forEach(function (t, i) {
      if (t === null) return;
      var row = rows[i];
      if (last >= 0) {    // the previous step is done: pill empties, the number becomes a check
        var p = rows[last];
        tl.to(one(p, '.st-bg'), { scaleX: 0, duration: 0.22, ease: E('exit') }, Q(t - 0.04));
        tl.to([one(p, '.st-l'), one(p, '.st-num')], { color: sub, borderColor: tok(r, '--k-faint'), duration: 0.18, ease: E('settle') }, Q(t));
        tl.to(one(p, '.st-num span'), { autoAlpha: 0, scale: 0.4, duration: 0.12, ease: E('exit') }, Q(t));
        tl.to(one(p, '.st-num svg path'), { strokeDashoffset: 0, duration: 0.22, ease: E('draw') }, Q(t + 0.08));
      }
      ft(tl, one(row, '.st-bg'), { scaleX: 0 }, { scaleX: 1, duration: 0.46, ease: E('glide') }, t);
      tl.to([one(row, '.st-l'), one(row, '.st-num')], { color: onacc, borderColor: onacc, duration: 0.18, ease: E('settle') }, Q(t + 0.04));
      ft(tl, row, { scale: 1 }, { scale: 1.07, duration: 0.11, ease: E('settle'), yoyo: true, repeat: 1 }, t);
      ft(tl, one(row, '.st-l'), { x: 0 }, { x: 8, duration: 0.3, ease: E('snap') }, t);
      last = i;
    });
    K.heroOut(tl, one(r, '.st-list'), c.out, c.exit);
  };

  // ---- 9. annotate: hand-drawn stroke draws on, handwritten label writes in
  K.annotate = function (tl, sel, c) {
    var r = document.querySelector(sel); if (!r) return;
    var paths = all(r, '.an-svg path'), chars = all(r, '.an-lab .c');
    K.life(tl, r, c.t_in, c.out + 0.25);
    var t = c.t_in, lab = c.lab === null ? null : c.lab;
    if (chars.length) {
      var lt = lab === null ? t : lab;
      ft(tl, chars, { autoAlpha: 0, yPercent: 40, rotation: -8, filter: 'blur(4px)' },
        { autoAlpha: 1, yPercent: 0, rotation: 0, filter: 'blur(0px)', duration: 0.26, ease: E('snap'), stagger: 0.035 }, lt);
      if (lab === null) t += Math.min(0.3, chars.length * 0.035);
    }
    var shaft = c.kind === 'circle' ? 0.5 : (c.kind === 'underline' ? 0.32 : 0.42);
    K.draw(tl, paths[0], t, shaft, 'draw');
    for (var i = 1; i < paths.length; i++) K.draw(tl, paths[i], t + (c.kind === 'arrow' ? shaft - 0.05 + (i - 1) * 0.05 : 0.12 * i), c.kind === 'arrow' ? 0.13 : 0.3, 'snap');
    if (c.exit === 'erase') {
      tl.to(paths, { strokeDashoffset: -1, duration: 0.2, ease: E('exit') }, Q(c.out));
      if (chars.length) tl.to(chars, { autoAlpha: 0, yPercent: -30, duration: 0.14, ease: E('exit'), stagger: 0.012 }, Q(c.out));
    } else K.heroOut(tl, r.firstElementChild, c.out, c.exit);
  };

  // ---- 10. phone: the frame-synced copy shrinks into a bezel over the brand ground, then grows back
  K.phone = function (tl, sel, c) {
    var r = document.querySelector(sel); if (!r) return;
    var stage = one(r, '.ph-stage'), vid = one(r, '.ph-vid'), bez = one(r, '.ph-bezel'), chrome = one(r, '.ph-chrome');
    var back = one(r, '.ph-back'), title = one(r, '.ph-title');
    K.life(tl, r, c.t_in, c.end);
    var k = c.k, X = c.cx - 540, Y = c.cy - 960, R = c.R, ring = c.ring, dur = 0.72;
    gsap.set(stage, { transformOrigin: '540px 960px' });
    gsap.set(bez, { '--ring': ring + 'px', borderRadius: 0 });
    if (chrome) gsap.set(chrome, { autoAlpha: 0 });
    if (title) gsap.set(title, { autoAlpha: 0 });
    ft(tl, stage, { scale: 1, x: 0, y: 0 }, { scale: k, x: X, y: Y, duration: dur, ease: E('camera') }, c.t_in);
    ft(tl, [vid, bez], { borderRadius: 0 }, { borderRadius: R, duration: dur * 0.8, ease: E('camera') }, c.t_in);
    ft(tl, back, { scale: 1.12 }, { scale: 1, duration: dur + 0.3, ease: E('settle') }, c.t_in);
    if (c.tilt) {
      ft(tl, stage, { rotationY: 0, rotationX: 0 }, { rotationY: -c.tilt, rotationX: c.tilt * 0.4, duration: dur, ease: E('camera') }, c.t_in + 0.1);
      var hold = c.back - (c.t_in + 0.1 + dur);
      if (hold > 0.4) ft(tl, stage, { rotationY: -c.tilt, rotationX: c.tilt * 0.4 }, { rotationY: c.tilt * 0.6, rotationX: -c.tilt * 0.2, duration: hold, ease: E('drift') }, c.t_in + 0.1 + dur);
      tl.to(stage, { rotationY: 0, rotationX: 0, duration: 0.5, ease: E('camera') }, Q(c.back));
    }
    if (chrome) ft(tl, chrome, { autoAlpha: 0, y: 30 }, { autoAlpha: 1, y: 0, duration: 0.4, ease: E('snap') }, c.t_in + dur - 0.12);
    if (title) ft(tl, title, { autoAlpha: 0, y: 30, filter: 'blur(8px)' }, { autoAlpha: 1, y: 0, filter: 'blur(0px)', duration: 0.42, ease: E('snap') }, c.t_in + dur - 0.2);
    // grow back: chrome and title leave first, then the copy fills the frame exactly as the plate
    if (chrome) tl.to(chrome, { autoAlpha: 0, duration: 0.12, ease: E('exit') }, Q(c.back - 0.06));
    if (title) tl.to(title, { autoAlpha: 0, y: -20, duration: 0.14, ease: E('exit') }, Q(c.back - 0.06));
    tl.to(stage, { scale: 1, x: 0, y: 0, duration: 0.58, ease: E('camera') }, Q(c.back));
    tl.to([vid, bez], { borderRadius: 0, duration: 0.5, ease: E('camera') }, Q(c.back + 0.06));
  };

  // ---- 11. before / after: tilted divider keyed per frame
  K.beforeAfter = function (tl, sel, c) {
    var r = document.querySelector(sel); if (!r) return;
    var bx = one(r, '.ba-box'), before = one(r, '.ba-before'), div = one(r, '.ba-div'), W = c.w, H = c.h;
    var tan = Math.tan(c.angle * Math.PI / 180) * H / 2;
    K.life(tl, r, c.t_in, c.out + 0.2);
    function poly(p) {               // share p of the width shows BEFORE (left side)
      var x = p * (W + 2 * tan) - tan;
      return 'polygon(0px 0px,' + (x + tan).toFixed(1) + 'px 0px,' + (x - tan).toFixed(1) + 'px ' + H + 'px,0px ' + H + 'px)';
    }
    function key(p) { var x = p * (W + 2 * tan) - tan; return { x: x }; }
    gsap.set(div, { rotation: c.angle, transformOrigin: '50% 50%' });
    function run(t0, dur, p0, p1, easeName) {
      var ez = K.curve(easeName), n = Math.max(1, Math.round(dur * FPS));
      for (var i = 0; i <= n; i++) {
        var p = p0 + (p1 - p0) * ez(i / n);
        tl.set(before, { clipPath: poly(p) }, Q(t0 + i / FPS));
        tl.set(div, key(p), Q(t0 + i / FPS));
      }
    }
    gsap.set(before, { clipPath: poly(1) });
    gsap.set(div, key(1));
    if (c.mode === 'card') K.heroIn(tl, bx, c.t_in, { y: 40, scale: 0.94, blur: 12 });
    ft(tl, one(r, '.ba-knob'), { scale: 0.3 }, { scale: 1, duration: 0.4, ease: E('pop') }, c.t_in + 0.08);
    ft(tl, all(r, '.ba-tag'), { autoAlpha: 0, y: -16 }, { autoAlpha: 1, y: 0, duration: 0.32, ease: E('snap'), stagger: 0.08 }, c.t_in + 0.2);
    run(c.t_in, 0.62, 1, c.rest, 'land');
    if (c.sweep) {
      run(c.sweep, 0.7, c.rest, c.end, 'whip');
      ft(tl, one(r, '.ba-knob'), { scale: 1 }, { scale: 1.18, duration: 0.12, ease: E('settle'), yoyo: true, repeat: 1 }, c.sweep);
      if (c.end <= 0.001) tl.to(div, { autoAlpha: 0, duration: 0.14, ease: E('exit') }, Q(c.sweep + 0.7));
    }
    if (c.mode === 'card') K.heroOut(tl, bx, c.out, 'blur');
    else tl.to(all(r, '.ba-tag'), { autoAlpha: 0, duration: 0.14, ease: E('exit') }, Q(c.out - 0.15));
  };

  // ---- 12. spotlight: a soft hole in a dim layer, glides between regions
  K.spotlight = function (tl, sel, c) {
    var r = document.querySelector(sel); if (!r) return;
    var hole = one(r, '.sl-hole'), ring = one(r, '.sl-ring'), k0 = c.keys[0];
    K.life(tl, r, c.t_in, c.out + 0.3);
    function g(k, grow) { grow = grow || 0; return { left: k[1] - grow, top: k[2] - grow, width: k[3] + 2 * grow, height: k[4] + 2 * grow }; }
    gsap.set([hole, ring], g(k0));
    var from = g(k0, 700); from.autoAlpha = 0;
    var to = g(k0); to.autoAlpha = 1; to.duration = 0.6; to.ease = E('camera');
    ft(tl, hole, from, to, c.t_in);
    if (ring) ft(tl, ring, Object.assign(g(k0, 40), { autoAlpha: 0 }), Object.assign(g(k0), { autoAlpha: 1, duration: 0.5, ease: E('snap') }), c.t_in + 0.25);
    function labAt(k) { return { left: k[1] + k[3] / 2, top: k[2] + k[4] + 22, xPercent: -50 }; }
    var labs = all(r, '.sl-lab');
    labs.forEach(function (l) { gsap.set(l, Object.assign(labAt(c.keys[+l.dataset.k] || k0), { autoAlpha: 0 })); });
    for (var i = 1; i < c.keys.length; i++) {
      var a = c.keys[i - 1], b = c.keys[i];
      ft(tl, hole, g(a), Object.assign(g(b), { duration: 0.55, ease: E('camera') }), b[0]);
      if (ring) ft(tl, ring, g(a), Object.assign(g(b), { duration: 0.55, ease: E('camera') }), b[0]);
    }
    labs.forEach(function (l) {
      var i = +l.dataset.k, k = c.keys[i] || k0, nxt = c.keys[i + 1];
      ft(tl, l, { autoAlpha: 0, y: 16, scale: 0.9 }, { autoAlpha: 1, y: 0, scale: 1, duration: 0.34, ease: E('pop') }, k[0] + (i ? 0.45 : 0.45));
      if (nxt) tl.to(l, { autoAlpha: 0, scale: 0.9, duration: 0.12, ease: E('exit') }, Q(nxt[0]));
      else tl.to(l, { autoAlpha: 0, duration: 0.12, ease: E('exit') }, Q(c.out));
    });
    var kl = c.keys[c.keys.length - 1];
    tl.to(hole, Object.assign(g(kl, 600), { autoAlpha: 0, duration: 0.32, ease: E('exit') }), Q(c.out));
    if (ring) tl.to(ring, { autoAlpha: 0, scale: 1.1, duration: 0.16, ease: E('exit') }, Q(c.out));
  };
})(window.RRK);
