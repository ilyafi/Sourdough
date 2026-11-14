# Calculator tests

Automated checks for `sourdough-calculator.html`. They open the real page in headless Chrome, so they test exactly what people use.

- **test_math.py**: 300 random recipes across loaf, baguette and focaccia, Simple and Advanced: trays and thickness, olive oil, flour blends, mix-ins and per-bowl levain. Every ingredient is checked against an independent baker's-percentage calculation, plus blend splits (% of total flour) and the "All bowls" full-bake column.
- **test_guide.py**: builds random recipes in the calculator, follows its guide link and checks the guide shows the same quantities for every bowl (including olive oil and tray oil for focaccia), a correctly sized levain build, and only the right steps for the bread type. Also checks each tab's default recipe, old-style guide links and broken links.
- **test_state.py**: interaction checks driven like a person would: mix-ins survive re-renders, focaccia trays (presets, custom, saved trays) and thickness, olive oil, the page remembering the last bake after a reload, saving/loading/replacing/deleting named recipes, no sideways scrolling on a phone, and the page still working when browser storage is blocked or corrupt.

## Run

```
pip install playwright
python3 -m playwright install chromium   # skip if Google Chrome is installed
python3 tests/test_math.py
python3 tests/test_state.py
python3 tests/test_guide.py
```

Each prints its failures and exits with code 1 if anything fails. Set `CHROME_PATH` to use a specific browser.
