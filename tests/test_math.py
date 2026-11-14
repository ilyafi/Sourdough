"""Randomised maths tests for sourdough-calculator.html.

Sets random recipes (loaf, baguette, focaccia; Simple and Advanced; flour
blends, olive oil, trays, mix-ins, per-bowl levain) on the real page, reads
the results table and checks it against an independent baker's-percentage
calculation.

Run:  python3 tests/test_math.py          (exit code 1 on any failure)
"""
import asyncio, json, math, random, sys
from playwright.async_api import async_playwright
from common import launch, PAGE

random.seed(42)
N_CASES = 300
fails = []

READ_TABLE = """() => {
  const out = {};
  document.querySelectorAll('.out-table tbody tr').forEach(r => {
    const l = r.querySelector('td.col-lbl'); if (!l) return;
    out[l.textContent.trim()] = [...r.querySelectorAll('td.val')].map(t => t.textContent.replace(/\\s*g$/,'').trim());
  });
  out._notes = [...document.querySelectorAll('.out-notes p')].map(p => p.textContent);
  return out;
}"""

TRAYS = {'p-20x20': 400, 'p-23x33': 759, 'p-28x38': 1064, 'p-33x46': 1518,
         'p-r24': math.pi * 144, 'p-r28': math.pi * 196}
THICK = {'thin': 0.8, 'medium': 1.1, 'thick': 1.4}
SIMPLE_HYD = {'loaf': 0.70, 'baguette': 0.70, 'focaccia': 0.75}

def num(v):
    v = v.replace(',', '').replace(' ', '').replace(' ', '')
    return 0.0 if v == '–' else float(v)

def random_case():
    """A random saved-state object plus what we expect it to mean."""
    typ = random.choice(['loaf', 'baguette', 'focaccia'])
    adv = random.random() < 0.5
    speed = random.randint(0, 2)
    hyd = random.randint(55, 110); salt = random.choice([1.5, 1.8, 2, 2.2, 2.5, 3]); glev = random.randint(5, 40)
    w = random.choice([100, 90, 80, 70, 60]); ww = random.choice([0, 100 - w]); rye = 100 - w - ww
    oil_on = random.random() < 0.6; oil = random.choice([2, 3, 4, 5, 8])
    bowls, exp_bowls = [], []
    for i in range(random.randint(1, 3)):
        count = random.randint(1, 6); one = random.random() < 0.7
        mixins = [{'name': f'mx{i}{k}', 'pct': str(random.choice([5, 10, 15, 22.5, 30]))} for k in range(random.randint(0, 2))]
        lev_on = adv and random.random() < 0.35; lev = random.randint(5, 40)
        b = {'name': f'B{i+1}', 'counts': {typ: str(count)}, 'oneBowl': one, 'mixins': mixins, 'lev': {'on': lev_on, 'pct': str(lev)}}
        if typ == 'focaccia':
            if random.random() < 0.7:
                sel = random.choice(list(TRAYS)); area = TRAYS[sel]
                b['tray'] = {'sel': sel}
            else:
                if random.random() < 0.5:
                    tw, tl = random.randint(15, 50), random.randint(15, 50); area = tw * tl
                    b['tray'] = {'sel': 'custom', 'shape': 'rect', 'w': str(tw), 'l': str(tl)}
                else:
                    d = random.randint(15, 40); area = math.pi * d * d / 4
                    b['tray'] = {'sel': 'custom', 'shape': 'round', 'd': str(d)}
            th = random.choice(['thin', 'medium', 'thick', 'custom'])
            g = THICK.get(th) or random.choice([0.6, 0.95, 1.25, 1.7])
            b['thick'] = th; b['thickCustom'] = str(g)
            W = max(1, round(area * g))
        else:
            W = random.choice([250, 400, 650, 950, 1200, random.randint(150, 3000)])
            b['weights'] = {typ: str(W)}
        bowls.append(b)
        exp_bowls.append(dict(W=W, n=count, one=one, mx=[float(m['pct']) / 100 for m in mixins], names=[m['name'] for m in mixins],
                              lev=(lev if lev_on else glev) / 100 if adv else [0.20, 0.15, 0.10][speed]))
    st = {'mode': 'advanced' if adv else 'simple', 'type': typ, 'speed': speed,
          'adv': {'hyd': {typ: str(hyd)}, 'salt': str(salt), 'levain': str(glev), 'blend': {'w': str(w), 'ww': str(ww), 'rye': str(rye)}},
          'oil': {'on': oil_on, 'pct': str(oil)}, 'bowls': bowls}
    exp = dict(type=typ, adv=adv, hyd=hyd / 100 if adv else SIMPLE_HYD[typ], salt=salt / 100 if adv else 0.02,
               oil=oil / 100 if (typ == 'focaccia' and oil_on) else 0, blend=(ww, rye) if adv and (ww or rye) else None, bowls=exp_bowls)
    return st, exp

