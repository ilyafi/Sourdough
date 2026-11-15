"""Moving recipes between devices: export file, import file, share links.
Each "device" is a separate browser context with its own storage.

Run:  python3 tests/test_transfer.py          (exit code 1 on any failure)
"""
import asyncio, json, sys, tempfile
from pathlib import Path
from playwright.async_api import async_playwright
from common import browser, PAGE

results, errs = [], []
def check(name, ok, detail=''):
    results.append((name, bool(ok), detail))

# Capture copied links instead of using the real clipboard; optionally make copying fail
CLIPBOARD_OK = "navigator.clipboard.writeText = async t => { window.__copied = t; };"
CLIPBOARD_FAIL = "navigator.clipboard.writeText = async t => { throw new Error('denied'); };"

async def device(b, clipboard=CLIPBOARD_OK):
    ctx = await b.new_context(viewport={'width': 1000, 'height': 900}, accept_downloads=True)
    await ctx.add_init_script(clipboard)
    pg = await ctx.new_page()
    pg.on('pageerror', lambda e: errs.append(str(e)))
    await pg.goto(PAGE)
    return pg

async def total(pg): return (await pg.text_content('td.val.total-row')).replace('g', '').strip()
async def msg(pg): return await pg.text_content('#rcp-msg')
async def recipe_names(pg): return await pg.evaluate("recipes().map(r => r.name).sort()")

async def save_recipe(pg, name):
    await pg.click('#recipes-btn'); await pg.fill('#rcp-name', name); await pg.click('#rcp-save-btn'); await pg.click('.dlg-x')

async def make_focaccia_with_tray(pg):
    await pg.click('#btn-type-focaccia')
    bid = await pg.evaluate("state.bowls[0].id")
    await pg.select_option(f'#b-tray-{bid}', 'custom')
    await pg.fill(f'#b-trayw-{bid}', '41'); await pg.fill(f'#b-trayl-{bid}', '35')
    await pg.fill(f'#b-trayname-{bid}', 'Big tray'); await pg.click(f'#bowl-{bid} button:has-text("Save tray")')
    await pg.fill(f'#b-count-{bid}', '2')

async def export(pg, folder):
    await pg.click('#recipes-btn')
    async with pg.expect_download() as d:
        await pg.click('#export-btn')
    dl = await d.value
    path = Path(folder) / dl.suggested_filename
    await dl.save_as(path)
    m = await msg(pg)
    await pg.click('.dlg-x')
    return path, m

async def import_file(pg, path):
    await pg.click('#recipes-btn')
    await pg.set_input_files('#import-file', str(path))
    await pg.wait_for_function("document.getElementById('rcp-msg').textContent.length > 0")
    m = await msg(pg)
    await pg.click('.dlg-x')
    return m

async def load(pg, name):
    await pg.click('#recipes-btn')
    await pg.click(f'.rcp-item:has(.rcp-name:text-is("{name}")) button:has-text("Load")')

