#!/usr/bin/env python3
"""trader-macro: a weekly-style picture of where money is moving.

Reads free Yahoo daily closes (one year) for the big indexes, the 11 SPDR
sector funds, semiconductors, international and emerging-market stocks, bonds, gold, the dollar, the VIX and the 10-year
yield, and prints:

  * each index's trend: vs its 50- and 200-day averages, distance from its
    1-year high, and a plain label (near high / pullback / correction / bear)
  * sector rotation: every sector ranked by its return minus the S&P 500's
    over 1 and 3 months, with the leaders and laggards
  * risk gauges: ratios that rise when investors lean "risk on" and fall when
    they lean "risk off" (discretionary vs staples, small vs large, equal vs
    cap weight, semis vs S&P, stocks vs bonds)
  * breadth proxy: how many of the 11 sectors are above their 50/200-day avg

It describes; it never predicts and never says what to buy.
Standard library only. Writes trader/macro.json unless --no-write.
"""
import argparse, json, math, os, sys, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timezone

UA = "Mozilla/5.0 (compatible; trader-macro/1.0)"

INDEXES = {"SPY": "S&P 500", "QQQ": "Nasdaq 100", "IWM": "Russell 2000 (small caps)",
           "DIA": "Dow 30", "RSP": "S&P 500 equal-weight"}
SECTORS = {"XLK": "Tech", "XLC": "Communication", "XLY": "Consumer discretionary",
           "XLF": "Financials", "XLI": "Industrials", "XLE": "Energy", "XLB": "Materials",
           "XLV": "Health care", "XLP": "Consumer staples", "XLU": "Utilities",
           "XLRE": "Real estate"}
EXTRA = {"SMH": "Semiconductors"}
# regions: tracked like a sector fund (rotation map, speed, flags) but kept out of
# the 11-sector ranking and the breadth count
INTL = {"VXUS": "International (ex-US)", "VWO": "Emerging markets"}
CROSS = {"TLT": "Long Treasuries (20y+)", "GLD": "Gold", "UUP": "US dollar", "USO": "Oil (WTI crude fund)",
         "^VIX": "VIX (fear gauge)", "^TNX": "10-year yield (%)"}
# ratio: (numerator, denominator, what a rising ratio usually means)
RATIOS = [("XLY", "XLP", "Discretionary vs staples", "risk on"),
          ("IWM", "SPY", "Small vs large caps", "risk on / broadening"),
          ("RSP", "SPY", "Equal vs cap weight", "broadening (average stock beating the giants)"),
          ("SMH", "SPY", "Semis vs S&P 500", "risk on (growth leading)"),
          ("SPY", "TLT", "Stocks vs long bonds", "risk on"),
          ("XLV", "SPY", "Health care vs S&P 500", "defensive")]

VOLS = {}  # symbol -> {timestamp: dollar volume}
LOOKBACK = {"1d": 1, "1w": 5, "1m": 21, "3m": 63, "6m": 126}


def fetch(sym, offline=None):
    if offline:
        path = os.path.join(offline, sym.replace("^", "_") + ".json")
        d = json.load(open(path))
    else:
        d, last = None, None
        # query2 first, query1 on 429/5xx; one more round after a pause
        for attempt in range(2):
            for host in ("query2", "query1"):
                u = (f"https://{host}.finance.yahoo.com/v8/finance/chart/"
                     f"{urllib.parse.quote(sym)}?range=1y&interval=1d")
                req = urllib.request.Request(u, headers={"User-Agent": UA, "Accept": "application/json"})
                try:
                    d = json.load(urllib.request.urlopen(req, timeout=20))
                    break
                except urllib.error.HTTPError as e:
                    last = e
                    if e.code != 429 and e.code < 500:
                        raise
            if d is not None:
                break
            time.sleep(5)
        if d is None:
            raise last
    res = d["chart"]["result"][0]
    ts = res["timestamp"]
    q = res["indicators"]["quote"][0]
    cl, vo = q["close"], q.get("volume") or [None] * len(ts)
    pts = [(t, c) for t, c in zip(ts, cl) if c is not None]
    VOLS[sym] = {t: c * v for t, c, v in zip(ts, cl, vo) if c is not None and v}
    if len(pts) < 60:
        raise ValueError(f"only {len(pts)} daily closes")
    return pts


