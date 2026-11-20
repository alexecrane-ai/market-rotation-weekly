# Market Rotation Weekly

A weekly picture of where money is moving in the US stock market: the big indexes, the 11 sector funds, how fast money is rotating between them, risk gauges, rates, the dollar, gold, oil and the VIX, and a "regime watch" on whether rates stay high or fall.

**Report:** https://alexecrane-ai.github.io/market-rotation-weekly/

Runs automatically every Sunday at 6:00pm New York time (GitHub Actions).
To refresh on demand, open **Actions → Market Rotation Weekly → Run workflow** (also works in the GitHub mobile app).

Run it locally (standard library only):

```
python3 macro.py --out macro.json
python3 dashboard_export.py macro.json data
python3 build_page.py
```

Each week's snapshot is kept in `history/`. Upcoming dates live in the `EVENTS` list in `dashboard_export.py`.

Describes past prices only, not a forecast and not financial advice.
