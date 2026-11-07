// Shared sourdough maths for the calculator and the guide.
// One source of truth so the two pages can never disagree.
(function (root) {
  'use strict';

  // Levain build: starter : flour : water, plus a margin for what sticks to
  // the jar and spoon. Change these to change the guide's levain step.
  const LEVAIN_BUILD = { starter: 1, flour: 2, water: 2, margin: 0.10 };

  // ── One bowl ─────────────────────────────────────────────────────────────
  // All percentages are of TOTAL flour (true baker's %), as fractions.
  // Levain is at 100% hydration: half flour, half water.
  //   T = target dough / (1 + hyd + salt + sum(mix-ins))   [levain cancels]
  // Ingredients round up (never too little dough); salt to 0.1 g.
  // Blend: whole wheat and rye are % of total flour; the levain's flour is
  // assumed white, so white makes up the rest of the added flour.
  function computeBowl({ loaves, lwt, oneBowl, hyd, salt, levainPct, mixins = [], blend = null }) {
    const mxTotal = mixins.reduce((s, m) => s + m.pct / 100, 0);
    const mult = oneBowl ? loaves : 1;
    const T = (lwt * mult) / (1 + hyd + salt + mxTotal);

    const levain = Math.ceil(T * levainPct);
    const water  = Math.ceil(T * hyd - T * levainPct / 2);
    const saltG  = Math.round(T * salt * 10) / 10;
    const flour  = Math.ceil(T * (1 - levainPct / 2));
    const mixG   = mixins.map(m => ({ name: m.name, g: Math.ceil(T * m.pct / 100) }));

    let split = null;
    if (blend) {
      const ww  = Math.round(T * blend.ww / 100);
      const rye = Math.round(T * blend.rye / 100);
      split = { white: flour - ww - rye, ww, rye };
    }
    const total = levain + water + saltG + flour + mixG.reduce((s, m) => s + m.g, 0);
    return { levain, water, salt: saltG, flour, totalFlour: Math.ceil(T), mixins: mixG, split,
             totalDough: Math.round(total) };
  }

  // ── Levain build for a given amount of ripe levain ──────────────────────
  function levainBuild(needed) {
    const B = LEVAIN_BUILD, parts = B.starter + B.flour + B.water;
    const unit = needed * (1 + B.margin) / parts;
    const starter = Math.ceil(unit * B.starter);
    const flour   = Math.ceil(unit * B.flour);
    const water   = Math.ceil(unit * B.water);
    return { needed, starter, flour, water, total: starter + flour + water,
             ratio: `${B.starter}:${B.flour}:${B.water}` };
  }

  // ── A whole recipe (all bowls) ──────────────────────────────────────────
  // recipe = { type, hyd, salt, blend|null, bowls:[{name, loaves, lwt, oneBowl, levainPct, mixins}] }
  // hyd, salt, levainPct are fractions; mix-in pct and blend are percentages.
  function computeRecipe(recipe) {
    const bowls = recipe.bowls.map(b => {
      const r = computeBowl({ loaves: b.loaves, lwt: b.lwt, oneBowl: b.oneBowl, hyd: recipe.hyd,
                              salt: recipe.salt, levainPct: b.levainPct, mixins: b.mixins, blend: recipe.blend });
      const factor = b.oneBowl ? 1 : b.loaves;   // per-loaf bowls are mixed once per loaf
      return Object.assign({}, b, { result: r, factor });
    });
    const levainNeeded = bowls.reduce((s, b) => s + b.result.levain * b.factor, 0);
    return { recipe, bowls, levainNeeded, build: levainBuild(levainNeeded) };
  }

  // ── Passing a recipe to the guide in the URL ────────────────────────────
  function encodeRecipe(recipe) {
    const compact = {
      t: recipe.type, h: +(recipe.hyd * 100).toFixed(1), s: +(recipe.salt * 100).toFixed(2),
      f: recipe.blend ? [recipe.blend.w, recipe.blend.ww, recipe.blend.rye] : undefined,
      b: recipe.bowls.map(b => [b.name, b.loaves, b.lwt, b.oneBowl ? 1 : 0, +(b.levainPct * 100).toFixed(1),
                                b.mixins.map(m => [m.name, m.pct])]),
    };
    return 'r=' + encodeURIComponent(JSON.stringify(compact));
  }

  function num(v, d) { const n = parseFloat(v); return isFinite(n) && n > 0 ? n : d; }

  function decodeRecipe(search) {
    const p = new URLSearchParams(search);
    if (p.has('r')) {
      try {
        const c = JSON.parse(p.get('r'));
        const type = c.t === 'baguette' ? 'baguette' : 'loaf';
        return {
          type, hyd: num(c.h, 70) / 100, salt: num(c.s, 2) / 100,
          blend: Array.isArray(c.f) ? { w: +c.f[0] || 0, ww: +c.f[1] || 0, rye: +c.f[2] || 0 } : null,
          bowls: (c.b || []).map((b, i) => ({
            name: String(b[0] || `Bowl ${i + 1}`), loaves: Math.max(1, Math.round(num(b[1], 1))),
            lwt: num(b[2], type === 'baguette' ? 400 : 950), oneBowl: !!b[3], levainPct: num(b[4], 15) / 100,
            mixins: (b[5] || []).map(m => ({ name: String(m[0] || 'Mix-in'), pct: +m[1] || 0 })),
          })),
        };
      } catch (e) { return null; }
    }
    // Older guide links carried computed numbers for one bowl; rebuild the recipe from them.
    if (p.has('levain') && p.has('totalFlour') && p.has('lwt')) {
      const type = p.get('type') === 'baguette' ? 'baguette' : 'loaf';
      const tf = num(p.get('totalFlour'), 0);
      return {
        type, hyd: num(p.get('hyd_pct'), 70) / 100, salt: tf ? num(p.get('salt'), 0) / tf || 0.02 : 0.02, blend: null,
        bowls: [{ name: p.get('bowl') || 'Bowl 1', loaves: Math.max(1, parseInt(p.get('loaves')) || 1),
                  lwt: num(p.get('lwt'), 950), oneBowl: p.get('onebowl') === '1',
                  levainPct: tf ? Math.round(num(p.get('levain'), 0) / tf * 100) / 100 : 0.15, mixins: [] }],
      };
    }
    return null;
  }

  // Default recipes shown when the guide is opened without a link
  function defaultRecipe(type) {
    return type === 'baguette'
      ? { type, hyd: 0.70, salt: 0.02, blend: null, bowls: [{ name: 'Baguettes', loaves: 2, lwt: 400, oneBowl: true, levainPct: 0.15, mixins: [] }] }
      : { type, hyd: 0.70, salt: 0.02, blend: null, bowls: [{ name: 'Loaf', loaves: 1, lwt: 950, oneBowl: true, levainPct: 0.15, mixins: [] }] };
  }

  // Grams for display: whole grams with thousands separators; salt to 0.1 g
  function fmt(g, isSalt) {
    if (isSalt) return (Math.round(g * 10) / 10).toFixed(1);
    return (Math.ceil(g - 1e-9) || 0).toLocaleString('en-AU');
  }

  root.Sourdough = { LEVAIN_BUILD, computeBowl, levainBuild, computeRecipe, encodeRecipe, decodeRecipe, defaultRecipe, fmt };
})(typeof window !== 'undefined' ? window : globalThis);
