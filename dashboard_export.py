#!/usr/bin/env python3
"""Turn trader/macro.json into the row files the Market Rotation Weekly
dashboard reads: trader/dashboard/{summary,indexes,sectors,gauges,cross,flow,flowtail,flags,regime,events}.json,
each {"rows": [...], "meta": [...]}. Standard library only. Run after macro.py."""
import json, os, sys

SRC = sys.argv[1] if len(sys.argv) > 1 else "trader/macro.json"
OUT = sys.argv[2] if len(sys.argv) > 2 else "trader/dashboard"
DEFENSIVE = {"XLP", "XLV", "XLU"}

m = json.load(open(SRC))
os.makedirs(OUT, exist_ok=True)
meta = [{"label": "Source", "value": m["source"]},
        {"label": "Closes as of", "value": m["as_of"]},
        {"label": "Built", "value": m["created_at"]},
        {"label": "Made by", "value": "trader-macro/macro.py, then dashboard_export.py"}]


def r(x):
    return None if x is None else round(x, 2)


def write(name, rows):
    json.dump({"rows": rows, "meta": meta}, open(os.path.join(OUT, name + ".json"), "w"), indent=1)


idx = [{"sym": s, "name": v["name"], "last": r(v["last"]), "w1": r(v["1w"]), "m1": r(v["1m"]),
        "m3": r(v["3m"]), "ytd": r(v.get("ytd")), "vs50": r(v["vs50"]), "vs200": r(v["vs200"]),
        "off_high": r(v["off_high"]), "drawdown": v["drawdown"], "trend": v["trend"]}
       for s, v in m["indexes"].items()]
write("indexes", idx)

sec = []
for s, v in m["sectors"].items():
    sec.append({"sym": s, "sector": v["name"], "ytd": r(v.get("ytd")), "w1": r(v["1w"]),
                "rel_1m": r(v["rel_1m"]), "rel_3m": r(v["rel_3m"]), "m6": r(v["6m"]),
                "vs200": r(v["vs200"]), "off_high": r(v["off_high"]),
                "group": "defensive" if s in DEFENSIVE else "cyclical",
                "rank_3m": m["sector_rank_3m"].index(s) + 1})
sec.sort(key=lambda x: x["rank_3m"])
write("sectors", sec)

write("gauges", [{"pair": g["pair"], "label": g["label"], "rising_means": g["rising_means"],
                  "m1": r(g["1m"]), "m3": r(g["3m"])} for g in m["ratios"]])

write("cross", [{"sym": s, "name": v["name"], "last": r(v["last"]), "w1": r(v["1w"]),
                 "m1": r(v["1m"]), "m3": r(v["3m"]), "off_high": r(v["off_high"])}
                for s, v in m["cross_asset"].items()])

fl = m.get("flows", {})
allf = {**m["sectors"], **m.get("extra", {}), **m.get("intl", {})}
INTL = set(m.get("intl", {}))


def group(s):
    return "defensive" if s in DEFENSIVE else "semis" if s == "SMH" else "intl" if s in INTL else "cyclical"


write("flow", [{"sym": s, "sector": v["name"], "group": group(s),
                "x": v["x"], "y": v["y"], "quadrant": v["quadrant"], "rel_1w": v["rel_1w"],
                "avg_week_before": v["avg_week_before"], "speed": v["speed"], "direction": v["direction"],
                "change": v["change"], "volume": v["volume"], "volume_ratio": v["volume_ratio"],
                "rel_3m": r(allf[s].get("rel_3m"))}
               for s, v in sorted(fl.items(), key=lambda kv: -abs(kv[1]["rel_1w"]))])
write("flowtail", [{"sym": s, "sector": v["name"], "weeks_ago": p["weeks_ago"], "date": p["date"], "x": p["x"], "y": p["y"]}
                   for s, v in fl.items() for p in v["tail"]])
write("flags", [{"id": f"{i + 1}", **f} for i, f in enumerate(m.get("flags", []))])

# Regime watch: which of two outlooks the past month's prices lean toward.
#   "rates stay high": yields, oil and the dollar rising; defensive and value sectors ahead
#   "rates and oil fall": the reverse, which tends to help growth stocks
HIGH, FALL, MIXED = "rates stay high", "rates and oil fall", "no clear lean"
ca, sc, ix = m["cross_asset"], m["sectors"], m["indexes"]


def g(group, s, k):
    return (group.get(s) or {}).get(k)


