# Calculator tests

Automated checks for `sourdough-calculator.html`. They open the real page in headless Chrome, so they test exactly what people use.

- **test_math.py**: 120 random Simple and 120 random Advanced recipes. Every ingredient is checked against an independent baker's-percentage calculation, and hydration, salt and levain are recovered from the displayed grams. Also checks flour blend splits (% of total flour) and the "All bowls" full-bake column.
- **test_state.py**: interaction checks. Mix-ins survive adding/removing bowls and switching bread type, labels match the mode, blank inputs fall back sensibly, and the guide link carries the recipe.

## Run

```
pip install playwright
python3 -m playwright install chromium   # skip if Google Chrome is installed
python3 tests/test_math.py
python3 tests/test_state.py
```

Each prints its failures and exits with code 1 if anything fails. Set `CHROME_PATH` to use a specific browser.
