#!/usr/bin/env python3
"""Build index.html (the phone page) from the data/*.json files that
dashboard_export.py writes. Standard library only."""
import html, json, os
from datetime import datetime, timezone

DATA = "data"
REPO = os.environ.get("GITHUB_REPOSITORY", "alexecrane-ai/market-rotation-weekly")
REFRESH_URL = f"https://github.com/{REPO}/actions/workflows/weekly.yml"


def load(name):
    with open(os.path.join(DATA, name + ".json")) as f:
        return json.load(f)["rows"]


e = html.escape
summary = load("summary")[0]
indexes, sectors, gauges = load("indexes"), load("sectors"), load("gauges")
cross, flow, flags = load("cross"), load("flow"), load("flags")
regime, events = load("regime"), load("events")


def num(v, d=1, pct=True, sign=True):
    if v is None:
        return "–"
    s = f"{v:+.{d}f}" if sign else f"{v:.{d}f}"
    return s + ("%" if pct else "")


def cls(v):
    return "" if v is None else "pos" if v > 0 else "neg" if v < 0 else ""


def bars(rows, label, value, unit="%", highlight=None):
    """Horizontal bar chart as inline SVG, zero line in the middle of the range."""
    rows = [r for r in rows if r[value] is not None]
    if not rows:
        return "<p class='cap'>No data.</p>"
    lo, hi = min(0, min(r[value] for r in rows)), max(0, max(r[value] for r in rows))
    span = (hi - lo) or 1
    W, LW, VW, H = 600, 170, 64, 26
    plot = W - LW - VW
    zx = LW + (0 - lo) / span * plot
    out = [f"<svg viewBox='0 0 {W} {H * len(rows) + 6}' class='bars' role='img'>"]
    for i, r in enumerate(rows):
        v, y = r[value], i * H + 3
        x0 = zx if v >= 0 else zx + v / span * plot
        w = abs(v) / span * plot
        c = "hl" if highlight and highlight(r) else ("p" if v >= 0 else "n")
        out.append(f"<text x='{LW - 8}' y='{y + 16}' text-anchor='end' class='lbl'>{e(label(r))}</text>"
                   f"<rect x='{x0:.1f}' y='{y + 3}' width='{max(w, 1):.1f}' height='{H - 8}' rx='3' class='b {c}'/>"
                   f"<text x='{W - 4}' y='{y + 16}' text-anchor='end' class='val'>{v:+.1f}{unit}</text>")
    out.append(f"<line x1='{zx:.1f}' x2='{zx:.1f}' y1='0' y2='{H * len(rows) + 6}' class='zero'/></svg>")
    return "".join(out)


def table(head, rows):
    h = "".join(f"<th>{e(c)}</th>" for c in head)
    b = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f"<div class='tw'><table><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table></div>"


def pct_td(v, d=1):
    return f"<span class='{cls(v)}'>{num(v, d)}</span>"


# --- sections ---------------------------------------------------------------
idx_sorted = sorted(indexes, key=lambda r: r["off_high"] or 0)
sec_ytd = sorted(sectors + [{"sector": "S&P 500 (SPY)", "sym": "SPY",
                             "ytd": next((i["ytd"] for i in indexes if i["sym"] == "SPY"), None)}],
                 key=lambda r: -(r["ytd"] or -999))
sec_rel = sorted(sectors, key=lambda r: -(r["rel_3m"] or -999))
fast = [f for f in flow if f["speed"] == "fast"]
fast_txt = ("; ".join(f"{e(f['direction'])} {e(f['sector'])} ({f['rel_1w']:+.1f} pts, {e(f['change'])})"
                      for f in fast[:3]) or "no fast moves this week")
lean = summary["regime_lean"]

events_html = "".join(
    f"<li><b>{e(ev['date'])}</b> ({ev['days_away']} days after the data date): {e(ev['event'])}. "
    f"<span class='muted'>{e(ev['why'])}</span></li>" for ev in events) or \
    "<li class='muted'>No upcoming dates listed: the EVENTS list in dashboard_export.py needs the next ones.</li>"

flag_html = "".join(
    f"<div class='flag'><div class='fh'><b>{e(f['name'])}</b> <span class='tag'>{e(f['sym'])}</span> "
    f"<span class='pill'>{e(f['flag'])}</span></div><p>{e(f['shows'])}</p>"
    f"<p class='muted'><b>Why some look:</b> {e(f['why_look'])}</p>"
    f"<p class='muted'><b>Risk:</b> {e(f['risk'])}</p></div>" for f in flags) or "<p class='muted'>No flags this week.</p>"

