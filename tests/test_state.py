"""Interaction tests for sourdough-calculator.html, driven like a person would:
entries survive re-renders, focaccia trays and thickness, olive oil, the page
remembering the last bake, named recipes, and storage being unavailable.

Run:  python3 tests/test_state.py          (exit code 1 on any failure)
"""
import asyncio, sys
from playwright.async_api import async_playwright
from common import browser, fresh_page, PAGE

results = []
def check(name, ok, detail=''):
    results.append((name, bool(ok), detail))

TABLE = """() => {
  const o = {}; document.querySelectorAll('.out-table tbody tr').forEach(r => {
    const l = r.querySelector('td.col-lbl'); if (!l) return;
    o[l.textContent.trim()] = [...r.querySelectorAll('td.val')].map(t => t.textContent.replace(/\\s*g$/,'').replace(/,/g,'').trim());
  });
  o._heads = [...document.querySelectorAll('.out-table thead th')].map(t => t.textContent.trim());
  o._notes = [...document.querySelectorAll('.out-notes p')].map(p => p.textContent.trim());
  return o; }"""

async def table(pg): return await pg.evaluate(TABLE)
async def ids(pg): return await pg.evaluate("state.bowls.map(b => b.id)")
async def toggle(pg, input_id): await pg.click(f'label:has(#{input_id})')
async def total(pg, col=0): return int((await table(pg))['Total dough'][col])

