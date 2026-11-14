"""Shared helpers for the calculator and guide tests."""
import os, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGE = (ROOT / 'sourdough-calculator.html').as_uri()
GUIDE = (ROOT / 'guide.html').as_uri()
BASE = ROOT.as_uri() + '/'

def _chrome():
    # Use installed Chrome if present, otherwise Playwright's bundled Chromium
    env = os.environ.get('CHROME_PATH')
    if env: return env
    for name in ('google-chrome', 'chromium', 'chromium-browser'):
        p = shutil.which(name)
        if p: return p
    mac = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    return mac if os.path.exists(mac) else None

async def browser(p):
    exe = _chrome()
    return await p.chromium.launch(**({'executable_path': exe} if exe else {}), args=['--no-sandbox'])

async def fresh_page(b, errs, **opts):
    """A page in a new browser context, so saved settings start empty."""
    ctx = await b.new_context(**opts)
    pg = await ctx.new_page()
    pg.on('pageerror', lambda e: errs.append(str(e)))
    return pg

async def launch(p, **page_opts):
    b = await browser(p)
    errs = []
    pg = await fresh_page(b, errs, **page_opts)
    return b, pg, errs
