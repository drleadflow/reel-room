/* kit_pip.js: head bubble (RRK animator). Markup + per-frame keys: comps_pip.py.
 * The move layer, the mask circle, the ring and the shadow are written once per frame from the planned rows
 * ([frame, s, tx, ty, mx, my, r, a]) as tl.set calls: seek-safe, no overlapping tweens on the same property. */
(function (K) {
  'use strict';
  var E = K.E, Q = K.Q, ft = K.ft, one = K.one, FPS = K.FPS;

  K.bubble = function (tl, sel, c) {
    var r = document.querySelector(sel); if (!r) return;
    var mv = one(r, '.hb-move'), mask = one(r, '.hb-mask'), ring = one(r, '.hb-ring'), shd = one(r, '.hb-shadow');
    var lab = one(r, '.hb-label'), w0 = c.rows[0];
    K.life(tl, r, c.t_in, c.end);
    gsap.set(mv, { transformOrigin: '0px 0px', x: 0, y: 0, scale: 1 });
    gsap.set(mask, { clipPath: 'circle(' + w0[6] + 'px at ' + w0[4] + 'px ' + w0[5] + 'px)' });
    gsap.set([ring, shd].filter(Boolean), { autoAlpha: 0 });
    c.rows.forEach(function (w) {
      var t = Math.max(0, (w[0] - 0.5) / FPS), s = w[1], R = w[6], a = w[7];
      tl.set(mv, { x: w[2], y: w[3], scale: s }, t);
      tl.set(mask, { clipPath: 'circle(' + R + 'px at ' + w[4] + 'px ' + w[5] + 'px)' }, t);
      if (shd) tl.set(shd, { left: w[4] - R, top: w[5] - R, width: 2 * R, height: 2 * R, autoAlpha: a }, t);
      if (ring) {
        var bw = c.ring / s, rr = R + c.gap / s;
        tl.set(ring, { left: w[4] - rr - bw, top: w[5] - rr - bw, width: 2 * rr, height: 2 * rr, borderWidth: bw, autoAlpha: a }, t);
      }
    });
    if (lab) {
      gsap.set(lab, { autoAlpha: 0, xPercent: -50 });
      ft(tl, lab, { autoAlpha: 0, y: 14, scale: 0.92 }, { autoAlpha: 1, y: 0, scale: 1, duration: 0.3, ease: E('pop') }, c.lab_in);
      tl.to(lab, { autoAlpha: 0, y: -8, duration: 0.12, ease: E('exit') }, Q(c.lab_out));
    }
  };
})(window.RRK);