def stats(pts):
    c = [p[1] for p in pts]
    last = c[-1]
    out = {"last": round(last, 2),
           "as_of": datetime.fromtimestamp(pts[-1][0], timezone.utc).strftime("%Y-%m-%d")}
    for k, n in LOOKBACK.items():
        out[k] = round((last / c[-1 - n] - 1) * 100, 2) if len(c) > n else None
    # year to date: from the last close of the previous year
    yr = datetime.fromtimestamp(pts[-1][0], timezone.utc).year
    prev = [cl for t, cl in pts if datetime.fromtimestamp(t, timezone.utc).year < yr]
    out["ytd"] = round((last / prev[-1] - 1) * 100, 2) if prev else None
    ma50 = sum(c[-50:]) / 50
    ma200 = sum(c[-200:]) / min(200, len(c))
    hi, lo = max(c[-252:]), min(c[-252:])
    out.update(ma50=round(ma50, 2), ma200=round(ma200, 2),
               vs50=round((last / ma50 - 1) * 100, 2), vs200=round((last / ma200 - 1) * 100, 2),
               off_high=round((last / hi - 1) * 100, 2), off_low=round((last / lo - 1) * 100, 2),
               ma50_above_ma200=ma50 > ma200, short_history=len(c) < 200)
    return out


def drawdown_label(off_high):
    if off_high > -3:
        return "near its high"
    if off_high > -10:
        return "pullback (3-10% off high)"
    if off_high > -20:
        return "correction (10-20% off high)"
    return "bear-market territory (20%+ off high)"


def trend_label(s):
    a50, a200 = s["vs50"] > 0, s["vs200"] > 0
    if a50 and a200:
        return "uptrend (above 50d and 200d)"
    if not a50 and a200:
        return "dip inside uptrend (below 50d, above 200d)"
    if a50 and not a200:
        return "bouncing (above 50d, below 200d)"
    return "downtrend (below 50d and 200d)"


def ratio_change(a, b, n):
    da = {t: c for t, c in a}
    common = [(t, da[t], c) for t, c in b if t in da]
    if len(common) <= n:
        return None
    r_now = common[-1][1] / common[-1][2]
    r_then = common[-1 - n][1] / common[-1 - n][2]
    return round((r_now / r_then - 1) * 100, 2)


def flow(sec, spy, vols):
    """Rotation map point, tail, speed and volume for one fund against SPY.

    x = relative strength vs its own 50-day average (100 = average; above
        100 the fund has been beating the S&P 500 lately)
    y = momentum: change in x over the last 5 trading days (above 100 = x is rising)
    """
    ds = dict(spy)
    common = [(t, c, ds[t]) for t, c in sec if t in ds]
    if len(common) < 80:
        return None
    rs = [c / p for _, c, p in common]
    n = len(rs)

    def x_at(i):
        w = rs[i - 49:i + 1]
        return 100 * rs[i] / (sum(w) / len(w))

    def y_at(i):
        return 100 + (x_at(i) - x_at(i - 5))

    def rel(a, b):  # relative return in % points between indexes a < b
        return (common[b][1] / common[a][1] - common[b][2] / common[a][2]) * 100

    tail = []
    for k in range(4, -1, -1):  # 4 weeks ago ... now
        i = n - 1 - 5 * k
        tail.append({"weeks_ago": k, "date": datetime.fromtimestamp(common[i][0], timezone.utc).strftime("%Y-%m-%d"),
                     "x": round(x_at(i), 2), "y": round(y_at(i), 2)})
    x, y = tail[-1]["x"], tail[-1]["y"]
    quad = ("leading" if y >= 100 else "weakening") if x >= 100 else ("improving" if y >= 100 else "lagging")
    w1 = rel(n - 6, n - 1)
    prev = rel(n - 66, n - 6) / 12 if n > 66 else None  # average week over the 12 before
    a = abs(w1)
    speed = "fast" if a >= 2 else "moderate" if a >= 0.75 else "slow"
    direction = "into" if w1 > 0 else "out of"
    if prev is None or abs(prev) < 0.1:
        change = "new move"
    elif (w1 > 0) != (prev > 0):
        change = "reversing"
    elif a > 1.5 * abs(prev):
        change = "speeding up"
    elif a < 0.67 * abs(prev):
        change = "slowing"
    else:
        change = "steady"
    # skip today's bar while the session is still running: its volume is partial
    done = common[:-1] if time.time() < common[-1][0] + 6.75 * 3600 else common
    dv = [vols.get(t) for t, _, _ in done[-50:]]
    dv = [v for v in dv if v]
    vr = (sum(dv[-5:]) / 5) / (sum(dv) / len(dv)) if len(dv) >= 20 else None
    vol = None if vr is None else "heavy" if vr >= 1.3 else "light" if vr <= 0.8 else "normal"
    move = ((tail[-1]["x"] - tail[-2]["x"]) ** 2 + (tail[-1]["y"] - tail[-2]["y"]) ** 2) ** 0.5
    return {"x": x, "y": y, "quadrant": quad, "tail": tail, "rel_1w": round(w1, 2),
            "avg_week_before": None if prev is None else round(prev, 2), "speed": speed,
            "direction": direction, "change": change, "map_move_1w": round(move, 2),
            "volume_ratio": None if vr is None else round(vr, 2), "volume": vol}