def check(case, rows, exp):
    h, s, oil = exp['hyd'], exp['salt'], exp['oil']
    for col, eb in enumerate(exp['bowls']):
        c = f'{case} bowl{col+1}'
        g = lambda lbl: num(rows[lbl][col])
        mult = eb['n'] if eb['one'] else 1
        T = eb['W'] * mult / (1 + h + s + oil + sum(eb['mx']))
        lev = eb['lev']
        for lbl, e in [('Levain', T * lev), ('Water', T * h - T * lev / 2), ('Flour', T * (1 - lev / 2))]:
            if not (e - 0.001 <= g(lbl) < e + 1.001): fails.append(f'{c}: {lbl} {g(lbl)}, exact {e:.2f}')
        if abs(g('Salt') - T * s) > 0.051: fails.append(f'{c}: Salt {g("Salt")}, exact {T*s:.2f}')
        if oil:
            if not (T * oil - 0.001 <= g('Olive oil') < T * oil + 1.001): fails.append(f'{c}: Olive oil {g("Olive oil")}, exact {T*oil:.2f}')
        elif 'Olive oil' in rows: fails.append(f'{c}: Olive oil row shown without oil')
        for name, p in zip(eb['names'], eb['mx']):
            if not (T * p - 0.001 <= g(name) < T * p + 1.001): fails.append(f'{c}: {name} {g(name)}, exact {T*p:.2f}')
        comp = sum(g(k) for k in ('Levain', 'Water', 'Salt', 'Flour')) + (g('Olive oil') if oil else 0) + sum(g(n) for n in eb['names'])
        if abs(g('Total dough') - comp) > 0.51: fails.append(f'{c}: Total dough {g("Total dough")} != rows {comp:.1f}')
        target = eb['W'] * mult
        if not (target - 0.5 <= g('Total dough') <= target + 7): fails.append(f'{c}: Total dough {g("Total dough")} vs target {target}')
        if abs(g('Total flour (incl. levain)') - (g('Flour') + g('Levain') / 2)) > 1.5: fails.append(f'{c}: total flour mismatch')
        if exp['blend']:
            ww, rye = exp['blend']
            parts = {k: g(k) for k in ('White', 'Whole wheat', 'Rye') if k in rows}
            if abs(sum(parts.values()) - g('Flour')) > 0.01: fails.append(f'{c}: blend rows {parts} != Flour {g("Flour")}')
            for k, pct in (('Whole wheat', ww), ('Rye', rye)):
                if pct and abs(parts.get(k, 0) - T * pct / 100) > 0.51: fails.append(f'{c}: {k} {parts.get(k)}, expected {T*pct/100:.1f}')
        elif any(k in rows for k in ('Whole wheat', 'Rye')): fails.append(f'{c}: blend rows shown without a blend')
    if len(exp['bowls']) > 1:
        factors = [1 if eb['one'] else eb['n'] for eb in exp['bowls']]
        for lbl, vals in rows.items():
            if lbl.startswith('_'): continue
            tot = sum(num(v) * f for v, f in zip(vals[:-1], factors))
            if abs(tot - num(vals[-1])) > (0.15 if lbl == 'Salt' else 1.01): fails.append(f'{case}: All bowls {lbl} {vals[-1]} vs {tot}')
    if exp['type'] == 'focaccia' and not any('Tray oil' in n for n in rows['_notes']): fails.append(f'{case}: no tray-oil note')

async def main():
    async with async_playwright() as p:
        b, pg, errs = await launch(p)
        await pg.goto(PAGE)
        counts = {'loaf': 0, 'baguette': 0, 'focaccia': 0}
        for i in range(N_CASES):
            st, exp = random_case()
            counts[exp['type']] += 1
            await pg.evaluate(f"state = sanitize({json.dumps(st)}); renderAll(); calc();")
            rows = await pg.evaluate(READ_TABLE)
            check(f'case{i} ({exp["type"]}, {"adv" if exp["adv"] else "simple"})', rows, exp)
        await b.close()
    fails.extend(f'JS error: {e}' for e in errs)
    print(f'{N_CASES} random recipes ({counts["loaf"]} loaf, {counts["baguette"]} baguette, {counts["focaccia"]} focaccia): {len(fails)} failure(s)')
    for f in fails[:25]: print('  FAIL', f)
    return 1 if fails else 0

if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