async def main():
    async with async_playwright() as p:
        b = await browser(p)
        errs = []
        pg = await fresh_page(b, errs, viewport={'width': 1100, 'height': 900})
        await pg.goto(PAGE)

        # ── Mix-ins survive re-renders ──
        await pg.click('#p-bowls .bowl-card .btn-add')
        [b1] = await ids(pg)
        m = (await pg.evaluate("state.bowls[0].mixins[0].id"))
        await pg.fill(f'#mx-n-{m}', 'figs'); await pg.fill(f'#mx-p-{m}', '22')
        await pg.click('.btn-add-bowl')
        check('Mix-in kept after adding a bowl', [await pg.input_value(f'#mx-n-{m}'), await pg.input_value(f'#mx-p-{m}')] == ['figs', '22'])
        await pg.click('#btn-type-baguette'); await pg.click('#btn-type-focaccia'); await pg.click('#btn-type-loaf')
        check('Mix-in kept after switching bread types', await pg.input_value(f'#mx-p-{m}') == '22')
        await pg.click('#btn-advanced'); await pg.click('#btn-simple')
        check('Mix-in kept after switching Simple/Advanced', await pg.input_value(f'#mx-n-{m}') == 'figs')
        [_, b2] = await ids(pg)
        await pg.click(f'#bowl-{b2} .btn-rm-bowl')
        check('Mix-in kept after removing another bowl', await pg.input_value(f'#mx-n-{m}') == 'figs')

        # ── Typed sizes are kept per bread type ──
        await pg.fill(f'#b-weight-{b1}', '1100')
        await pg.click('#btn-type-baguette')
        check('Baguette label and default weight', 'baguette' in (await pg.text_content(f'label[for=b-weight-{b1}]')).lower() and await pg.input_value(f'#b-weight-{b1}') == '400')
        await pg.click('#btn-type-loaf')
        check('Typed loaf weight survives Loaf→Baguette→Loaf', await pg.input_value(f'#b-weight-{b1}') == '1100')
        await pg.fill(f'#b-weight-{b1}', '')
        check('Blank weight falls back to the default', await total(pg) in range(1900, 1906), (await table(pg))['Total dough'])
        await pg.fill(f'#b-weight-{b1}', '950')

        # ── All bowls column = full bake ──
        await pg.click('.btn-add-bowl')
        [b1, b2] = await ids(pg)
        await pg.click(f'#bowl-{b2} .btn-rm')          # drop default walnuts
        await toggle(pg, f'b-one-{b1}')                 # bowl 1 mixed per loaf
        t = await table(pg); tot = [int(x) for x in t['Total dough']]
        check('All bowls = full bake when a bowl is per-loaf', tot[2] == tot[0] * 2 + tot[1], tot)
        check('Per-loaf header says so', 'one loaf' in t['_heads'][1], t['_heads'][1])
        await toggle(pg, f'b-one-{b1}')
        await pg.click(f'#bowl-{b2} .btn-rm-bowl')

        # ── Focaccia: trays, thickness, oil ──
        await pg.click('#btn-type-focaccia')
        check('Focaccia shows tray picker', await pg.is_visible(f'#b-tray-{b1}'))
        check('Focaccia default: 23×33 medium → 835 g', await total(pg) in range(835, 840), await total(pg))
        thin, med, thick = [], [], []
        for lvl, store in (('Thin', thin), ('Medium', med), ('Thick', thick)):
            await pg.click(f'#bowl-{b1} .seg-sm button:has-text("{lvl}")'); store.append(await total(pg))
        check('Thickness changes dough: thin < medium < thick', thin[0] < med[0] < thick[0], (thin, med, thick))
        await pg.click(f'#bowl-{b1} .seg-sm button:has-text("Medium")')
        await pg.select_option(f'#b-tray-{b1}', 'p-33x46')
        check('Bigger tray → more dough (33×46 ≈ 1670 g)', await total(pg) in range(1670, 1676), await total(pg))
        await pg.select_option(f'#b-tray-{b1}', 'p-r24')
        check('Round tray area used (⌀24 ≈ 498 g)', await total(pg) in range(497, 503), await total(pg))
        await pg.select_option(f'#b-tray-{b1}', 'custom')
        check('Custom starts from the last tray’s size (round 24)', await pg.input_value(f'#b-trayd-{b1}') == '24')
        await pg.click(f'#bowl-{b1} .custom-tray button:has-text("Rectangle")')
        await pg.fill(f'#b-trayw-{b1}', '41'); await pg.fill(f'#b-trayl-{b1}', '35')
        check('Custom tray 41×35 → ~1579 g', await total(pg) in range(1578, 1584), await total(pg))
        await pg.fill(f'#b-trayname-{b1}', 'Big tray'); await pg.click(f'#bowl-{b1} button:has-text("Save tray")')
        sel = await pg.input_value(f'#b-tray-{b1}')
        check('Saved tray is selected', sel.startswith('u') and 'Big tray' in await pg.text_content(f'#b-tray-{b1} option:checked'))
        await pg.click('.btn-add-bowl')
        [b1, b2] = await ids(pg)
        check('Saved tray offered in another bowl', 'Big tray' in await pg.text_content(f'#b-tray-{b2}'))
        check('New bowl copies the last bowl’s tray', await pg.input_value(f'#b-tray-{b2}') == sel)
        await pg.click(f'#bowl-{b2} .btn-rm-bowl')

        t = await table(pg)
        check('No olive oil row while oil is off', 'Olive oil' not in t)
        check('Tray-oil note shown for focaccia', any('Tray oil' in n and 'tbsp' in n for n in t['_notes']), t['_notes'])
        await toggle(pg, 'oil-on')
        t = await table(pg)
        check('Olive oil row appears when switched on', 'Olive oil' in t and float(t['Olive oil'][0]) > 0, t.get('Olive oil'))
        flour = float(t['Total flour (incl. levain)'][0])
        check('Oil is 4% of flour by default', abs(float(t['Olive oil'][0]) - flour * 0.04) <= 1.5, (t['Olive oil'], flour))
        await pg.fill('#oil-pct', '8')
        t = await table(pg)
        check('Oil % follows the input', abs(float(t['Olive oil'][0]) - float(t['Total flour (incl. levain)'][0]) * 0.08) <= 1.5)
        await pg.click('#btn-type-loaf')
        check('Oil settings hidden for loaves', not await pg.is_visible('#oil-settings') and 'Olive oil' not in await table(pg))
        await pg.click('#btn-type-focaccia')

        # ── Advanced: per-type hydration, own levain ──
        await pg.click('#btn-advanced')
        check('Advanced focaccia defaults to 75% hydration', await pg.text_content('#lbl-h') == '75%')
        await pg.click('#btn-type-loaf')
        check('Advanced loaf keeps 70% hydration', await pg.text_content('#lbl-h') == '70%')
        await pg.click('#btn-type-focaccia')
        [b1] = await ids(pg)
        await toggle(pg, f'b-levon-{b1}'); await pg.fill(f'#b-lev-{b1}', '25')
        t = await table(pg)
        check('Own levain % used', abs(float(t['Levain'][0]) / float(t['Total flour (incl. levain)'][0]) - 0.25) < 0.004)
        await pg.click('#btn-simple')

        # ── Remembers the last bake ──
        await pg.fill(f'#b-name-{b1}', 'Saturday focaccia')
        await pg.wait_for_timeout(400)
        before = await table(pg)
        await pg.reload(); await pg.wait_for_timeout(200)
        after = await table(pg)
        check('Reload restores bread type', await pg.get_attribute('#btn-type-focaccia', 'class') and 'active' in await pg.get_attribute('#btn-type-focaccia', 'class'))
        check('Reload restores the same recipe', before == after, (before.get('Total dough'), after.get('Total dough')))
        [b1] = await ids(pg)
        check('Reload restores names and trays', await pg.input_value(f'#b-name-{b1}') == 'Saturday focaccia' and 'Big tray' in await pg.text_content(f'#b-tray-{b1} option:checked'))
        check('Reload restores mix-ins', 'figs' in after, list(after))

        # ── Named recipes ──
        await pg.click('#recipes-btn')
        check('Recipes dialog opens', await pg.is_visible('#recipes-dlg'))
        await pg.click('#rcp-save-btn')
        check('Saving without a name asks for one', 'name' in (await pg.text_content('#rcp-msg')).lower())
        await pg.fill('#rcp-name', 'Party focaccia'); await pg.click('#rcp-save-btn')
        check('Recipe saved and listed', 'Party focaccia' in await pg.text_content('#rcp-list'))
        check('Toolbar shows the recipe name', 'Party focaccia' in await pg.text_content('#recipes-btn'))
        saved_total = await total(pg)
        await pg.click('.dlg-x')
        await pg.click('#btn-type-loaf'); await pg.fill(f'#b-count-{b1}', '5')
        check('Edited recipe shows a dot', (await pg.text_content('#recipes-btn')).endswith('•'))
        await pg.click('#recipes-btn')
        await pg.fill('#rcp-name', 'Five loaves'); await pg.click('#rcp-save-btn')
        await pg.fill('#rcp-name', 'party FOCACCIA')
        check('Same name (any case) offers Replace', await pg.text_content('#rcp-save-btn') == 'Replace')
        await pg.fill('#rcp-name', '')
        items = await pg.eval_on_selector_all('.rcp-item .rcp-name', 'els => els.map(e => e.textContent)')
        check('Two recipes listed, newest first', len(items) == 2 and items[0].startswith('Five loaves'), items)
        await pg.click('.rcp-item:has-text("Party focaccia") button:has-text("Load")')
        check('Loading restores the saved recipe', 'active' in await pg.get_attribute('#btn-type-focaccia', 'class') and await total(pg) == saved_total)
        check('Loaded recipe is not marked changed', not (await pg.text_content('#recipes-btn')).endswith('•'))
        await pg.reload(); await pg.wait_for_timeout(200)
        check('Loaded recipe name survives reload', 'Party focaccia' in await pg.text_content('#recipes-btn'))
        await pg.click('#recipes-btn')
        await pg.click('.rcp-item:has-text("Five loaves") button:has-text("Delete")')
        check('Delete asks to confirm', await pg.is_visible('.rcp-item:has-text("Five loaves") button:has-text("Yes")'))
        await pg.click('.rcp-item:has-text("Five loaves") button:has-text("Yes")')
        check('Recipe deleted', 'Five loaves' not in await pg.text_content('#rcp-list'))
        await pg.click('#rcp-new button')
        await pg.click('#rcp-new button:has-text("Yes")')
        [b1] = await ids(pg)
        check('Start new: defaults, keeps bread type', await pg.input_value(f'#b-name-{b1}') == 'Bowl 1' and 'active' in await pg.get_attribute('#btn-type-focaccia', 'class'))
        check('Start new: no recipe name', await pg.text_content('#recipes-btn') == '📁 Recipes')
        check('Saved trays survive starting new', 'Big tray' in await pg.text_content(f'#b-tray-{b1}'))

        # ── Opening the recipe list must not disturb the bowls being edited ──
        await pg.click('#btn-type-loaf')
        await pg.click('.btn-add-bowl'); await pg.click('.btn-add-bowl')
        await pg.click('#recipes-btn'); await pg.click('.dlg-x')
        for _ in range(3): await pg.click('.btn-add-bowl')
        all_ids = await ids(pg)
        check('Bowl ids stay unique after opening Recipes', len(set(all_ids)) == len(all_ids), all_ids)
        await pg.fill(f'#b-name-{all_ids[-1]}', 'Last')
        names = await pg.evaluate("state.bowls.map(b => b.name)")
        check('Editing the new bowl changes only that bowl', names == ['Bowl 1', 'Bowl 2', 'Bowl 3', 'Bowl 4', 'Bowl 5', 'Last'], names)
        for _ in range(5): await pg.click('.bowl-card:last-child .btn-rm-bowl')

        # ── Guide link ──
        check('Guide link carries the recipe', (await pg.get_attribute('#guide-link', 'href')).startswith('guide.html?r='))

        # ── Phone width: no sideways scrolling of the page ──
        ph = await fresh_page(b, errs, viewport={'width': 375, 'height': 800})
        await ph.goto(PAGE)
        await ph.click('#btn-type-focaccia'); await ph.click('.btn-add-bowl'); await ph.click('.btn-add-bowl')
        sw = await ph.evaluate("document.documentElement.scrollWidth")
        check('No page overflow at 375 px with 3 focaccia bowls', sw <= 375, sw)

        # ── Storage blocked (e.g. private browsing) ──
        blocked_errs = []
        ctx = await b.new_context()
        await ctx.add_init_script("Object.defineProperty(window, 'localStorage', { get() { throw new Error('blocked'); } });")
        bp = await ctx.new_page(); bp.on('pageerror', lambda e: blocked_errs.append(str(e)))
        await bp.goto(PAGE)
        await bp.click('#btn-type-focaccia'); await bp.click('.btn-add-bowl')
        await bp.click('#recipes-btn'); await bp.fill('#rcp-name', 'X'); await bp.click('#rcp-save-btn')
        check('Blocked storage: page still works', not blocked_errs and len((await bp.evaluate(TABLE))['Total dough']) == 3, blocked_errs)
        check('Blocked storage: explains save failed', 'blocking storage' in await bp.text_content('#rcp-msg'))

        # ── Corrupt saved data falls back to defaults ──
        cp = await fresh_page(b, errs)
        await cp.goto(PAGE)
        await cp.evaluate("localStorage.setItem('sourdough:last', '{not json'); localStorage.setItem('sourdough:recipes', '[1,null,{\"x\":1}]')")
        await cp.reload()
        check('Corrupt saved data → defaults', (await cp.evaluate(TABLE))['Total dough'] in (['1901'], ['1902']))
        await cp.click('#recipes-btn')
        check('Corrupt recipe list ignored', 'No saved recipes' in await cp.text_content('#rcp-list'))

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
