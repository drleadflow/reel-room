/* kit_ui.js: typer, checklist, progress, odometer, pill, receipt (RRK animators). Markup comes from comps_ui.py.
 * The typer's pill <-> bar clip, per-character typing and SENT/DONE label states are adapted from reel-kit
 * fx/prompt-bar (Copyright (c) 2026 Justyn Berkovits, MIT License, see THIRD_PARTY_NOTICES.md). */
(function (K) {
  'use strict';
  var E = K.E, Q = K.Q, ft = K.ft, one = K.one, all = K.all;

  // ---- 1. typer: pill opens to a bar, types, sends, shows the result, closes back to the pill
  K.typer = function (tl, sel, c) {
    var r = document.querySelector(sel); if (!r) return;
    var shell = one(r, '.ty-shell'), card = one(r, '.ty-card'), W = c.w;
    var PILL = 'inset(0px ' + (W - 148) + 'px 0px 0px round 74px)', FULL = 'inset(0px 0px 0px 0px round 74px)';
    K.life(tl, r, c.t_in, c.out + 0.3);
    gsap.set(card, { clipPath: PILL });
    gsap.set(all(r, '.ty-text .c'), { display: 'none' });
    gsap.set([one(r, '.ty-lab .l1'), one(r, '.ty-lab .l2')], { yPercent: 110 });
    gsap.set(one(r, '.ty-done'), { yPercent: 110 });
    gsap.set(one(r, '.ty-line'), { scaleX: 0 });
    gsap.set([one(r, '.ty-ring'), one(r, '.ty-check')], { autoAlpha: 0 });
    gsap.set(one(r, '.ty-caret'), { opacity: 0 });
    // in: the pill pops (blur + scale + rise), then opens into the bar
    ft(tl, shell, { y: 34, scale: 0.86, filter: 'blur(12px)' }, { y: 0, scale: 1, filter: 'blur(0px)', duration: 0.4, ease: E('snap') }, c.t_in);
    ft(tl, one(r, '.k-spark'), { rotation: -90, scale: 0.4 }, { rotation: 0, scale: 1, duration: 0.5, ease: E('pop') }, c.t_in + 0.04);
    ft(tl, card, { clipPath: PILL }, { clipPath: FULL, duration: 0.46, ease: E('glide') }, c.t_in + 0.12);
    ft(tl, one(r, '.ty-lab .l0'), { yPercent: 110 }, { yPercent: 0, duration: 0.3, ease: E('snap') }, c.t_in + 0.24);
    // caret blinks while waiting, solid while typing
    K.blink(tl, one(r, '.ty-caret'), c.t_in + 0.3, c.ty0, true);
    tl.set(one(r, '.ty-caret'), { opacity: 1 }, Q(c.ty0));
    var ch = all(r, '.ty-text .c'), dt = (c.ty1 - c.ty0) / Math.max(1, ch.length);
    for (var i = 0; i < ch.length; i++) tl.set(ch[i], { display: 'inline' }, Q(c.ty0 + i * dt));
    K.blink(tl, one(r, '.ty-caret'), c.ty1 + 0.2, c.send, false);
    tl.set(one(r, '.ty-caret'), { opacity: 0 }, Q(c.send));
    // send: press, the arrow leaves, a ring spins, SENT
    tl.to(one(r, '.ty-send'), { scale: 0.84, duration: 0.07, ease: E('exit') }, Q(c.send));
    tl.to(one(r, '.ty-send'), { scale: 1, duration: 0.34, ease: E('pop') }, Q(c.send + 0.07));
    tl.to(one(r, '.ty-arrow'), { y: -70, autoAlpha: 0, duration: 0.16, ease: E('exit') }, Q(c.send + 0.02));
    var END = c.done || (c.out + 0.1);
    ft(tl, one(r, '.ty-ring'), { autoAlpha: 0, scale: 0.4 }, { autoAlpha: 1, scale: 1, duration: 0.24, ease: E('pop') }, c.send + 0.14);
    ft(tl, one(r, '.ty-ring path'), { rotation: 0 }, { rotation: 360 * Math.max(1, Math.round((END - c.send) / 0.55)), svgOrigin: '40 40',
      duration: Math.max(0.1, END - c.send - 0.14), ease: E('push') }, c.send + 0.14);
    tl.to(one(r, '.ty-lab .l0'), { yPercent: -110, duration: 0.22, ease: E('snap') }, Q(c.send));
    tl.to(one(r, '.ty-lab .l1'), { yPercent: 0, duration: 0.22, ease: E('snap') }, Q(c.send));
    tl.to(one(r, '.ty-field'), { opacity: 0.45, duration: 0.2, ease: E('settle') }, Q(c.send + 0.06));
    ft(tl, one(r, '.ty-line'), { scaleX: 0 }, { scaleX: 1, duration: Math.max(0.12, (c.done || c.out) - c.send - 0.1), ease: E('draw') }, c.send + 0.1);
    if (c.done) {   // the instruction rolls up as the result rolls in; the ring becomes a check; DONE
      tl.to(one(r, '.ty-field'), { yPercent: -120, duration: 0.3, ease: E('camera') }, Q(c.done - 0.04));
      ft(tl, one(r, '.ty-done'), { yPercent: 110, filter: 'blur(6px)' }, { yPercent: 0, filter: 'blur(0px)', duration: 0.34, ease: E('snap') }, c.done - 0.02);
      tl.to(one(r, '.ty-lab .l1'), { yPercent: -110, duration: 0.22, ease: E('camera') }, Q(c.done - 0.04));
      tl.to(one(r, '.ty-lab .l2'), { yPercent: 0, duration: 0.22, ease: E('camera') }, Q(c.done - 0.04));
      tl.to(one(r, '.ty-ring'), { autoAlpha: 0, scale: 0.5, duration: 0.1, ease: E('exit') }, Q(c.done - 0.04));
      tl.set(one(r, '.ty-check'), { autoAlpha: 1 }, Q(c.done));
      K.draw(tl, one(r, '.ty-check path'), c.done, 0.24, 'draw');
      ft(tl, one(r, '.ty-send'), { backgroundColor: getComputedStyle(r).getPropertyValue('--k-ink') },
        { backgroundColor: getComputedStyle(r).getPropertyValue('--k-acc'), duration: 0.2, ease: E('settle') }, c.done);
      ft(tl, card, { scale: 1 }, { scale: 1.035, duration: 0.09, ease: E('settle'), yoyo: true, repeat: 1 }, c.done);
    }
    // out: back to the pill, lifts away
    if (c.exit === 'pill') {
      ft(tl, card, { clipPath: FULL }, { clipPath: PILL, duration: 0.22, ease: E('exit') }, c.out);
      tl.to(shell, { y: -24, autoAlpha: 0, filter: 'blur(8px)', duration: 0.12, ease: E('exit') }, Q(c.out + 0.18));
    } else K.heroOut(tl, shell, c.out, c.exit);
  };

  // ---- 2. checklist: rows rise in, each ticks on its word
  K.checklist = function (tl, sel, c) {
    var r = document.querySelector(sel); if (!r) return;
    var card = one(r, '.ck-card'), rows = all(r, '.ck-row');
    K.life(tl, r, c.t_in, c.out + 0.2);
    gsap.set(all(r, '.ck-fill'), { scale: 0 });
    gsap.set(all(r, '.ck-hl'), { scaleX: 0 });
    gsap.set(all(r, '.ck-strike'), { scaleX: 0 });
    gsap.set(all(r, '.ck-ring svg path'), { strokeDasharray: 1, strokeDashoffset: 1 });
    K.heroIn(tl, card, c.t_in, { y: 50, scale: 0.94, blur: 14 });
    var ttl = one(r, '.ck-ttl span');
    if (ttl) ft(tl, ttl, { yPercent: 110 }, { yPercent: 0, duration: 0.36, ease: E('snap') }, c.t_in + 0.08);
    rows.forEach(function (row, i) {
      ft(tl, row, { autoAlpha: 0, x: -34, filter: 'blur(6px)' }, { autoAlpha: 1, x: 0, filter: 'blur(0px)', duration: 0.36, ease: E('snap') }, c.t_in + 0.14 + 0.07 * i);
      var t = c.ticks[i]; if (t === null || t === undefined) return;
      ft(tl, one(row, '.ck-fill'), { scale: 0 }, { scale: 1, duration: 0.3, ease: E('pop') }, t);
      tl.to(one(row, '.ck-ring svg path'), { strokeDashoffset: 0, duration: 0.2, ease: E('draw') }, Q(t + 0.06));
      ft(tl, one(row, '.ck-ring'), { scale: 1 }, { scale: 1.16, duration: 0.08, ease: E('settle'), yoyo: true, repeat: 1 }, t);
      if (c.style === 'strike') {
        tl.to(one(row, '.ck-strike'), { scaleX: 1, duration: 0.22, ease: E('draw') }, Q(t + 0.04));
        tl.to(one(row, '.ck-lbl span'), { opacity: 0.45, duration: 0.2, ease: E('settle') }, Q(t + 0.1));
      } else {
        ft(tl, one(row, '.ck-hl'), { scaleX: 0 }, { scaleX: 1, duration: 0.42, ease: E('glide') }, t + 0.02);
        ft(tl, one(row, '.ck-lbl span'), { x: 0 }, { x: 10, duration: 0.3, ease: E('snap') }, t);
        tl.to(one(row, '.ck-lbl span'), { color: getComputedStyle(r).getPropertyValue('--k-on'), duration: 0.2, ease: E('settle') }, Q(t));
      }
    });
    var last = Math.max.apply(null, c.ticks.filter(function (t) { return t !== null; }).concat([c.t_in]));
    if (last > c.t_in) ft(tl, card, { scale: 1 }, { scale: 1.025, duration: 0.1, ease: E('settle'), yoyo: true, repeat: 1 }, last + 0.08);
    K.heroOut(tl, card, c.out, c.exit);
  };

  // ---- 3. progress: fill + lead dot + rolling percentage
  K.progress = function (tl, sel, c) {
    var r = document.querySelector(sel); if (!r) return;
    var card = one(r, '.pg-card'), fill = one(r, '.pg-fill'), dot = one(r, '.pg-dot'), num = one(r, '.pg-num'), TW = c.tw;
    var notes = all(r, '.pg-note');
    K.life(tl, r, c.t_in, c.out + 0.2);
    function clip(v) { return 'inset(0% ' + (100 - v).toFixed(2) + '% 0% 0% round 999px)'; }
    gsap.set(fill, { clipPath: clip(c.start) });
    gsap.set(dot, { x: TW * c.start / 100 });
    gsap.set(notes, { autoAlpha: 0 });
    gsap.set(all(r, '.pg-mark'), { scaleY: 0 });
    K.heroIn(tl, card, c.t_in, { y: 40, scale: 0.95, blur: 12 });
    ft(tl, all(r, '.pg-mark'), { scaleY: 0 }, { scaleY: 1, duration: 0.3, ease: E('pop'), stagger: 0.05 }, c.t_in + 0.2);
    ft(tl, dot, { scale: 0 }, { scale: 1, duration: 0.3, ease: E('pop') }, c.t_in + 0.16);
    var prev = c.start;
    c.keys.forEach(function (k, i) {
      var t = k[0], v = k[1], d = 0.62;
      ft(tl, fill, { clipPath: clip(prev) }, { clipPath: clip(v), duration: d, ease: E('glide') }, t);
      ft(tl, dot, { x: TW * prev / 100 }, { x: TW * v / 100, duration: d, ease: E('glide') }, t);
      ft(tl, dot, { scale: 1.45 }, { scale: 1, duration: 0.36, ease: E('pop') }, t + 0.02);
      K.count(tl, num, t, d, prev, v, function (x) { return Math.round(x); }, 'glide');
      ft(tl, one(r, '.pg-pct'), { y: -8 }, { y: 0, duration: 0.3, ease: E('pop') }, t);
      if (notes[i]) {
        if (i > 0 && notes[i - 1]) tl.to(notes[i - 1], { autoAlpha: 0, yPercent: -60, duration: 0.14, ease: E('exit') }, Q(t));
        ft(tl, notes[i], { autoAlpha: 0, yPercent: 70, filter: 'blur(6px)' }, { autoAlpha: 1, yPercent: 0, filter: 'blur(0px)', duration: 0.34, ease: E('snap') }, t + 0.06);
      }
      if (v >= 100) {   // done: the bar turns the highlight colour and the card takes a beat
        tl.to(fill, { backgroundColor: getComputedStyle(r).getPropertyValue('--k-hl'), duration: 0.2, ease: E('settle') }, Q(t + d - 0.05));
        ft(tl, card, { scale: 1 }, { scale: 1.03, duration: 0.1, ease: E('settle'), yoyo: true, repeat: 1 }, t + d - 0.05);
      }
      prev = v;
    });
    K.heroOut(tl, card, c.out, c.exit);
  };

  // ---- 4. odometer: digit drums roll and lock
  K.odometer = function (tl, sel, c) {
    var r = document.querySelector(sel); if (!r) return;
    var shell = one(r, '.od-shell'), numEl = one(r, '.od-num'), cols = all(r, '.od-col'), lab = one(r, '.od-lab');
    K.life(tl, r, c.t_in, c.out + 0.2);
    var em = cols.length ? cols[0].getBoundingClientRect().height : 100;
    K.heroIn(tl, shell, c.t_in, { y: 40, scale: 0.9, blur: 14, dur: 0.4 });
    if (lab) ft(tl, lab, { yPercent: 110, autoAlpha: 0 }, { yPercent: 0, autoAlpha: 1, duration: 0.34, ease: E('snap') }, c.t_in + 0.06);
    var n = cols.length, roll = Math.max(0.3, c.land - c.t_in - 0.08);
    cols.forEach(function (col, i) {
      var strip = one(col, '.od-strip'), steps = +strip.dataset.steps;
      var end = c.land - (n - 1 - i) * 0.05;          // drums lock left to right, the last one on the word
      var dur = Math.max(0.25, end - (c.t_in + 0.08));
      ft(tl, strip, { y: 0 }, { y: -steps * em, duration: dur, ease: E('glide') }, c.t_in + 0.08);
      ft(tl, strip, { filter: 'blur(5px)' }, { filter: 'blur(0px)', duration: dur, ease: E('glide') }, c.t_in + 0.08);
    });
    ft(tl, numEl, { scale: 1.1 }, { scale: 1, duration: 0.24, ease: E('stamp') }, c.land);
    ft(tl, one(r, '.od-suf'), { autoAlpha: 0, x: -20 }, { autoAlpha: 1, x: 0, duration: 0.3, ease: E('snap') }, c.land + 0.04);
    K.shake(tl, numEl, c.land + 0.02, 5, 4, 3);
    K.hold(tl, shell, c.land + 0.3, c.out, 1.025);
    K.heroOut(tl, shell, c.out, c.exit);
  };

  // ---- 5. label pill: pop + burst; strike + tumble
  K.pill = function (tl, sel, c) {
    var r = document.querySelector(sel); if (!r) return;
    var shell = one(r, '.pl-shell'), body = one(r, '.pl-body'), rays = all(r, '.pl-burst path');
    K.life(tl, r, c.t_in, c.out + 0.1);
    if (body.scrollWidth > body.clientWidth + 1) body.style.fontSize = (parseFloat(getComputedStyle(body).fontSize) * body.clientWidth / body.scrollWidth * 0.97) + 'px';
    gsap.set(one(r, '.pl-strike'), { scaleX: 0 });
    gsap.set(rays, { strokeDasharray: '0.42 1.6', strokeDashoffset: 0.42, autoAlpha: 0 });
    ft(tl, body, { scale: 0.5, rotation: -7, filter: 'blur(10px)' }, { scale: 1, rotation: 0, filter: 'blur(0px)', duration: 0.42, ease: E('pop') }, c.t_in);
    ft(tl, one(r, '.pl-t'), { yPercent: 60 }, { yPercent: 0, duration: 0.34, ease: E('snap') }, c.t_in + 0.03);
    if (c.burst && rays.length) {   // rays shoot out from the pill and vanish
      tl.set(rays, { autoAlpha: 1 }, Q(c.t_in + 0.04));
      tl.to(rays, { strokeDashoffset: -1.02, duration: 0.4, ease: E('draw') }, Q(c.t_in + 0.04));
      tl.set(rays, { autoAlpha: 0 }, Q(c.t_in + 0.46));
    }
    if (c.strike) {
      tl.to(one(r, '.pl-strike'), { scaleX: 1, duration: 0.14, ease: E('draw') }, Q(c.strike));
      tl.to(body, { filter: 'saturate(0.35) brightness(0.92)', duration: 0.16, ease: E('settle') }, Q(c.strike + 0.06));
      ft(tl, body, { rotation: 0 }, { rotation: -3, duration: 0.08, ease: E('settle') }, c.strike + 0.06);
    }
    if (c.exit === 'tumble') {
      var t = (c.strike || c.out) + (c.strike ? 0.2 : 0);
      tl.to(shell, { y: -34, rotation: -6, duration: 0.09, ease: E('settle') }, Q(t));
      tl.to(shell, { y: 1500, rotation: 34, duration: 0.5, ease: E('fall') }, Q(t + 0.09));
    } else if (c.exit === 'pop') {
      tl.to(shell, { scale: 0, autoAlpha: 0, duration: 0.14, ease: E('exit') }, Q(c.out));
    } else K.heroOut(tl, shell, c.out, c.exit);
  };

  // ---- 6. receipt: prints top-down out of the slot (the paper edge feeds down as each row prints), totals, stamps
  K.receipt = function (tl, sel, c) {
    var r = document.querySelector(sel); if (!r) return;
    var slot = one(r, '.rc-slot'), feed = one(r, '.rc-feed'), win = one(r, '.rc-win'), teeth = one(r, '.rc-teeth');
    var paper = one(r, '.rc-paper'), rows = all(r, '.rc-row'), tot = one(r, '.rc-tot'), stamp = one(r, '.rc-stamp');
    K.life(tl, r, c.t_in, c.out + 0.2);
    var shown = 0;
    function feedTo(t, px, dur) {     // the paper edge (and its torn teeth) feeds down to px
      ft(tl, win, { height: shown }, { height: px, duration: dur, ease: E('snap') }, t);
      ft(tl, teeth, { y: shown }, { y: px, duration: dur, ease: E('snap') }, t);
      ft(tl, paper, { y: -10 }, { y: 0, duration: dur, ease: E('snap') }, t);
      shown = px;
    }
    gsap.set(win, { height: 0 });
    gsap.set(teeth, { y: 0 });
    gsap.set(rows.concat([tot]), { autoAlpha: 0 });
    if (stamp) gsap.set(stamp, { autoAlpha: 0 });
    K.heroIn(tl, slot, c.t_in, { y: -30, scale: 0.94, blur: 10, dur: 0.34 });
    ft(tl, teeth, { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.1, ease: E('settle') }, c.t_in + 0.1);
    feedTo(c.t_in + 0.1, c.head_h, 0.4);
    rows.forEach(function (row, i) {
      var t = c.prints[i];
      feedTo(t, c.head_h + (i + 1) * c.row_h, 0.26);
      ft(tl, row, { autoAlpha: 0, filter: 'blur(4px)', x: -8 }, { autoAlpha: 1, filter: 'blur(0px)', x: 0, duration: 0.22, ease: E('snap') }, t + 0.02);
      var was = one(row, '.rc-was');
      if (was) { gsap.set(was, { '--rcs': 0 }); tl.to(was, { '--rcs': 1, duration: 0.18, ease: E('draw') }, Q(t + 0.2)); }
    });
    feedTo(c.tot - 0.04, c.paper_h, 0.34);
    ft(tl, tot, { autoAlpha: 0, y: 10 }, { autoAlpha: 1, y: 0, duration: 0.24, ease: E('snap') }, c.tot);
    K.count(tl, one(r, '.rc-tn'), c.tot, 0.6, 0, c.total, K.fmtNum(c.dec), 'glide');
    if (stamp && c.stamp) {
      ft(tl, stamp, { autoAlpha: 0, scale: 2.3, rotation: -4, filter: 'blur(16px)' },
        { autoAlpha: 1, scale: 1, rotation: -11, filter: 'blur(0px)', duration: 0.2, ease: E('stamp') }, c.stamp);
      K.shake(tl, feed, c.stamp + 0.19, 7, 5, 11);
    }
    K.heroOut(tl, feed, c.out, c.exit);
    K.heroOut(tl, slot, c.out + 0.06, c.exit);
  };
})(window.RRK);
