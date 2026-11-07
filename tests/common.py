"""Shared helpers for the calculator tests."""
import os, shutil
from pathlib import Path

PAGE = (Path(__file__).resolve().parent.parent / 'sourdough-calculator.html').as_uri()

def _chrome():
    # Use installed Chrome if present, otherwise Playwright's bundled Chromium
    env = os.environ.get('CHROME_PATH')
    if env: return env
    for name in ('google-chrome', 'chromium', 'chromium-browser'):
        p = shutil.which(name)
        if p: return p
    mac = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    return mac if os.path.exists(mac) else None

async def launch(p, **page_opts):
    exe = _chrome()
    b = await p.chromium.launch(**({'executable_path': exe} if exe else {}), args=['--no-sandbox'])
    pg = await b.new_page(**page_opts)
    errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    return b, pg, errs
