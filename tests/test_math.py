"""Randomised maths tests for sourdough-calculator.html.

Drives the real page in headless Chrome, sets random recipes in Simple and
Advanced mode, reads the results table and checks it against an independent
baker's-percentage calculation.

Run:  python3 tests/test_math.py          (exit code 1 on any failure)
"""
import asyncio, random, sys
from pathlib import Path
from playwright.async_api import async_playwright
from common import launch, PAGE

random.seed(42)
N_CASES = 120          # per mode
fails = []

READ_TABLE = """() => {
  const out = {};
  document.querySelectorAll('.out-table tbody tr').forEach(r => {
    const l = r.querySelector('td.col-lbl'); if (!l) return;
    out[l.textContent.trim()] = [...r.querySelectorAll('td.val')].map(t => t.textContent.replace(/\\s*g$/,'').trim());
  });
  return out;
}"""

def num(v):
    v = v.replace(',', '').replace(' ', '').replace('\u00a0', '')
    return 0.0 if v == '–' else float(v)

def expected(W, loaves, onebowl, h, s, lev, mx):
    mult = loaves if onebowl else 1
    T = W * mult / (1 + h + s + sum(mx))
    return dict(T=T, levain=T*lev, water=T*h - T*lev/2, salt=T*s, flour=T*(1-lev/2),
                mixins=[T*m for m in mx], target=W*mult)

def check_bowl(case, col, rows, exp, mx_names, h, s, lev):
    g = lambda lbl: num(rows[lbl][col])
    # Each ingredient rounded up from the exact value (salt to 0.1 g)
    for key, lbl in [('levain','Levain'), ('water','Water'), ('flour','Flour')]:
        if not (exp[key] - 0.001 <= g(lbl) < exp[key] + 1.001):
            fails.append(f'{case}: {lbl} shows {g(lbl)}, exact {exp[key]:.2f}')
    if abs(g('Salt') - exp['salt']) > 0.051:
        fails.append(f'{case}: Salt shows {g("Salt")}, exact {exp["salt"]:.2f}')
    for name, e in zip(mx_names, exp['mixins']):
        if not (e - 0.001 <= g(name) < e + 1.001):
            fails.append(f'{case}: {name} shows {g(name)}, exact {e:.2f}')
    # Total dough = sum of rows, and at or just over target
    comp = g('Levain') + g('Water') + g('Salt') + g('Flour') + sum(g(n) for n in mx_names)
    if abs(g('Total dough') - comp) > 0.51:
        fails.append(f'{case}: Total dough {g("Total dough")} != sum of rows {comp:.1f}')
    if not (exp['target'] - 0.5 <= g('Total dough') <= exp['target'] + 6):
        fails.append(f'{case}: Total dough {g("Total dough")} vs target {exp["target"]}')
    # Percentages recovered from the displayed grams (tolerance: rounding to 1 g)
    lv, wt, fl = g('Levain'), g('Water'), g('Flour')
    tf = fl + lv/2
    if abs(g('Total flour (incl. levain)') - tf) > 1.5:
        fails.append(f'{case}: Total flour {g("Total flour (incl. levain)")} vs flour+levain/2 {tf:.1f}')
    if abs((wt + lv/2) - h*tf) > 2:   fails.append(f'{case}: hydration off: {(wt+lv/2)/tf:.4f} vs {h}')
    if abs(g('Salt') - s*tf) > 0.15:  fails.append(f'{case}: salt off: {g("Salt")/tf:.4f} vs {s}')
    if abs(lv - lev*tf) > 1.5:        fails.append(f'{case}: levain off: {lv/tf:.4f} vs {lev}')

def check_all_bowls(case, rows, factors):
    """'All bowls' column = sum of each column scaled to its full bake."""
    for lbl, vals in rows.items():
        s = sum(num(v) * f for v, f in zip(vals[:-1], factors)); t = num(vals[-1])
        if abs(s - t) > (0.15 if lbl == 'Salt' else 1.01):
            fails.append(f'{case}: All bowls {lbl} = {t}, expected {s}')

async def set_val(pg, sel, v):
    await pg.evaluate("([s,v]) => { document.querySelector(s).value = v; }", [sel, str(v)])