page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Market Rotation Weekly</title>
<style>
:root {{ --bg:#f6f7f9; --card:#fff; --ink:#15181d; --muted:#667085; --line:#e4e7ec;
  --pos:#0f8a5f; --neg:#c2352b; --hl:#3559e0; --pill:#eef1f5; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#0f1115; --card:#181b21; --ink:#e8eaee;
  --muted:#98a2b3; --line:#2a2f38; --pos:#3ecf8e; --neg:#ff6b5e; --hl:#7c9bff; --pill:#232832; }} }}
* {{ box-sizing:border-box }}
body {{ margin:0; background:var(--bg); color:var(--ink);
  font:15px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
main {{ max-width:980px; margin:0 auto; padding:24px 16px 48px }}
h1 {{ margin:0 0 4px; font-size:26px }}
.sub {{ color:var(--muted); margin:0 0 20px }} .sub a {{ color:var(--hl); font-weight:600; text-decoration:none }}
.cards {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(150px, 1fr)); gap:12px; margin-bottom:16px }}
.kpi {{ background:var(--card); border:1px solid var(--line); border-radius:14px; padding:14px 16px }}
.kpi .n {{ font-size:12px; color:var(--muted); text-transform:uppercase; letter-spacing:.05em }}
.kpi .v {{ font-size:22px; font-weight:700; margin-top:4px }}
.kpi .s {{ font-size:13px; color:var(--muted) }}
section {{ background:var(--card); border:1px solid var(--line); border-radius:14px; padding:18px; margin-bottom:16px; min-width:0 }}
h2 {{ margin:0 0 6px; font-size:17px }}
.take {{ margin:0 0 12px }} .cap, .muted {{ color:var(--muted); font-size:13px }}
.bars {{ width:100%; height:auto; display:block }}
.bars text {{ font-size:13px; fill:var(--muted) }} .bars .lbl {{ fill:var(--ink) }}
.b.p {{ fill:var(--pos) }} .b.n {{ fill:var(--neg) }} .b.hl {{ fill:var(--hl) }}
.zero {{ stroke:var(--muted); stroke-width:1 }}
.tw {{ overflow-x:auto }}
table {{ width:100%; border-collapse:collapse; font-size:14px; font-variant-numeric:tabular-nums }}
th, td {{ text-align:left; padding:7px 8px; border-bottom:1px solid var(--line); white-space:nowrap }}
th {{ color:var(--muted); font-weight:600; font-size:12px; text-transform:uppercase; letter-spacing:.04em }}
.pos {{ color:var(--pos) }} .neg {{ color:var(--neg) }}
.flag {{ border-top:1px solid var(--line); padding:10px 0 }} .flag p {{ margin:4px 0 }}
.tag {{ color:var(--muted); font-size:12px }}
.pill {{ display:inline-block; font-size:12px; padding:2px 8px; border-radius:999px; background:var(--pill) }}
ul {{ padding-left:20px; margin:6px 0 }} li {{ margin:4px 0 }}
footer {{ color:var(--muted); font-size:13px; margin-top:20px }}
</style></head><body><main>
<h1>Market Rotation Weekly</h1>
<p class="sub">Closes as of {e(summary['as_of'])} · built {datetime.now(timezone.utc):%a %b %d, %H:%M} UTC ·
<a href="{REFRESH_URL}">Refresh now ↻</a></p>

<div class="cards">
 <div class="kpi"><div class="n">Pattern</div><div class="v">{e(summary['pattern'].title())}</div>
  <div class="s">{summary['defensive_in_top3']} of top 3 sectors are defensive</div></div>
 <div class="kpi"><div class="n">Leaders (3 mo)</div><div class="v" style="font-size:15px">{e(summary['leaders'])}</div></div>
 <div class="kpi"><div class="n">Laggards (3 mo)</div><div class="v" style="font-size:15px">{e(summary['laggards'])}</div></div>
 <div class="kpi"><div class="n">Breadth</div><div class="v">{summary['above_200d']}/{summary['sectors']}</div>
  <div class="s">sectors above 200-day avg ({summary['above_50d']} above 50-day)</div></div>
 <div class="kpi"><div class="n">Regime lean</div><div class="v" style="font-size:15px">{e(lean)}</div>
  <div class="s">{summary['regime_high']} say high, {summary['regime_fall']} say fall, of {summary['regime_signals']}</div></div>
</div>

<section><h2>Big indexes: how far below their 1-year high</h2>
<p class="take">0% means at the high. Down 10% is a "correction", down 20% a "bear market".</p>
{bars(idx_sorted, lambda r: r['sym'] + ' · ' + r['name'].split(' (')[0], 'off_high')}
{table(['Index', 'Trend', '1 wk', '1 mo', '3 mo', 'YTD', 'vs 200-day'],
       [[e(r['sym']), e(r['trend']), pct_td(r['w1']), pct_td(r['m1']), pct_td(r['m3']), pct_td(r['ytd']), pct_td(r['vs200'])] for r in indexes])}
</section>

<section><h2>Sector returns this year</h2>
<p class="take">Year-to-date return of each of the 11 sector funds, with the S&P 500 in blue for comparison.</p>
{bars(sec_ytd, lambda r: r['sector'], 'ytd', highlight=lambda r: r['sym'] == 'SPY')}
</section>

<section><h2>Where money moved in the last 3 months</h2>
<p class="take">Each sector's 3-month return minus the S&P 500's, in % points. Above zero = beat the market.
The pattern is <b>{e(summary['pattern'])}</b>: staples, health care and utilities are "defensive" (people buy them when cautious).</p>
{bars(sec_rel, lambda r: r['sector'], 'rel_3m', unit=' pts')}
</section>

<section><h2>How fast money is moving, and where</h2>
<p class="take">Fastest moves this week: {fast_txt}. "Pts" is this week's return minus the S&P 500's.</p>
{table(['Fund', 'Spot', 'This wk', 'Speed', 'Direction', 'Change', 'Volume'],
       [[f"{e(f['sector'])} <span class='tag'>{e(f['sym'])}</span>", e(f['quadrant']), pct_td(f['rel_1w']).replace('%', ' pts'),
         e(f['speed']), e(f['direction']), e(f['change']), e(f['volume'])] for f in flow])}
<p class="cap">Spot: leading (strong and gaining), weakening (strong but fading), lagging (weak and falling), improving (weak but gaining).</p>
</section>

<section><h2>Risk gauges</h2>
<p class="take">Ratios between two funds. When a ratio rises, it usually means what the last column says.</p>
{table(['Gauge', '1 mo', '3 mo', 'Rising means'],
       [[e(g['label']), pct_td(g['m1']), pct_td(g['m3']), e(g['rising_means'])] for g in gauges])}
</section>

<section><h2>Rates, dollar, gold and fear</h2>
{table(['Asset', 'Last', '1 wk', '1 mo', '3 mo', 'From 1-yr high'],
       [[e(c['name']), num(c['last'], 2, pct=False, sign=False), pct_td(c['w1']), pct_td(c['m1']), pct_td(c['m3']), pct_td(c['off_high'])] for c in cross])}
<p class="cap">VIX is the "fear gauge": higher means investors expect bigger swings. The 10-year yield row is a % rate; its changes are % moves in that rate.</p>
</section>

<section><h2>Regime watch: will rates stay high or fall?</h2>
<p class="take">Six price signals from the past month. Overall lean: <b>{e(lean)}</b>. This describes the lean, not who wins.</p>
{table(['Signal', '1 mo', '3 mo', 'Leans', 'Why it matters'],
       [[e(r['signal']) + f"<br><span class='tag'>{e(r['measure'])}</span>", num(r['m1'], 2, pct=False), num(r['m3'], 2, pct=False),
         e(r['leans']), f"<span class='muted' style='white-space:normal'>{e(r['why'])}</span>"] for r in regime])}
<p class="take" style="margin-top:12px"><b>Dates that can tip it:</b></p><ul>{events_html}</ul>
</section>

<section><h2>What the data flags this week</h2>
<p class="take">Rule-based patterns worth researching. Not recommendations.</p>
{flag_html}
</section>

<footer>Source: Yahoo Finance daily closes (free, unofficial, can lag). Updated every Sunday evening by GitHub Actions.<br>
Describes past prices only, not a forecast and not financial advice.</footer>
</main></body></html>"""

with open("index.html", "w") as f:
    f.write(page)
print("Wrote index.html")
