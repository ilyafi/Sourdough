"""Guide tests: the guide shows exactly the calculator's quantities, sizes the
levain build correctly, shows only the right steps, and old links still work.

Run:  python3 tests/test_guide.py          (exit code 1 on any failure)
"""
import asyncio, math, random, sys
from pathlib import Path
from playwright.async_api import async_playwright
from common import launch, PAGE

GUIDE = PAGE.replace('sourdough-calculator.html', 'guide.html')
BASE = PAGE.rsplit('/', 1)[0] + '/'
random.seed(7)
fails, checks = [], 0

def check(name, ok, detail=''):
    global checks
    checks += 1
    if not ok: fails.append(f'{name}: {detail}')

def n(v): return float(str(v).replace(',', '').replace('g', '').strip() or 0)

CALC_TABLE = """() => { const o = {}; document.querySelectorAll('.out-table tbody tr').forEach(r => {
  const l = r.querySelector('td.col-lbl'); if (!l) return;
  o[l.textContent.trim()] = [...r.querySelectorAll('td.val')].map(t => t.textContent.replace(/\\s*g$/,'').trim()); });
  o._factors = (mode === 'simple' ? bowls.map(b => document.getElementById('bowl-onebowl-'+b.id).checked ? 1 : rInt('bowl-loaves-'+b.id,1))
                                  : advBowls.map(b => document.getElementById('ab-onebowl-'+b.id).checked ? 1 : rInt('ab-loaves-'+b.id,1)));
  return o; }"""

GUIDE_READ = """() => {
  const q = k => document.querySelector('#step2 [data-q="'+k+'"]').textContent;
  const lev = [...document.querySelectorAll('#ing-levain td.amt')].map(t => t.textContent);
  const dough = {}; document.querySelectorAll('#ing-dough tr').forEach(r => {
    const t = r.querySelector('td'); const a = r.querySelector('td.amt');
    dough[t.childNodes[0].textContent.trim()] = a.textContent; });
  return { levain: q('levain'), water: q('water'), salt: q('salt'), flour: q('flour'), build: lev, dough,
           step1: document.getElementById('levain-build-text').textContent,
           visible: [...document.querySelectorAll('.section[id]')].filter(s => getComputedStyle(s).display !== 'none').map(s => s.id),
           pickers: document.querySelectorAll('#step2 [data-picker] button').length }; }"""

async def set_val(pg, sel, v):
    await pg.evaluate("([s,v]) => { document.querySelector(s).value = v; }", [sel, str(v)])

async def random_calc(pg, i):
    await pg.goto(PAGE)
    advanced = i % 2 == 1
    if not advanced:
        await pg.evaluate(f"setStep({random.randint(0,2)})")
        if random.random() < 0.4: await pg.evaluate("setBreadType('baguette')")
        for _ in range(random.randint(0, 2)): await pg.evaluate("addBowl()")
        for bid in await pg.evaluate("bowls.map(b=>b.id)"):
            await set_val(pg, f'#bowl-loaves-{bid}', random.randint(1, 6))
            await set_val(pg, f'#bowl-weight-{bid}', random.randint(250, 1500))
            await pg.evaluate(f"document.getElementById('bowl-onebowl-{bid}').checked={str(random.random()<0.75).lower()}")
    else:
        await pg.evaluate("setMode('advanced')")
        await set_val(pg, '#a-hyd', random.randint(60, 95)); await set_val(pg, '#a-salt', random.choice([1.8, 2, 2.2]))
        await set_val(pg, '#a-starter', random.randint(8, 30))
        w = random.choice([100, 80, 70]); ww = random.choice([0, 100 - w])
        await set_val(pg, '#fb-white', w); await set_val(pg, '#fb-ww', ww); await set_val(pg, '#fb-rye', 100 - w - ww)
        if random.random() < 0.6:
            await pg.evaluate("addMixin()")
            mid = (await pg.evaluate("advMx.slice()"))[0]
            await pg.evaluate(f"mxVals[{mid}]={{name:'seeds',pct:'{random.choice([5,10,15])}'}}")
        for _ in range(random.randint(0, 2)): await pg.evaluate("addAdvBowl()")
        for bid in await pg.evaluate("advBowls.map(b=>b.id)"):
            await set_val(pg, f'#ab-loaves-{bid}', random.randint(1, 5)); await set_val(pg, f'#ab-weight-{bid}', random.randint(300, 1800))
            await pg.evaluate(f"document.getElementById('ab-onebowl-{bid}').checked={str(random.random()<0.75).lower()}")
            if random.random() < 0.3:
                await pg.evaluate(f"document.getElementById('ab-ovr-{bid}').checked=true")
                await set_val(pg, f'#ab-ovr-val-{bid}', random.randint(8, 30))
    await pg.evaluate("calc()")
    return advanced

