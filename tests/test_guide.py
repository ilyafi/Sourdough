"""Guide tests: the guide shows exactly the calculator's quantities (all bowls,
all bread types including focaccia with olive oil), sizes the levain build
correctly, shows only the right steps, and old links still work.

Run:  python3 tests/test_guide.py          (exit code 1 on any failure)
"""
import asyncio, json, random, sys
from playwright.async_api import async_playwright
from common import launch, PAGE, GUIDE, BASE
from test_math import random_case

random.seed(7)
fails, checks = [], 0

def check(name, ok, detail=''):
    global checks
    checks += 1
    if not ok: fails.append(f'{name}: {detail}')

def n(v):
    v = str(v).replace(',', '').replace('g', '').replace('ml', '').replace('\u00a0', '').strip()
    return 0.0 if v in ('', '–') else float(v)

CALC = """() => { const o = {}; document.querySelectorAll('.out-table tbody tr').forEach(r => {
  const l = r.querySelector('td.col-lbl'); if (!l) return;
  o[l.textContent.trim()] = [...r.querySelectorAll('td.val')].map(t => t.textContent.replace(/\\s*g$/,'').trim()); });
  o._factors = plan.bowls.map(b => b.factor);
  o._areas = plan.bowls.map(b => b.tray ? b.tray.area : 0);
  o._oil = plan.recipe.oil;
  return o; }"""

GUIDE_READ = """() => {
  const q = k => document.querySelector('#step2 [data-q="'+k+'"]').textContent;
  const vis = el => el && getComputedStyle(el).display !== 'none' && !el.closest('.hidden');
  const dough = {}; document.querySelectorAll('#ing-dough tr').forEach(r => {
    dough[r.querySelector('td').childNodes[0].textContent.trim()] = r.querySelector('td.amt').textContent; });
  const trayOil = document.querySelector('#step4f [data-trayoil]');
  return { levain: q('levain'), water: q('water'), salt: q('salt'), flour: q('flour'), oil: q('oil'),
           oilStepShown: vis(document.querySelector('#step2 [data-oil]')),
           build: [...document.querySelectorAll('#ing-levain td.amt')].map(t => t.textContent), dough,
           step1: document.getElementById('levain-build-text').textContent,
           trayOil: trayOil ? trayOil.textContent : '',
           shopping: document.getElementById('ing-shopping').textContent,
           banner: document.getElementById('banner').textContent,
           visible: [...document.querySelectorAll('.section[id]')].filter(s => getComputedStyle(s).display !== 'none').map(s => s.id),
           pickers: document.querySelectorAll('#step2 [data-picker] button').length }; }"""

STEPS = {'loaf': ['step4', 'step5'], 'baguette': ['step4b', 'step5b'], 'focaccia': ['step4f', 'step5f']}