async def main():
    tmp = tempfile.mkdtemp()
    async with async_playwright() as p:
        b = await browser(p)

        # ── Device A: two recipes and a saved tray ──
        A = await device(b)
        await A.click('#recipes-btn'); await A.click('#export-btn')
        check('Export with nothing saved explains why', 'Nothing to export' in await msg(A), await msg(A))
        await A.click('.dlg-x')
        await save_recipe(A, 'Plain loaves')
        await make_focaccia_with_tray(A)
        await save_recipe(A, 'Party focaccia')
        focaccia_total = await total(A)
        path, m = await export(A, tmp)
        data = json.loads(path.read_text())
        check('Export file name has the date', path.name.startswith('sourdough-recipes-20') and path.suffix == '.json', path.name)
        check('Export contains 2 recipes and 1 tray', data.get('kind') == 'ilyabread-recipes' and len(data['recipes']) == 2 and len(data['trays']) == 1, data.keys())
        check('Export message summarises', '2 recipes and 1 tray' in m, m)

        # ── Device B: import into an empty device ──
        B = await device(b)
        m = await import_file(B, path)
        check('Import adds recipes and tray', '2 new recipes' in m and '1 new tray' in m, m)
        check('Imported recipes listed', await recipe_names(B) == ['Party focaccia', 'Plain loaves'])
        await load(B, 'Party focaccia')
        check('Imported recipe gives the same quantities', await total(B) == focaccia_total, (await total(B), focaccia_total))
        bid = await B.evaluate("state.bowls[0].id")
        check('Imported recipe uses the imported tray', 'Big tray' in await B.text_content(f'#b-tray-{bid} option:checked'))

        m = await import_file(B, path)
        check('Re-importing the same file changes nothing', m.startswith('Nothing new'), m)

        # ── Newer version wins, both directions ──
        await load(B, 'Plain loaves')
        bid = await B.evaluate("state.bowls[0].id")
        await B.fill(f'#b-count-{bid}', '6'); await save_recipe(B, 'Plain loaves')
        m = await import_file(B, path)
        check('Older file does not overwrite a newer recipe', m.startswith('Nothing new'), m)
        await load(B, 'Plain loaves')
        check('Newer recipe still in place', await B.input_value(f'#b-count-{await B.evaluate("state.bowls[0].id")}') == '6')

        await load(A, 'Party focaccia')
        aid = await A.evaluate("state.bowls[0].id")
        await A.fill(f'#b-count-{aid}', '3'); await save_recipe(A, 'Party focaccia')
        d2 = Path(tmp) / 'second'; d2.mkdir()
        path2, _ = await export(A, d2)
        m = await import_file(B, path2)
        check('Newer file updates the older recipe', '1 recipe updated' in m, m)
        await load(B, 'Party focaccia')
        check('Updated recipe has the new values', await B.input_value(f'#b-count-{await B.evaluate("state.bowls[0].id")}') == '3')

        # ── Same tray name on the receiving device: no duplicate tray ──
        C = await device(b)
        await make_focaccia_with_tray(C)           # C already has its own "Big tray"
        c_tray_id = await C.evaluate("savedTrays()[0].id")
        m = await import_file(C, path)
        check('Same-named tray not duplicated', await C.evaluate("savedTrays().length") == 1 and 'new tray' not in m, m)
        await load(C, 'Party focaccia')
        check('Recipe points at the existing tray', await C.evaluate("state.bowls[0].tray.sel") == c_tray_id)

        # ── Bad files are rejected and change nothing ──
        bad1 = Path(tmp) / 'notes.json'; bad1.write_text('this is not json')
        bad2 = Path(tmp) / 'other.json'; bad2.write_text(json.dumps({'hello': 'world'}))
        before = await recipe_names(C)
        for bad in (bad1, bad2):
            m = await import_file(C, bad)
            check(f'Rejects {bad.name}', 'isn’t a recipes export' in m, m)
        check('Bad files change nothing', await recipe_names(C) == before)

        # ── Share link: copy on A, open on a new device D ──
        await A.click('#recipes-btn')
        await A.click('.rcp-item:has(.rcp-name:text-is("Party focaccia")) button:has-text("Link")')
        link = await A.evaluate("window.__copied")
        check('Link copied', link and '#recipe=' in link and 'copied' in await msg(A), (link or '')[:80])
        check('Link is a reasonable length', link and len(link) < 2500, len(link or ''))
        await A.click('.dlg-x')

        D = await device(b)
        await D.goto(link)
        check('Opening a link shows the shared recipe', await D.is_visible('.rcp-incoming') and 'Party focaccia' in await D.text_content('.rcp-incoming'))
        check('Link removed from the address bar', '#recipe=' not in D.url, D.url)
        await D.click('.rcp-incoming button:has-text("Open and save it")')
        check('Shared recipe opened with same quantities', await total(D) == await total(A), (await total(D), await total(A)))
        check('Shared recipe saved', await recipe_names(D) == ['Party focaccia'])
        check('Toolbar shows the shared recipe name', 'Party focaccia' in await D.text_content('#recipes-btn'))

        await D.goto(link)
        await D.click('.rcp-incoming button:has-text("Open and save it")')
        check('Opening the same link again does not duplicate', await recipe_names(D) == ['Party focaccia'], await recipe_names(D))

        did = await D.evaluate("state.bowls[0].id")
        await D.fill(f'#b-count-{did}', '9'); await save_recipe(D, 'Party focaccia')
        await D.goto(link)
        await D.click('.rcp-incoming button:has-text("Open and save it")')
        check('Different recipe with the same name is kept as (2)', await recipe_names(D) == ['Party focaccia', 'Party focaccia (2)'], await recipe_names(D))
        await load(D, 'Party focaccia')
        check('Own recipe untouched', await D.input_value(f'#b-count-{await D.evaluate("state.bowls[0].id")}') == '9')

        await D.goto(link)
        await D.click('.rcp-incoming button:has-text("Not now")')
        check('"Not now" leaves current settings alone', await D.input_value(f'#b-count-{await D.evaluate("state.bowls[0].id")}') == '9')

        await D.goto(PAGE + '#recipe=abc$$broken')
        check('Damaged link explains itself', 'damaged' in await D.text_content('#rcp-incoming'))
        await D.goto(PAGE + '#recipe=' + 'eyJmb28iOjF9')   # valid base64 of {"foo":1}
        check('Unrelated link data rejected', 'damaged' in await D.text_content('#rcp-incoming'))

        # ── Copying blocked: link shown to copy by hand ──
        E = await device(b, CLIPBOARD_FAIL)
        await save_recipe(E, 'Test')
        await E.click('#recipes-btn'); await E.click('.rcp-item button:has-text("Link")')
        check('Copy blocked → link shown in a box', await E.is_visible('#rcp-linkbox') and '#recipe=' in await E.input_value('#rcp-linkbox-input'))

        # ── Hydration/oil and blend survive a link ──
        F = await device(b)
        await F.click('#btn-advanced'); await F.click('#btn-type-focaccia')
        await F.click('label:has(#oil-on)'); await F.fill('#oil-pct', '6')
        await F.fill('#fb-white', '80'); await F.fill('#fb-ww', '20')
        await save_recipe(F, 'Wholemeal focaccia')
        ftotal = await total(F)
        await F.click('#recipes-btn'); await F.click('.rcp-item button:has-text("Link")')
        flink = await F.evaluate("window.__copied")
        G = await device(b)
        await G.goto(flink); await G.click('.rcp-incoming button:has-text("Open and save it")')
        check('Advanced settings, oil and blend survive a link', await total(G) == ftotal and await G.input_value('#oil-pct') == '6' and await G.input_value('#fb-ww') == '20',
              (await total(G), ftotal))

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