async def main():
    async with async_playwright() as p:
        b, pg, errs = await launch(p, viewport={'width': 1100, 'height': 900})

        # ── Calculator → guide: quantities match for every bowl ──
        for i in range(40):
            adv = await random_calc(pg, i)
            calc = await pg.evaluate(CALC_TABLE)
            btype = await pg.evaluate("mode==='simple' ? breadType : 'loaf'")
            href = await pg.get_attribute('#guide-link', 'href')
            await pg.goto(BASE + href); await pg.wait_for_timeout(50)
            nb = len(calc['_factors'])
            needed = 0
            for col in range(nb):
                if nb > 1: await pg.click(f'#step2 [data-picker] button:nth-of-type({col+1})')
                gd = await pg.evaluate(GUIDE_READ)
                case = f'case{i} ({"adv" if adv else "simple"}) bowl{col+1}'
                for k, lbl in [('levain','Levain'), ('water','Water'), ('salt','Salt'), ('flour','Flour')]:
                    check(f'{case} {k}', abs(n(gd[k]) - n(calc[lbl][col])) < 0.01, f'guide {gd[k]} vs calculator {calc[lbl][col]}')
                check(f'{case} total dough', abs(n(gd['dough']['Total dough']) - n(calc['Total dough'][col])) < 0.01,
                      f'guide {gd["dough"]["Total dough"]} vs calc {calc["Total dough"][col]}')
                for k in ('White bread flour', 'Whole wheat flour', 'Rye flour'):
                    calc_k = {'White bread flour': 'White', 'Whole wheat flour': 'Whole wheat', 'Rye flour': 'Rye'}[k]
                    if calc_k in calc and n(calc[calc_k][col]) and k in gd['dough']:
                        check(f'{case} {k}', abs(n(gd['dough'][k]) - n(calc[calc_k][col])) < 0.01, f'{gd["dough"][k]} vs {calc[calc_k][col]}')
                if 'seeds' in calc:
                    check(f'{case} mix-in', abs(n(gd['dough'].get('seeds', 0)) - n(calc['seeds'][col])) < 0.01, f'{gd["dough"].get("seeds")} vs {calc["seeds"][col]}')
                needed += n(calc['Levain'][col]) * calc['_factors'][col]
            # Levain build: 1:2:2, at least what's needed, roughly 10% margin
            st, fl, wa, tot = [n(x) for x in gd['build']]
            check(f'case{i} build ratio', abs(fl - 2*st) <= 2 and fl == wa, f'{st}:{fl}:{wa}')
            check(f'case{i} build covers all bowls', tot >= needed * 1.09 and tot <= needed * 1.10 + 5,
                  f'build {tot} g for {needed} g needed')
            check(f'case{i} step 1 text uses build', f'{int(st)} g' in gd['step1'] and f'{int(fl)} g' in gd['step1'], gd['step1'][:80])
            want = ['step4b', 'step5b'] if btype == 'baguette' else ['step4', 'step5']
            other = ['step4', 'step5'] if btype == 'baguette' else ['step4b', 'step5b']
            check(f'case{i} correct steps shown', all(s in gd['visible'] for s in want) and not any(s in gd['visible'] for s in other), gd['visible'])
            check(f'case{i} bowl picker', (gd['pickers'] == nb) if nb > 1 else gd['pickers'] == 0, f'{gd["pickers"]} buttons for {nb} bowls')

        # ── Guide opened directly ──
        for mode, steps, notsteps, lev in [('loaf', ['step4','step5'], ['step4b','step5b'], 83), ('baguette', ['step4b','step5b'], ['step4','step5'], 70)]:
            await pg.goto(GUIDE)
            if mode == 'baguette': await pg.click('#tab-baguette')
            gd = await pg.evaluate(GUIDE_READ)
            check(f'default {mode}: steps', all(s in gd['visible'] for s in steps) and not any(s in gd['visible'] for s in notsteps), gd['visible'])
            check(f'default {mode}: levain', n(gd['levain']) == lev, gd['levain'])

        # ── Old-style guide link (bookmarks made before this change) ──
        await pg.goto(GUIDE + '?levain=166&water=691&salt=22.1&flour=1022&totalFlour=1105&hyd_pct=70&loaves=2&lwt=950&onebowl=1&bowl=Bowl+1&mixins=&type=loaf')
        gd = await pg.evaluate(GUIDE_READ)
        check('legacy link quantities', (n(gd['levain']), n(gd['water']), n(gd['flour'])) == (166, 691, 1022), gd)
        await pg.goto(GUIDE + '?levain=140&water=582&salt=18.6&flour=862&totalFlour=932&hyd_pct=70&loaves=4&lwt=400&onebowl=1&type=baguette')
        gd = await pg.evaluate(GUIDE_READ)
        check('legacy baguette link', 'step4b' in gd['visible'] and n(gd['levain']) == 140, gd)

        # ── Garbage link falls back to defaults without errors ──
        await pg.goto(GUIDE + '?r=%7Bnot-json')
        gd = await pg.evaluate(GUIDE_READ)
        check('bad link falls back to default', n(gd['levain']) == 83, gd['levain'])

        await b.close()
    fails.extend(f'JS error: {e}' for e in errs)
    print(f'{checks} guide checks: {len(fails)} failure(s)')
    for f in fails[:25]: print('  FAIL', f)
    return 1 if fails else 0

if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