def avg(vals):
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else None


def diff(a, b):
    return None if a is None or b is None else a - b


def lean(v, cut, up_means):
    if v is None:
        return "n/a"
    if v >= cut:
        return up_means
    if v <= -cut:
        return FALL if up_means == HIGH else HIGH
    return MIXED


def tnx_pts(n):  # change in the 10-year yield in percentage points over n
    last, pct = g(ca, "^TNX", "last"), g(ca, "^TNX", n)
    return None if last is None or pct is None else last - last / (1 + pct / 100)


SIG = [
    ("tnx", "10-year Treasury yield", "change in % points", tnx_pts("1m"), tnx_pts("3m"), 0.10, HIGH,
     "Higher yields mean borrowing stays expensive."),
    ("tlt", "Long Treasury bonds (TLT)", "price change, %", g(ca, "TLT", "1m"), g(ca, "TLT", "3m"), 1.0, FALL,
     "Bond prices rise when yields fall."),
    ("oil", "Oil (USO)", "price change, %", g(ca, "USO", "1m"), g(ca, "USO", "3m"), 3.0, HIGH,
     "Rising oil feeds inflation, which keeps rates up."),
    ("usd", "US dollar (UUP)", "price change, %", g(ca, "UUP", "1m"), g(ca, "UUP", "3m"), 1.0, HIGH,
     "A firm dollar often goes with higher US rates."),
    ("defgrowth", "Defensive sectors vs Nasdaq 100", "staples, health care, utilities minus QQQ, % points",
     diff(avg([g(sc, s, "1m") for s in ("XLP", "XLV", "XLU")]), g(ix, "QQQ", "1m")),
     diff(avg([g(sc, s, "3m") for s in ("XLP", "XLV", "XLU")]), g(ix, "QQQ", "3m")), 2.0, HIGH,
     "Defensive stocks ahead of growth stocks is a cautious pattern."),
    ("valuetech", "Financials and energy vs tech", "XLF and XLE minus XLK, % points",
     diff(avg([g(sc, s, "1m") for s in ("XLF", "XLE")]), g(sc, "XLK", "1m")),
     diff(avg([g(sc, s, "3m") for s in ("XLF", "XLE")]), g(sc, "XLK", "3m")), 2.0, HIGH,
     "Banks and energy tend to do well when rates and oil stay high; tech tends to do well when they fall."),
]
regime = [{"id": i, "signal": nm, "measure": me, "m1": r(v1), "m3": r(v3), "leans": lean(v1, cut, up), "why": why}
          for i, nm, me, v1, v3, cut, up, why in SIG]
write("regime", regime)
n_high = sum(1 for x in regime if x["leans"] == HIGH)
n_fall = sum(1 for x in regime if x["leans"] == FALL)
overall = HIGH if n_high >= n_fall + 2 else FALL if n_fall >= n_high + 2 else MIXED

# dates that can tip the balance (public schedules; keep this list current)
from datetime import date
EVENTS = [("2026-11-17", "nvda", "Nvidia quarterly results (after the close)",
           "The largest AI stock; its results tend to move tech and chip stocks."),
          ("2026-12-09", "fomc", "Federal Reserve rate decision",
           "Whether the Fed raises, holds or cuts rates is the clearest signal of which outlook wins.")]
asof = date.fromisoformat(m["as_of"])
write("events", [{"id": i, "date": d, "event": e, "why": w, "days_away": (date.fromisoformat(d) - asof).days}
                 for d, i, e, w in EVENTS if date.fromisoformat(d) >= asof])

rank = m["sector_rank_3m"]
name = lambda s: m["sectors"][s]["name"]
write("summary", [{"as_of": m["as_of"], "leaders": ", ".join(name(s) for s in rank[:3]),
                   "laggards": ", ".join(name(s) for s in rank[-3:]),
                   "defensive_in_top3": m["defensive_in_top3"],
                   "pattern": "defensive" if m["defensive_in_top3"] >= 2 else "cyclical",
                   "above_50d": m["breadth"]["above_50d"], "above_200d": m["breadth"]["above_200d"],
                   "sectors": m["breadth"]["sectors"],
                   "regime_lean": overall, "regime_high": n_high, "regime_fall": n_fall,
                   "regime_signals": len(regime)}])
print("Wrote", ", ".join(f"{OUT}/{n}.json" for n in ("summary", "indexes", "sectors", "gauges", "cross", "flow", "flowtail", "flags", "regime", "events")))