def make_flags(data, flows, pattern):
    """Rule-based patterns worth researching. Descriptions, not recommendations."""
    out = []
    allf = {**data["sectors"], **data["extra"], **data.get("intl", {})}
    for sym, st in allf.items():
        fl = flows.get(sym)
        if not fl:
            continue
        nm, q, r3, oh = st["name"], fl["quadrant"], st["rel_3m"] or 0, st["off_high"]
        area = "region" if sym in INTL else "sector"
        if oh <= -10 and q == "improving":
            out.append({"sym": sym, "name": nm, "flag": "Beaten down, starting to turn",
                        "shows": f"{abs(oh):.0f}% below its 1-year high, but gaining on the S&P 500 this week ({fl['rel_1w']:+.1f} pts).",
                        "why_look": "Some investors research areas that fell hard once they start to recover.",
                        "risk": "A one-week bounce often fails; the longer downtrend is still in place."})
        elif oh <= -10 and q == "lagging":
            out.append({"sym": sym, "name": nm, "flag": "Correction, still falling behind",
                        "shows": f"{abs(oh):.0f}% below its 1-year high and still losing ground to the S&P 500.",
                        "why_look": "Worth re-checking the reasons if you already own it or plan to.",
                        "risk": f"Buying a falling {area} early is a common way to lose money; nothing here says it has bottomed."})
        if r3 >= 5 and q == "weakening":
            out.append({"sym": sym, "name": nm, "flag": "Leader losing speed",
                        "shows": f"Beat the S&P 500 by {r3:.1f} pts over 3 months, but that lead stopped growing this week.",
                        "why_look": "A fading leader is where rotation out often begins; watch whether it keeps fading.",
                        "risk": "Leaders often pause and then resume; one week is not a trend."})
        if r3 >= 2 and q == "leading" and fl["speed"] in ("fast", "moderate") and fl["direction"] == "into":
            out.append({"sym": sym, "name": nm, "flag": "Strong and still gaining",
                        "shows": f"Ahead of the S&P 500 over 3 months ({r3:+.1f} pts) and money moved in {'quickly' if fl['speed'] == 'fast' else 'at a moderate pace'} this week.",
                        "why_look": "Momentum: money is still arriving.",
                        "risk": "Arriving late to a strong move risks buying near a peak."})
        if pattern == "defensive" and sym in ("XLF", "XLI", "XLY", "XLK", "XLC") and fl["rel_1w"] <= 0.5 and q in ("lagging", "weakening"):
            out.append({"sym": sym, "name": nm, "flag": "Left out of the move",
                        "shows": f"Money is leaning defensive, and this cyclical sector saw little inflow this week ({fl['rel_1w']:+.1f} pts).",
                        "why_look": "Shows where money is not going right now; useful to know before adding exposure here.",
                        "risk": "Cyclical sectors can turn quickly if the mood changes."})
        if fl["volume"] == "heavy":
            out.append({"sym": sym, "name": nm, "flag": "Heavy trading",
                        "shows": f"Dollar volume this week was {fl['volume_ratio']:.1f}x its 50-day average, while money moved {fl['direction']} it.",
                        "why_look": "Heavy volume means big players are active; check the news for why.",
                        "risk": "Heavy volume can mean buying or selling; it does not tell you which way it goes next."})
    return out