async def main():
    async with async_playwright() as p:
        b, pg, errs = await launch(p, viewport={'width': 1100, 'height': 900})
        tray_oil = lambda area: pg.evaluate(f"Sourdough.trayOil({area})")

        # ── Calculator → guide: quantities match for every bowl ──
        for i in range(60):
            st, exp = random_case()
            await pg.goto(PAGE)
            await pg.evaluate(f"state = sanitize({json.dumps(st)}); renderAll(); calc();")
            calc = await pg.evaluate(CALC)
            href = await pg.get_attribute('#guide-link', 'href')
            await pg.goto(BASE + href)
            typ = exp['type']; nb = len(calc['_factors']); case = f'case{i} ({typ})'
            for col in range(nb):
                if nb > 1: await pg.click(f'#step2 [data-picker] button:nth-of-type({col+1})')
                gd = await pg.evaluate(GUIDE_READ)
                c = f'{case} bowl{col+1}'
                for k, lbl in [('levain', 'Levain'), ('water', 'Water'), ('salt', 'Salt'), ('flour', 'Flour')]:
                    check(f'{c} {k}', abs(n(gd[k]) - n(calc[lbl][col])) < 0.01, f'guide {gd[k]} vs calculator {calc[lbl][col]}')
                check(f'{c} total dough', abs(n(gd['dough']['Total dough']) - n(calc['Total dough'][col])) < 0.01, (gd['dough'], calc['Total dough'][col]))
                if calc['_oil']:
                    check(f'{c} oil', abs(n(gd['oil']) - n(calc['Olive oil'][col])) < 0.01 and abs(n(gd['dough'].get('Olive oil', 0)) - n(calc['Olive oil'][col])) < 0.01, (gd['oil'], calc['Olive oil'][col]))
                    check(f'{c} oil step shown', gd['oilStepShown'])
                else:
                    check(f'{c} no oil step', not gd['oilStepShown'] and 'Olive oil' not in gd['dough'])
                for gk, ck in (('White bread flour', 'White'), ('Whole wheat flour', 'Whole wheat'), ('Rye flour', 'Rye')):
                    if ck in calc and n(calc[ck][col]):
                        check(f'{c} {gk}', abs(n(gd['dough'].get(gk, 0)) - n(calc[ck][col])) < 0.01, (gd['dough'].get(gk), calc[ck][col]))
                for name in (k for k in calc if k.startswith('mx')):
                    if n(calc[name][col]): check(f'{c} {name}', abs(n(gd['dough'].get(name, 0)) - n(calc[name][col])) < 0.01)
                if typ == 'focaccia':
                    o = await tray_oil(calc['_areas'][col])
                    check(f'{c} tray oil', f"{o['ml']} ml" in gd['trayOil'], (gd['trayOil'], o))
            needed = sum(n(calc['Levain'][col]) * f for col, f in enumerate(calc['_factors']))
            st_, fl, wa, tot = [n(x) for x in gd['build']]
            check(f'{case} build ratio', abs(fl - 2 * st_) <= 2 and fl == wa, f'{st_}:{fl}:{wa}')
            check(f'{case} build covers all bowls', needed * 1.09 <= tot <= needed * 1.10 + 5, f'{tot} for {needed}')
            check(f'{case} step 1 text', f'{int(st_)} g' in gd['step1'] and f'{int(fl)} g' in gd['step1'], gd['step1'][:80])
            want, other = STEPS[typ], [s for t, ss in STEPS.items() if t != typ for s in ss]
            check(f'{case} correct steps', all(s in gd['visible'] for s in want) and not any(s in gd['visible'] for s in other), gd['visible'])
            check(f'{case} bowl picker', gd['pickers'] == (nb if nb > 1 else 0), f'{gd["pickers"]} for {nb}')
            if typ == 'focaccia':
                check(f'{case} tray oil in shopping list', 'Olive oil for the tray' in gd['shopping'] and 'Rice flour' not in gd['shopping'])

        # ── Guide opened directly: each tab ──
        for tab, lev in (('loaf', 83), ('baguette', 70), ('focaccia', 71)):
            await pg.goto(GUIDE)
            await pg.click(f'#tab-{tab}')
            gd = await pg.evaluate(GUIDE_READ)
            check(f'default {tab}: steps', all(s in gd['visible'] for s in STEPS[tab]) and sum(s in gd['visible'] for t in STEPS for s in STEPS[t]) == 2, gd['visible'])
            check(f'default {tab}: levain', n(gd['levain']) == lev, gd['levain'])
        o = await tray_oil(759)
        check('default focaccia tray oil', f"{o['ml']} ml" in gd['trayOil'], gd['trayOil'])
        await pg.goto(GUIDE + '#focaccia')
        check('#focaccia opens the focaccia tab', 'active' in await pg.get_attribute('#tab-focaccia', 'class'))

        # ── Switching tab away from a linked recipe ──
        await pg.goto(PAGE)
        await pg.evaluate("state = sanitize({type:'focaccia', bowls:[{counts:{focaccia:'3'}}]}); renderAll(); calc();")
        await pg.goto(BASE + await pg.get_attribute('#guide-link', 'href'))
        gd = await pg.evaluate(GUIDE_READ)
        check('linked focaccia shows "Your recipe"', 'Your recipe' in gd['banner'] and '3 trays' in gd['banner'], gd['banner'])
        await pg.click('#tab-loaf')
        gd = await pg.evaluate(GUIDE_READ)
        check('other tab shows default with a way back', n(gd['levain']) == 83 and 'Back to your focaccia recipe' in gd['banner'], gd['banner'])
        await pg.click('#banner a')
        gd = await pg.evaluate(GUIDE_READ)
        check('back link returns to linked recipe', 'Your recipe' in gd['banner'] and 'step4f' in gd['visible'])

        # ── Old-style guide links (bookmarks made before the shared maths) ──
        await pg.goto(GUIDE + '?levain=166&water=691&salt=22.1&flour=1022&totalFlour=1105&hyd_pct=70&loaves=2&lwt=950&onebowl=1&bowl=Bowl+1&mixins=&type=loaf')
        gd = await pg.evaluate(GUIDE_READ)
        check('legacy link quantities', (n(gd['levain']), n(gd['water']), n(gd['flour'])) == (166, 691, 1022), gd)
        await pg.goto(GUIDE + '?levain=140&water=582&salt=18.6&flour=862&totalFlour=932&hyd_pct=70&loaves=4&lwt=400&onebowl=1&type=baguette')
        gd = await pg.evaluate(GUIDE_READ)
        check('legacy baguette link', 'step4b' in gd['visible'] and n(gd['levain']) == 140, gd)

        # ── Links made before focaccia existed (no oil / tray fields) ──
        await pg.goto(GUIDE + '?r=' + json.dumps({"t": "loaf", "h": 70, "s": 2, "b": [["Plain", 2, 950, 1, 15, []]]}))
        gd = await pg.evaluate(GUIDE_READ)
        check('pre-focaccia ?r= link', n(gd['levain']) == 166 and not gd['oilStepShown'], gd)

        # ── Garbage links fall back to defaults without errors ──
        for q in ('?r=%7Bnot-json', '?r=' + json.dumps({"t": "focaccia", "b": []})):
            await pg.goto(GUIDE + q)
            gd = await pg.evaluate(GUIDE_READ)
            check(f'bad link {q[:20]} → default', n(gd['levain']) in (83, 71), gd['levain'])

        await b.close()
    fails.extend(f'JS error: {e}' for e in errs)
    print(f'{checks} guide checks: {len(fails)} failure(s)')
    for f in fails[:25]: print('  FAIL', f)
    return 1 if fails else 0

if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