async def simple_cases(pg):
    for i in range(N_CASES):
        await pg.goto(PAGE)
        step = random.randint(0, 2); lev = [0.20, 0.15, 0.10][step]
        await pg.evaluate(f"setStep({step})")
        if random.random() < 0.3: await pg.evaluate("setBreadType('baguette')")
        for _ in range(random.randint(0, 2)): await pg.evaluate("addBowl()")
        specs = []
        for bid in await pg.evaluate("bowls.map(b=>b.id)"):
            loaves = random.randint(1, 8)
            W = random.choice([250, 400, 650, 950, 1200, random.randint(150, 3000)])
            ob = random.random() < 0.7
            await set_val(pg, f'#bowl-loaves-{bid}', loaves); await set_val(pg, f'#bowl-weight-{bid}', W)
            await pg.evaluate(f"document.getElementById('bowl-onebowl-{bid}').checked={str(ob).lower()}")
            names, pcts = [], []
            for k, mid in enumerate(await pg.evaluate(f"bowls.find(b=>b.id=={bid}).mixins")):
                nm, pc = f'mx{bid}_{k}', random.choice([5, 10, 15, 22.5, 30])
                await pg.evaluate(f"mxVals[{mid}]={{name:'{nm}',pct:'{pc}'}}")
                names.append(nm); pcts.append(pc/100)
            specs.append((W, loaves, ob, names, pcts))
        await pg.evaluate("calc()")
        rows = await pg.evaluate(READ_TABLE)
        for col, (W, loaves, ob, names, pcts) in enumerate(specs):
            check_bowl(f'simple#{i} bowl{col+1} W={W} n={loaves} one={ob} lev={lev}', col, rows,
                       expected(W, loaves, ob, 0.70, 0.02, lev, pcts), names, 0.70, 0.02, lev)
        if len(specs) > 1:
            check_all_bowls(f'simple#{i}', rows, [1 if ob else n for _, n, ob, _, _ in specs])

async def advanced_cases(pg):
    for i in range(N_CASES):
        await pg.goto(PAGE)
        await pg.evaluate("setMode('advanced')")
        h = random.randint(55, 110)/100; s = random.choice([1.5, 1.8, 2.0, 2.2, 2.5, 3.0])/100
        glev = random.randint(5, 40)/100
        await set_val(pg, '#a-hyd', round(h*100)); await set_val(pg, '#a-salt', s*100); await set_val(pg, '#a-starter', round(glev*100))
        wpct = random.choice([100, 90, 80, 70, 60]); ww = random.choice([0, 100 - wpct]); rye = 100 - wpct - ww
        await set_val(pg, '#fb-white', wpct); await set_val(pg, '#fb-ww', ww); await set_val(pg, '#fb-rye', rye)
        names, pcts = [], []
        for k in range(random.randint(0, 2)):
            await pg.evaluate("addMixin()")
        for k, mid in enumerate(await pg.evaluate("advMx.slice()")):
            nm, pc = f'amx{k}', random.choice([5, 10, 15, 25])
            await pg.evaluate(f"mxVals[{mid}]={{name:'{nm}',pct:'{pc}'}}")
            names.append(nm); pcts.append(pc/100)
        for _ in range(random.randint(0, 2)): await pg.evaluate("addAdvBowl()")
        specs = []
        for bid in await pg.evaluate("advBowls.map(b=>b.id)"):
            loaves, W, ob = random.randint(1, 6), random.randint(200, 2000), random.random() < 0.7
            ovr, olev = random.random() < 0.4, random.randint(5, 40)/100
            await set_val(pg, f'#ab-loaves-{bid}', loaves); await set_val(pg, f'#ab-weight-{bid}', W)
            await pg.evaluate(f"document.getElementById('ab-onebowl-{bid}').checked={str(ob).lower()}")
            await pg.evaluate(f"document.getElementById('ab-ovr-{bid}').checked={str(ovr).lower()}")
            await set_val(pg, f'#ab-ovr-val-{bid}', round(olev*100))
            specs.append((W, loaves, ob, olev if ovr else glev))
        await pg.evaluate("calc()")
        rows = await pg.evaluate(READ_TABLE)
        for col, (W, loaves, ob, lev) in enumerate(specs):
            case = f'adv#{i} bowl{col+1} W={W} n={loaves} one={ob} h={h} s={s} lev={lev} blend={wpct}/{ww}/{rye}'
            exp = expected(W, loaves, ob, h, s, lev, pcts)
            check_bowl(case, col, rows, exp, names, h, s, lev)
            # Blend: rows sum exactly to the flour to add; ww/rye are % of TOTAL flour
            if ww or rye:
                parts = {k: num(rows[k][col]) for k in ('White', 'Whole wheat', 'Rye') if k in rows}
                if abs(sum(parts.values()) - num(rows['Flour'][col])) > 0.01:
                    fails.append(f'{case}: blend rows {parts} do not sum to Flour {rows["Flour"][col]}')
                for k, pct in (('Whole wheat', ww), ('Rye', rye)):
                    if pct and abs(parts.get(k, 0) - exp['T']*pct/100) > 0.51:
                        fails.append(f'{case}: {k} {parts.get(k)} g, expected {exp["T"]*pct/100:.1f} g ({pct}% of total flour)')
        if len(specs) > 1:
            check_all_bowls(f'adv#{i}', rows, [1 if ob else n for _, n, ob, _ in specs])

async def main():
    async with async_playwright() as p:
        b, pg, errs = await launch(p)
        await simple_cases(pg)
        await advanced_cases(pg)
        await b.close()
    fails.extend(f'JS error: {e}' for e in errs)
    print(f'{N_CASES} Simple + {N_CASES} Advanced random recipes checked: {len(fails)} failure(s)')
    for f in fails[:25]: print('  FAIL', f)
    return 1 if fails else 0

if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