def f(x, w=7, d=1):
    return f"{'n/a':>{w}}" if x is None else f"{x:>{w}.{d}f}"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true", help="print the JSON instead of the report")
    ap.add_argument("--no-write", action="store_true", help="do not write trader/macro.json")
    ap.add_argument("--out", default="trader/macro.json")
    ap.add_argument("--offline", help="folder of saved Yahoo chart JSON files named <SYM>.json (^ as _)")
    a = ap.parse_args()

    groups = {"indexes": INDEXES, "sectors": SECTORS, "extra": EXTRA, "intl": INTL, "cross_asset": CROSS}
    raw, data, failed = {}, {}, {}
    for g, syms in groups.items():
        data[g] = {}
        for s, name in syms.items():
            try:
                raw[s] = fetch(s, a.offline)
                st = stats(raw[s])
                st["name"] = name
                data[g][s] = st
            except Exception as e:
                failed[s] = str(e)[:120]
            if not a.offline:
                time.sleep(0.3)

    if "SPY" not in data["indexes"]:
        print("Could not read SPY; nothing to compare against.", file=sys.stderr)
        return 2
    spy = data["indexes"]["SPY"]

    for g in ("indexes", "sectors", "extra", "intl"):
        for s, st in data[g].items():
            st["trend"] = trend_label(st)
            st["drawdown"] = drawdown_label(st["off_high"])
            st["rel_1m"] = None if st["1m"] is None else round(st["1m"] - spy["1m"], 2)
            st["rel_3m"] = None if st["3m"] is None else round(st["3m"] - spy["3m"], 2)

    ranked = sorted(data["sectors"].items(), key=lambda kv: kv[1]["rel_3m"] or -1e9, reverse=True)
    sec = data["sectors"]
    breadth = {"sectors": len(sec),
               "above_50d": sum(1 for s in sec.values() if s["vs50"] > 0),
               "above_200d": sum(1 for s in sec.values() if s["vs200"] > 0)}

    flows = {}
    for g in ("sectors", "extra", "intl"):
        for sym in data[g]:
            fl = flow(raw[sym], raw["SPY"], VOLS.get(sym, {}))
            if fl:
                fl["name"] = data[g][sym]["name"]
                flows[sym] = fl

    ratios = []
    for n, d, label, meaning in RATIOS:
        if n in raw and d in raw:
            ratios.append({"pair": f"{n}/{d}", "label": label, "rising_means": meaning,
                           "1m": ratio_change(raw[n], raw[d], 21), "3m": ratio_change(raw[n], raw[d], 63)})

    defensive = {"XLP", "XLV", "XLU"}
    top3 = [s for s, _ in ranked[:3]]
    n_def_top = sum(1 for s in top3 if s in defensive)

    flags = make_flags(data, flows, "defensive" if n_def_top >= 2 else "cyclical")

    report = {"created_by": "trader-macro", "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "as_of": spy["as_of"], "source": "Yahoo Finance daily closes (free, unofficial, can lag)",
              **data, "sector_rank_3m": [s for s, _ in ranked], "breadth": breadth,
              "ratios": ratios, "flows": flows, "flags": flags, "defensive_in_top3": n_def_top, "failed": failed,
              "note": "Describes past prices only. Not a forecast, not advice."}

    if not a.no_write:
        os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
        json.dump(report, open(a.out, "w"), indent=2)

    if a.json:
        print(json.dumps(report, indent=2))
        return 0

    P = print
    P(f"MACRO SNAPSHOT  closes as of {spy['as_of']}  (Yahoo daily, free, can lag)\n")
    P("INDEXES")
    P(f"  {'sym':5} {'name':27}{'last':>9}{'1w':>7}{'1m':>7}{'3m':>7}{'vs50d':>7}{'vs200d':>7}{'offHi':>7}  status")
    for s, st in data["indexes"].items():
        P(f"  {s:5} {st['name'][:26]:27}{st['last']:9.2f}{f(st['1w'])}{f(st['1m'])}{f(st['3m'])}"
          f"{f(st['vs50'])}{f(st['vs200'])}{f(st['off_high'])}  {st['drawdown']}; {st['trend']}")

    P("\nSECTOR ROTATION  (ranked by 3-month return minus the S&P 500's, in % points)")
    P(f"  {'sym':5} {'name':24}{'1m rel':>8}{'3m rel':>8}{'6m':>7}{'ytd':>7}{'vs200d':>7}{'offHi':>7}")
    for s, st in ranked:
        P(f"  {s:5} {st['name'][:23]:24}{f(st['rel_1m'],8)}{f(st['rel_3m'],8)}{f(st['6m'])}{f(st['ytd'])}{f(st['vs200'])}{f(st['off_high'])}")
    for s, st in data["extra"].items():
        P(f"  {s:5} {st['name'][:23]:24}{f(st['rel_1m'],8)}{f(st['rel_3m'],8)}{f(st['6m'])}{f(st['ytd'])}{f(st['vs200'])}{f(st['off_high'])}  (not a sector fund)")
    for s, st in data["intl"].items():
        P(f"  {s:5} {st['name'][:23]:24}{f(st['rel_1m'],8)}{f(st['rel_3m'],8)}{f(st['6m'])}{f(st['ytd'])}{f(st['vs200'])}{f(st['off_high'])}  (not a sector fund: region)")
    P(f"  Leaders: {', '.join(sec[s]['name'] for s, _ in ranked[:3])}.  "
      f"Laggards: {', '.join(sec[s]['name'] for s, _ in ranked[-3:])}.")
    if n_def_top >= 2:
        P("  Defensive sectors (staples, health care, utilities) hold 2+ of the top 3 spots: a cautious pattern.")

    P(f"\nBREADTH PROXY  {breadth['above_50d']}/{breadth['sectors']} sectors above their 50-day avg, "
      f"{breadth['above_200d']}/{breadth['sectors']} above their 200-day avg.")

    P("\nRISK GAUGES  (change in the ratio, %)")
    P(f"  {'pair':9} {'what':27}{'1m':>7}{'3m':>7}  rising usually means")
    for r in ratios:
        P(f"  {r['pair']:9} {r['label'][:26]:27}{f(r['1m'])}{f(r['3m'])}  {r['rising_means']}")

    P("\nMONEY FLOW SPEED  (this week vs the S&P 500, fastest first)")
    P(f"  {'sym':5} {'name':24}{'1w rel':>8}  {'speed / direction':24}{'vs past weeks':15}{'map':11}volume")
    for sym, fl in sorted(flows.items(), key=lambda kv: -abs(kv[1]["rel_1w"])):
        P(f"  {sym:5} {fl['name'][:23]:24}{f(fl['rel_1w'],8)}  {(fl['speed'] + ' ' + fl['direction']):24}{fl['change']:15}{fl['quadrant']:11}{fl['volume'] or 'n/a'}{'  (not a sector fund)' if sym in EXTRA or sym in INTL else ''}")
    P("  map: leading = beating the S&P and gaining; weakening = beating it but fading;")
    P("       lagging = trailing and still losing ground; improving = trailing but catching up.")

    P("\nWHAT THE DATA FLAGS THIS WEEK  (rule-based patterns to research, not recommendations)")
    for fg in flags:
        P(f"  {fg['sym']:5} {fg['flag']}: {fg['shows']}")
        P(f"        Why look: {fg['why_look']}  Risk: {fg['risk']}")
    if not flags:
        P("  Nothing matched the rules this week.")

    P("\nCROSS-ASSET")
    for s, st in data["cross_asset"].items():
        P(f"  {s:5} {st['name'][:26]:27}{st['last']:9.2f}  1m {f(st['1m'],6)}  3m {f(st['3m'],6)}  "
          f"vs200d {f(st['vs200'],6)}  off 1y high {f(st['off_high'],6)}")

    if failed:
        P(f"\nCould not read: {', '.join(f'{k} ({v})' for k, v in failed.items())}")
    if not a.no_write:
        P(f"\nWrote {a.out}.")
    P("Describes past prices only. Not a forecast, not financial advice.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
