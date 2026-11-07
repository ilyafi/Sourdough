"""Interaction tests for sourdough-calculator.html: entries survive re-renders,
totals stay coherent, labels match the mode.

Run:  python3 tests/test_state.py          (exit code 1 on any failure)
"""
import asyncio, sys
from playwright.async_api import async_playwright
from common import launch, PAGE

results = []
def check(name, ok, detail=''):
    results.append((name, bool(ok), detail))

async def typ(pg, sel, v):
    await pg.fill(sel, str(v))      # fires input events like a real user

async def table(pg):
    return await pg.evaluate("""() => {
      const o = {}; document.querySelectorAll('.out-table tbody tr').forEach(r => {
        const l = r.querySelector('td.col-lbl'); if (!l) return;
        o[l.textContent.trim()] = [...r.querySelectorAll('td.val')].map(t => t.textContent.replace(/\\s*g$/,'').replace(/,/g,'').trim());
      });
      o._heads = [...document.querySelectorAll('.out-table thead th')].map(t => t.textContent.trim());
      o._notes = [...document.querySelectorAll('.out-table tr.note-row td')].map(t => t.textContent.trim());
      return o; }""")

async def vals(pg, *sels):
    return [await pg.input_value(s) for s in sels]

async def main():
    async with async_playwright() as p:
        b, pg, errs = await launch(p, viewport={'width': 1100, 'height': 900})

        # ── Mix-ins survive re-renders ──
        await pg.goto(PAGE)
        await pg.click('#p-simple-in .bowl-card .btn-add')
        m = (await pg.evaluate("bowls[0].mixins"))[0]
        await typ(pg, f'#bmx-n-1-{m}', 'figs'); await typ(pg, f'#bmx-p-1-{m}', '22')
        await pg.click('#p-simple-in .btn-add-bowl')
        v = await vals(pg, f'#bmx-n-1-{m}', f'#bmx-p-1-{m}')
        check('Simple: bowl 1 mix-in kept after adding a bowl', v == ['figs', '22'], v)

        m2 = (await pg.evaluate("bowls[1].mixins"))[0]
        await typ(pg, f'#bmx-n-2-{m2}', 'pecans'); await typ(pg, f'#bmx-p-2-{m2}', '18')
        await pg.click('#p-simple-in .btn-add-bowl')
        v = await vals(pg, f'#bmx-n-2-{m2}', f'#bmx-p-2-{m2}')
        check('Simple: edited default mix-in kept after adding another bowl', v == ['pecans', '18'], v)

        await pg.click('#btn-type-baguette')
        v = await vals(pg, f'#bmx-n-2-{m2}', f'#bmx-p-2-{m2}')
        check('Simple: mix-ins kept after Loaf→Baguette', v == ['pecans', '18'], v)

        await pg.click('#p-simple-in .bowl-card:nth-child(1) .btn-rm-bowl')
        v = await vals(pg, f'#bmx-n-2-{m2}', f'#bmx-p-2-{m2}')
        check('Simple: other mix-ins kept after removing a bowl', v == ['pecans', '18'], v)

        await pg.goto(PAGE); await pg.click('#btn-advanced')
        await pg.click('#p-adv-pct .btn-add')
        a1 = (await pg.evaluate("advMx.slice()"))[0]
        await typ(pg, f'#mx-n-{a1}', 'olives'); await typ(pg, f'#mx-p-{a1}', '12')
        await pg.click('#p-adv-pct .btn-add')
        v = await vals(pg, f'#mx-n-{a1}', f'#mx-p-{a1}')
        check('Advanced: mix-in kept after adding another', v == ['olives', '12'], v)
        a2 = (await pg.evaluate("advMx.slice()"))[1]
        await typ(pg, f'#mx-n-{a2}', 'rosemary'); await typ(pg, f'#mx-p-{a2}', '1')
        await pg.click('#p-adv-pct .mx-row:nth-child(1) .btn-rm')
        v = await vals(pg, f'#mx-n-{a2}', f'#mx-p-{a2}')
        check('Advanced: remaining mix-in kept after removing one', v == ['rosemary', '1'], v)

        # ── All bowls column is the full bake ──
        await pg.goto(PAGE)
        await pg.click('#p-simple-in .btn-add-bowl')
        await pg.click('#p-simple-in .bowl-card:nth-child(2) .btn-rm')       # drop walnuts
        await pg.click('#p-simple-in .bowl-card:nth-child(1) .tog-wrap')     # bowl 1 per-loaf
        t = await table(pg)
        tot = [int(x) for x in t['Total dough']]
        check('All bowls = full bake when a bowl is per-loaf', tot[2] == tot[0]*2 + tot[1], tot)
        check('Per-loaf column header says so', 'one loaf' in t['_heads'][1], t['_heads'][1])

        # ── Large batches show exact grams ──
        await pg.goto(PAGE)
        await typ(pg, '#bowl-loaves-1', '12')
        t = await table(pg)
        check('≥10 kg shown in exact grams', t['Total dough'][0].isdigit() and int(t['Total dough'][0]) in range(11400, 11406),
              t['Total dough'][0])

        # ── Duplicate mix-in names merge ──
        await pg.goto(PAGE); await pg.click('#btn-advanced')
        await pg.click('#p-adv-pct .btn-add'); await pg.click('#p-adv-pct .btn-add')
        ms = await pg.evaluate("advMx.slice()")
        await typ(pg, f'#mx-n-{ms[0]}', 'seeds'); await typ(pg, f'#mx-p-{ms[0]}', '5')
        await typ(pg, f'#mx-n-{ms[1]}', 'Seeds'); await typ(pg, f'#mx-p-{ms[1]}', '10')
        t = await table(pg)
        comp = sum(float(t[k][0]) for k in ('Levain', 'Water', 'Salt', 'Flour', 'seeds'))
        check('Duplicate mix-in names merge and table adds up', abs(comp - float(t['Total dough'][0])) <= 0.5,
              f'seeds={t["seeds"][0]}, rows={comp:.1f}, total={t["Total dough"][0]}')

        # ── Flour blend ──
        await pg.goto(PAGE); await pg.click('#btn-advanced')
        await typ(pg, '#fb-white', '80'); await typ(pg, '#fb-ww', '20')
        t = await table(pg)
        ww, tf, fl = float(t['Whole wheat'][0]), float(t['Total flour (incl. levain)'][0]), float(t['Flour'][0])
        check('Blend: whole wheat is 20% of total flour', abs(ww/tf - 0.20) < 0.002, f'{ww} / {tf}')
        check('Blend rows sum to flour', float(t['White'][0]) + ww == fl, f'{t["White"][0]} + {ww} vs {fl}')
        await typ(pg, '#a-starter', '60'); await pg.dispatch_event('#a-starter', 'input')
        await typ(pg, '#fb-white', '20'); await typ(pg, '#fb-ww', '80')
        t = await table(pg)
        check('Blend: warns when levain flour exceeds white share', any('levain' in n.lower() for n in t['_notes']), t['_notes'])

        # ── Labels, defaults, fallbacks ──
        await pg.goto(PAGE); await pg.click('#btn-type-baguette')
        lbl = await pg.evaluate("document.querySelector('#bowl-cards .frow .field:nth-child(2) label').textContent")
        check('Baguette: weight label says baguette', 'baguette' in lbl.lower(), lbl)
        check('Baguette: default weight 400 g', (await pg.input_value('#bowl-weight-1')) == '400')
        await pg.click('#btn-advanced')
        t = await table(pg)
        check('Advanced header does not borrow Simple bread type', 'baguette' not in t['_heads'][1], t['_heads'][1])

        await pg.goto(PAGE)
        await typ(pg, '#bowl-weight-1', '1100')
        await pg.click('#btn-type-baguette'); await pg.click('#btn-type-loaf')
        check('Typed weight survives Loaf→Baguette→Loaf', (await pg.input_value('#bowl-weight-1')) == '1100')

        await pg.goto(PAGE)
        ref = (await table(pg))['Total dough'][0]
        await typ(pg, '#bowl-weight-1', '')
        t = await table(pg)
        check('Blank weight falls back to default (950 g)', t['Total dough'][0] == ref, f'{t["Total dough"][0]} vs {ref}')

        t = await table(pg)
        check('No redundant "Added flour" row', 'Added flour' not in t)

        href = await pg.get_attribute('#guide-link', 'href')
        check('Guide link carries the recipe', href.startswith('guide.html?r='), href[:90])

        await b.close()

    for e in errs: results.append(('No JavaScript errors', False, e))
    bad = 0
    for n, ok, d in results:
        bad += not ok
        print(('PASS ' if ok else 'FAIL ') + n + ('' if ok else f'\n       {d}'))
    print(f'{len(results) - bad}/{len(results)} passed')
    return 1 if bad else 0

if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
