"""
NDX vertical spread trade visualizer — comprehensive edition.
One 1920×1080 PNG per trading day → trading_logs/viz/YYYY-MM-DD.png

Layout:
  [PRICE]   candlestick + VWAP + time-bounded spread bands + trade callouts
  [RATIONALE] day-level context strip (bias, outcome, regime)
  [VOL]     volume bars + VWAP scale
  [LEGEND]  per-spread table (direction, strikes, DTE, hold, adds, Q-score, why)
"""

import json, datetime, warnings, textwrap
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.ticker as mticker
import matplotlib.dates as mdates
from matplotlib.patches import Rectangle, FancyBboxPatch

warnings.filterwarnings('ignore')

BASE = Path(__file__).parent
OUT  = BASE / 'viz'
OUT.mkdir(exist_ok=True)

# ── data ──────────────────────────────────────────────────────────────────────
ndx_raw = json.load(open(BASE / 'NDX_5min_2026.json'))
trades  = json.load(open(BASE / 'trades.json'))

DST_START = datetime.datetime(2026, 3, 8, 7, 0)

def utc_str_to_et(s):
    dt = datetime.datetime.strptime(s, '%Y-%m-%d %H:%M')
    return dt - datetime.timedelta(hours=4 if dt >= DST_START else 5)

import pandas as pd
ndx_df = pd.DataFrame(ndx_raw['bars'])
ndx_df['et']   = ndx_df['datetime_utc'].apply(utc_str_to_et)
ndx_df['date'] = ndx_df['et'].dt.date.astype(str)

MONTHS = {'JAN':1,'FEB':2,'MAR':3,'APR':4,'MAY':5,'JUN':6,
          'JUL':7,'AUG':8,'SEP':9,'OCT':10,'NOV':11,'DEC':12}
def parse_exp(s):
    try:
        return datetime.date(2000+int(s[5:7]), MONTHS[s[2:5]], int(s[:2]))
    except:
        return None

# ── palette ───────────────────────────────────────────────────────────────────
BG      = '#0f1117'
PANEL   = '#181c2a'
PANEL2  = '#1e2235'
GRID    = '#252a3d'
GRID2   = '#1a1f30'
TEXT    = '#d1d4dc'
TEXT2   = '#7a849e'
TEXT3   = '#4e5568'
UP      = '#26a69a'
DOWN    = '#ef5350'
ENTRY_C = '#f5a623'
EXIT_C  = '#7b61ff'
SCALE_C = '#5a6278'
VWAP_C  = '#ce93d8'

SPREAD_COLORS = [
    '#26a69a', '#ef5350', '#f5a623', '#7b61ff',
    '#00bcd4', '#ff7043', '#9ccc65', '#f06292',
    '#4fc3f7', '#ffca28',
]

SESSION_PHASES = [
    (9.50, 10.00, '#161c2c', 'Open'),
    (10.00, 10.50, '#192038', ''),      # prime window
    (10.50, 12.00, '#0f1117', ''),
    (12.00, 14.00, '#141820', 'Lunch'),
    (14.00, 15.00, '#0f1117', ''),
    (15.00, 16.00, '#161c2c', 'EDT'),
]

# ── helpers ───────────────────────────────────────────────────────────────────
def to_dt(date_str, time_str):
    return datetime.datetime.strptime(f'{date_str} {time_str}', '%Y-%m-%d %H:%M:%S')

def nearest_bar(day_df, dt):
    diffs = (day_df['et'] - dt).abs()
    if diffs.empty: return None, None
    idx = diffs.idxmin()
    return day_df.loc[idx, 'close'], day_df.loc[idx, 'et']

def bars_before(day_df, dt):
    return day_df[day_df['et'] <= dt]

def draw_candles(ax, day_df):
    bw = (mdates.date2num(datetime.datetime(2000,1,2))
        - mdates.date2num(datetime.datetime(2000,1,1))) * (3.6/(24*60))
    for _, r in day_df.iterrows():
        x = mdates.date2num(r['et'])
        o, h, l, c = r['open'], r['high'], r['low'], r['close']
        col = UP if c >= o else DOWN
        ax.plot([x, x], [l, h], color=col, linewidth=0.9, zorder=2, solid_capstyle='butt')
        ax.add_patch(Rectangle((x - bw/2, min(o,c)), bw, max(abs(c-o), 0.5),
                                facecolor=col, edgecolor='none', zorder=3))

def classify_legs(day_trades):
    groups = defaultdict(list)
    for t in sorted(day_trades, key=lambda x: x['time']):
        groups[(t['expiry'], t['option_type'], t['strike'])].append(t)
    result = []
    for _, legs in groups.items():
        for i, leg in enumerate(legs):
            role = ('ENTRY' if i == 0
                    else ('EXIT' if i == len(legs)-1 and len(legs) > 1 else 'SCALE'))
            result.append({**leg, 'role': role})
    return result

def build_spreads(day_trades, date_str):
    by_key = defaultdict(list)
    for t in day_trades:
        by_key[(t['expiry'], t['option_type'])].append(t)
    spreads = []
    seen = set()
    for (exp, otype), legs in by_key.items():
        strikes = sorted(set(l['strike'] for l in legs))
        for i in range(len(strikes)-1):
            lo, hi = strikes[i], strikes[i+1]
            if hi-lo > 200: continue
            key = (exp, otype, lo, hi)
            if key in seen: continue
            seen.add(key)
            lo_legs = [l for l in legs if l['strike']==lo]
            hi_legs = [l for l in legs if l['strike']==hi]
            all_legs = sorted(lo_legs+hi_legs, key=lambda x: x['time'])
            lo_net = sum(l['quantity'] for l in lo_legs)
            if otype=='P': direction = 'Bull Put' if lo_net>0 else 'Bear Put'
            else:          direction = 'Bear Call' if lo_net<0 else 'Bull Call'
            t_open  = to_dt(all_legs[0]['date'],  all_legs[0]['time'])
            t_close = to_dt(all_legs[-1]['date'], all_legs[-1]['time'])
            hold    = (t_close-t_open).total_seconds()/60
            net     = sum(l['quantity']*l['price']*100 for l in all_legs)
            times_seen = defaultdict(int)
            for l in all_legs: times_seen[l['time']] += 1
            n_adds  = len(times_seen) - 1
            exp_date = parse_exp(exp)
            td = datetime.date.fromisoformat(date_str)
            dte = (exp_date-td).days if exp_date else None
            is_edt = ((t_open.hour>14 or (t_open.hour==14 and t_open.minute>=45))
                      and dte==1)
            short_s = hi if otype=='P' else lo
            long_s  = lo if otype=='P' else hi
            spreads.append(dict(
                exp=exp, dte=dte, type=otype, direction=direction,
                lo=lo, hi=hi, short_s=short_s, long_s=long_s,
                t_open=t_open, t_close=t_close, hold=hold,
                legs=all_legs, net=round(net,0),
                n_adds=n_adds, is_edt=is_edt,
            ))
    return spreads

def session_summary(day_df):
    if day_df.empty: return None
    o = day_df.iloc[0]['open']; c = day_df.iloc[-1]['close']
    h = day_df['high'].max();   l = day_df['low'].min()
    rng = h-l
    avg_bar = (day_df['high']-day_df['low']).mean()
    vol = day_df['volume'].sum()
    vwap = (day_df['close']*day_df['volume']).sum()/vol if vol else (h+l)/2
    return {'open':o,'close':c,'high':h,'low':l,'range':rng,'avg_bar':avg_bar,
            'vwap':vwap, 'trending':rng>2.5*avg_bar,
            'direction':'UP' if c>=o else 'DOWN',
            'range_pos':(c-l)/rng if rng else 0.5}

def entry_quality(sp, sess, day_df, open_et):
    if not sess or sp['dte'] is None: return None, []
    flags, score = [], 50
    mins = (sp['t_open']-open_et).total_seconds()/60
    if 30 <= mins <= 60:   score += 20; flags.append('✓ Prime window (10–10:30)')
    elif mins < 30:        score -= 10; flags.append('⚠ Opening (volatile)')
    elif mins > 300:       score -= 25; flags.append('✗ Late / EDT risk')
    if sp['dte'] == 0:     score += 15; flags.append('✓ 0DTE')
    elif sp['is_edt']:     score -= 30; flags.append('✗ EDT overnight')
    elif sp['dte'] and sp['dte'] >= 2: score -= 15; flags.append(f'✗ {sp["dte"]}DTE')
    if sp['direction']=='Bear Put':    score += 15; flags.append('✓ Bear Put (+EV)')
    elif sp['direction']=='Bull Put':  score -= 30; flags.append('✗ Bull Put (–EV)')
    elif sp['direction']=='Bear Call': score -= 20; flags.append('✗ Bear Call (–EV)')
    bb = bars_before(day_df, sp['t_open'])
    if not bb.empty:
        ep = bb.iloc[-1]['close']
        dist = (ep - sp['short_s']) if sp['type']=='P' else (sp['short_s'] - ep)
        if dist >= 100:   score += 10; flags.append(f'✓ {dist:.0f}pt OTM')
        elif dist < 50:   score -= 15; flags.append(f'⚠ Only {dist:.0f}pt OTM')
    if sess['trending']:   score -= 20; flags.append('⚠ Trending regime')
    else:                  score += 10; flags.append('✓ Range regime')
    if sp['n_adds'] >= 5:  score -= 25; flags.append(f'✗ {sp["n_adds"]} scale-ins')
    elif sp['n_adds'] <= 2: score += 5; flags.append(f'✓ {sp["n_adds"]} add(s)')
    return max(0, min(100, score)), flags

def quality_color(score):
    if score is None: return TEXT2
    if score >= 65: return '#26a69a'
    if score >= 45: return '#f5a623'
    return '#ef5350'

# ── per-spread trade rationale text ──────────────────────────────────────────
def trade_why(sp, sess, day_df, open_et):
    """
    Generate a short 'why this trade' paragraph for display on the chart.
    Returns (headline str, detail str).
    """
    if not sess:
        return sp['direction'], "No NDX context"

    bb = bars_before(day_df, sp['t_open'])
    ep = bb.iloc[-1]['close'] if not bb.empty else None
    mins = (sp['t_open'] - open_et).total_seconds() / 60

    # Running high/low at entry
    run_h = bb['high'].max() if not bb.empty else None
    run_l = bb['low'].min()  if not bb.empty else None

    # 30-min momentum
    bb_30 = day_df[(day_df['et'] >= sp['t_open']-datetime.timedelta(minutes=35))
                   & (day_df['et'] <= sp['t_open'])]
    mom30 = (bb_30.iloc[-1]['close'] - bb_30.iloc[0]['close']) if len(bb_30) >= 2 else 0

    # vs open
    vs_open = (ep - sess['open']) if ep else 0

    # position in running range
    rng_pos = ((ep - run_l)/(run_h - run_l) if ep and run_h and run_l and run_h!=run_l
               else 0.5)

    # time description
    if mins < 30:     t_ctx = "at the open"
    elif mins <= 75:  t_ctx = f"{mins:.0f}min after open"
    elif mins <= 180: t_ctx = f"{mins/60:.1f}h into session"
    elif sp['is_edt']:t_ctx = "late (EDT setup)"
    else:             t_ctx = f"{mins/60:.1f}h into session"

    # price context
    if ep:
        if rng_pos > 0.75:
            price_ctx = f"NDX near session high ({vs_open:+.0f}pt from open)"
        elif rng_pos < 0.25:
            price_ctx = f"NDX near session low ({vs_open:+.0f}pt from open)"
        else:
            price_ctx = f"NDX mid-range ({vs_open:+.0f}pt from open)"
    else:
        price_ctx = "NDX context unavailable"

    # momentum context
    if mom30 > 50:      mom_ctx = f"sharp rally +{mom30:.0f}pt in 30min"
    elif mom30 > 15:    mom_ctx = f"rising +{mom30:.0f}pt in 30min"
    elif mom30 < -50:   mom_ctx = f"sharp selloff {mom30:.0f}pt in 30min"
    elif mom30 < -15:   mom_ctx = f"drifting lower {mom30:.0f}pt in 30min"
    else:               mom_ctx = f"flat ({mom30:+.0f}pt in 30min)"

    # OTM distance
    if ep:
        dist = (ep - sp['short_s']) if sp['type']=='P' else (sp['short_s'] - ep)
        otm_ctx = f"short strike {dist:.0f}pt OTM"
    else:
        otm_ctx = ""

    # build headline
    dir_map = {
        'Bear Put':  'Bear Put — sell put spread above support',
        'Bull Put':  'Bull Put — sell put spread below resistance (fade drop)',
        'Bear Call': 'Bear Call — sell call spread below resistance (fade rally)',
        'Bull Call': 'Bull Call — sell call spread above support',
    }
    headline = dir_map.get(sp['direction'], sp['direction'])

    # build detail
    detail_parts = [price_ctx, mom_ctx]
    if otm_ctx: detail_parts.append(otm_ctx)
    detail_parts.append(t_ctx)

    # add EDT note
    if sp['is_edt']:
        detail_parts.append("overnight theta capture — HIGH RISK")

    # rationale for direction
    if sp['direction'] == 'Bear Put':
        detail_parts.append("→ expect NDX to hold above short put at expiry")
    elif sp['direction'] == 'Bull Put':
        detail_parts.append("→ fading the dip; expect bounce above short put")
    elif sp['direction'] == 'Bear Call':
        detail_parts.append("→ fading the rally; expect NDX to stay below short call")
    elif sp['direction'] == 'Bull Call':
        detail_parts.append("→ expect continued strength above short call")

    detail = "  ·  ".join(detail_parts)
    return headline, detail

def make_day_rationale(spreads, sess):
    if not sess: return "No NDX context", ""
    bull_n = sum(1 for s in spreads if 'Bull' in s['direction'])
    bear_n = sum(1 for s in spreads if 'Bear' in s['direction'])
    pnl = sum(s['net'] for s in spreads)
    bias = ("Bullish (fading dips)" if bull_n > bear_n
            else "Bearish (fading rallies)" if bear_n > bull_n
            else "Neutral")
    rng = sess['range']; dirn = sess['direction']
    rpos = sess['range_pos']; trnd = sess['trending']
    if trnd and dirn=='DOWN' and bull_n >= bear_n:
        ctx = f"NDX trended DOWN {rng:.0f}pt — bull fades ran over (closed {100*rpos:.0f}% from low)"
        risk = "HIGH"
    elif trnd and dirn=='UP' and bear_n >= bull_n:
        ctx = f"NDX trended UP {rng:.0f}pt — bear fades ran over (closed {100*rpos:.0f}% from low)"
        risk = "HIGH"
    elif trnd:
        ctx = f"NDX trended {dirn} {rng:.0f}pt — bias aligned with direction"
        risk = "MED"
    elif rng < 180:
        ctx = f"Tight {rng:.0f}pt range — favorable theta decay environment"
        risk = "LOW"
    else:
        ctx = f"Choppy {rng:.0f}pt range — partial mean-reversion"
        risk = "MED"
    outcome = "WIN" if pnl > 0 else "LOSS"
    line1 = f"Day bias: {bias}   Outcome: {outcome} ${pnl:+,.0f}"
    line2 = f"{ctx}   Regime risk: {risk}"
    return line1, line2

# ── cumulative P&L ─────────────────────────────────────────────────────────────
by_day_all = defaultdict(list)
for t in trades: by_day_all[t['date']].append(t)

cum = 0.0; cum_pnl_by_date = {}
for d in sorted(by_day_all.keys()):
    sp = build_spreads(by_day_all[d], d)
    cum += sum(s['net'] for s in sp)
    cum_pnl_by_date[d] = cum

# ── main ──────────────────────────────────────────────────────────────────────
trade_dates = sorted(by_day_all.keys())
print(f'Generating {len(trade_dates)} charts...')

for date_str in trade_dates:
    day_trades = by_day_all[date_str]
    day_df     = ndx_df[ndx_df['date'] == date_str].copy()
    if day_df.empty:
        print(f'  {date_str}: no NDX data — skip'); continue

    spreads = build_spreads(day_trades, date_str)
    tagged  = classify_legs(day_trades)
    if not spreads: continue

    sess = session_summary(day_df)
    trade_date = datetime.date.fromisoformat(date_str)
    open_et = datetime.datetime.combine(trade_date, datetime.time(9, 30))

    # Pre-compute per-spread rationale
    for sp in spreads:
        sp['why_head'], sp['why_detail'] = trade_why(sp, sess, day_df, open_et)
        sp['q_score'], sp['q_flags']     = entry_quality(sp, sess, day_df, open_et)

    # ── figure ─────────────────────────────────────────────────────────────────
    n_legend_rows = max(1, (len(spreads)+1)//2)
    leg_h = max(1.0, 0.52 * n_legend_rows)

    fig = plt.figure(figsize=(20, 11.25), dpi=96, facecolor=BG)
    gs  = fig.add_gridspec(4, 1,
                            height_ratios=[5.8, 0.82, 1.3, leg_h],
                            hspace=0.0, left=0.058, right=0.976,
                            top=0.925, bottom=0.035)
    ax      = fig.add_subplot(gs[0])
    ax_rat  = fig.add_subplot(gs[1], sharex=ax)
    ax_vol  = fig.add_subplot(gs[2], sharex=ax)
    ax_leg  = fig.add_subplot(gs[3])

    for a in (ax, ax_rat, ax_vol):
        a.set_facecolor(BG)
        a.tick_params(colors=TEXT2, labelsize=8)
        for spine in a.spines.values(): spine.set_edgecolor(GRID)
    ax_leg.set_facecolor(BG); ax_leg.axis('off')

    # ── session shading ────────────────────────────────────────────────────────
    for h0, h1, fc, label in SESSION_PHASES:
        p0 = mdates.date2num(datetime.datetime.combine(trade_date,
                             datetime.time(int(h0), int((h0%1)*60))))
        p1 = mdates.date2num(datetime.datetime.combine(trade_date,
                             datetime.time(int(h1), int((h1%1)*60))))
        for a in (ax, ax_rat, ax_vol):
            a.axvspan(p0, p1, facecolor=fc, alpha=1.0, zorder=0)
        if label:
            ax.text(p0+(p1-p0)*0.5, 0.997, label,
                    transform=ax.get_xaxis_transform(),
                    color=TEXT3, fontsize=6.5, ha='center', va='top')

    # Prime window subtle highlight
    prime0 = mdates.date2num(datetime.datetime.combine(trade_date, datetime.time(10,0)))
    prime1 = mdates.date2num(datetime.datetime.combine(trade_date, datetime.time(10,30)))
    ax.axvspan(prime0, prime1, facecolor='#26a69a', alpha=0.055, zorder=0)
    ax.text(prime0+(prime1-prime0)*0.5, 0.988, '★ Prime',
            transform=ax.get_xaxis_transform(),
            color='#26a69a', fontsize=5.8, ha='center', va='top', alpha=0.75)

    # ── candlesticks ───────────────────────────────────────────────────────────
    draw_candles(ax, day_df)

    # ── VWAP ───────────────────────────────────────────────────────────────────
    if sess:
        cum_vol = day_df['volume'].cumsum()
        cum_vwp = (day_df['close'] * day_df['volume']).cumsum()
        vwap_s = cum_vwp / cum_vol
        x_arr = day_df['et'].map(mdates.date2num).values
        ax.plot(x_arr, vwap_s, color=VWAP_C, linewidth=1.0,
                linestyle='--', alpha=0.55, zorder=4, label='VWAP')
        ax_vol.plot(x_arr, vwap_s, color=VWAP_C, linewidth=0.9,
                    alpha=0.5, zorder=4)

    # ── volume ─────────────────────────────────────────────────────────────────
    bw_v = (mdates.date2num(datetime.datetime(2000,1,1,0,3,30))
          - mdates.date2num(datetime.datetime(2000,1,1,0,0,0)))
    for _, r in day_df.iterrows():
        col = UP if r['close'] >= r['open'] else DOWN
        ax_vol.bar(mdates.date2num(r['et']), r['volume'],
                   width=bw_v, color=col, alpha=0.65, linewidth=0)
    ax_vol.set_ylabel('Vol', color=TEXT2, fontsize=7)
    ax_vol.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x,_: f'{x/1e6:.1f}M'))
    ax_vol.yaxis.set_major_locator(mticker.MaxNLocator(3))
    ax_vol.tick_params(axis='y', labelsize=7)

    # ── y-axis range ──────────────────────────────────────────────────────────
    all_lo  = [s['lo'] for s in spreads]
    all_hi  = [s['hi'] for s in spreads]
    px_lo   = day_df['low'].min(); px_hi = day_df['high'].max()
    data_lo = min(px_lo, min(all_lo)); data_hi = max(px_hi, max(all_hi))
    pad     = (data_hi - data_lo) * 0.22
    ax.set_ylim(data_lo - pad*0.3, data_hi + pad + pad*1.1)
    ylim    = ax.get_ylim()

    # ── spread bands ──────────────────────────────────────────────────────────
    # Sort by entry time so callout boxes get consistent vertical offsets
    spreads_sorted = sorted(spreads, key=lambda s: s['t_open'])

    # Track y positions used by callout boxes to avoid overlap
    callout_y_slots = []   # list of (x_center, y_bottom, y_top)

    legend_items = []
    for idx, sp in enumerate(spreads_sorted):
        sc  = SPREAD_COLORS[idx % len(SPREAD_COLORS)]
        win = sp['net'] > 0

        # Time-bounded rectangle
        x0 = mdates.date2num(sp['t_open']  - datetime.timedelta(minutes=4))
        x1 = mdates.date2num(sp['t_close'] + datetime.timedelta(minutes=4))
        if x1 <= x0:
            x0 = mdates.date2num(day_df['et'].min() - datetime.timedelta(minutes=5))
            x1 = mdates.date2num(day_df['et'].max() + datetime.timedelta(minutes=5))

        band_h = max(sp['hi'] - sp['lo'], 1)
        ax.add_patch(Rectangle((x0, sp['lo']), x1-x0, band_h,
                                facecolor=sc, alpha=0.18 if win else 0.09,
                                edgecolor='none', zorder=2))
        border_ls = (0, (6,2)) if win else (0, (3,3))
        ax.add_patch(Rectangle((x0, sp['lo']), x1-x0, band_h,
                                facecolor='none', edgecolor=sc, linewidth=0.9,
                                linestyle=border_ls, alpha=0.75, zorder=3))

        # Strike lines
        ax.hlines(sp['short_s'], x0, x1, colors=sc, linewidth=1.1,
                  linestyles='--', alpha=0.9, zorder=4)
        ax.hlines(sp['long_s'],  x0, x1, colors=sc, linewidth=0.65,
                  linestyles=':', alpha=0.7, zorder=4)

        # Strike labels (left margin)
        x_lbl = mdates.date2num(day_df['et'].min() - datetime.timedelta(minutes=3))
        ax.text(x_lbl, sp['short_s'], f'{sp["short_s"]:,.0f}  ─S',
                color=sc, fontsize=6.5, va='center', ha='right', zorder=6)
        ax.text(x_lbl, sp['long_s'], f'{sp["long_s"]:,.0f}  ─L',
                color=sc, fontsize=6.0, va='center', ha='right', zorder=6, alpha=0.7)

        # ── per-spread "WHY" callout box ─────────────────────────────────────
        # Position: anchored to entry time, placed in the label headroom above candles
        entry_xn = mdates.date2num(sp['t_open'])
        bb_entry = bars_before(day_df, sp['t_open'])
        entry_ndx = bb_entry.iloc[-1]['close'] if not bb_entry.empty else (data_lo+data_hi)/2

        # Callout y: stagger boxes in the headroom area above the price range
        y_span    = ylim[1] - ylim[0]
        headroom_top    = ylim[1] - y_span * 0.005
        headroom_bottom = data_hi + pad * 0.05
        slot_height     = (headroom_top - headroom_bottom) / max(len(spreads_sorted), 1)
        callout_y_center = headroom_top - slot_height * (idx + 0.5)

        dte_str  = f"{sp['dte']}DTE" if sp['dte'] is not None else '?DTE'
        if sp['is_edt']: dte_str += ' EDT'
        hold_str = (f"{sp['hold']:.0f}min" if sp['hold'] < 120
                    else f"{sp['hold']/60:.1f}h")
        sign = '+' if sp['net'] >= 0 else ''
        q_col = quality_color(sp['q_score'])
        q_str = f"Q{sp['q_score']}" if sp['q_score'] is not None else "Q?"

        # First line: direction + key stats
        box_line1 = (f"{sp['direction']}  {dte_str}  {hold_str}  "
                     f"+{sp['n_adds']}adds  ${sign}{sp['net']:,.0f}  {q_str}")
        # Second line: WHY headline
        box_line2 = sp['why_head']
        # Third line: detail (truncated)
        detail_trunc = sp['why_detail']
        if len(detail_trunc) > 110:
            detail_trunc = detail_trunc[:107] + '…'

        full_txt = f"{box_line1}\n{box_line2}\n{detail_trunc}"

        ax.annotate(
            full_txt,
            xy=(entry_xn, entry_ndx),
            xytext=(entry_xn, callout_y_center),
            color=sc, fontsize=6.2, va='center', ha='center',
            fontfamily='monospace',
            arrowprops=dict(
                arrowstyle='-|>', color=sc, alpha=0.45,
                lw=0.7, mutation_scale=5,
                connectionstyle='arc3,rad=0.0'
            ),
            bbox=dict(
                boxstyle='round,pad=0.35', fc=PANEL2,
                ec=sc, alpha=0.95, linewidth=1.0
            ),
            zorder=11
        )

        # Legend row
        q_badge = f"[Q{sp['q_score']}]" if sp['q_score'] is not None else "[Q?]"
        legend_items.append(mpatches.Patch(
            facecolor=sc, alpha=0.85,
            label=(f"{sp['direction']:10s}  {sp['lo']:>7,.0f}/{sp['hi']:>7,.0f}  "
                   f"{dte_str:8s}  ${sign}{sp['net']:>8,.0f}  "
                   f"{hold_str:7s}  +{sp['n_adds']}  {q_badge}  "
                   f"{sp['why_head'][:45]}")
        ))

    # ── trade markers ─────────────────────────────────────────────────────────
    role_cfg = {
        'ENTRY': dict(color=ENTRY_C, marker='D', ms=7,   lw=1.5, ls='--', zo=9),
        'EXIT':  dict(color=EXIT_C,  marker='s', ms=7,   lw=1.2, ls='-.', zo=9),
        'SCALE': dict(color=SCALE_C, marker='o', ms=4.5, lw=0.7, ls=':',  zo=8),
    }
    for leg in sorted(tagged, key=lambda x: x['time']):
        try: leg_dt = to_dt(leg['date'], leg['time'])
        except: continue
        ndx_px, _ = nearest_bar(day_df, leg_dt)
        if ndx_px is None: continue
        cfg = role_cfg[leg['role']]
        ax.axvline(mdates.date2num(leg_dt), color=cfg['color'],
                   linewidth=cfg['lw'], linestyle=cfg['ls'],
                   alpha=0.45, zorder=cfg['zo'])
        ax.scatter(mdates.date2num(leg_dt), ndx_px,
                   marker=cfg['marker'], color=cfg['color'],
                   s=cfg['ms']**2, zorder=cfg['zo']+1,
                   edgecolors='white', linewidths=0.55)

    # ── day rationale strip ────────────────────────────────────────────────────
    ax_rat.set_ylim(0, 1); ax_rat.set_yticks([])
    ax_rat.tick_params(bottom=False, labelbottom=False)
    for sp in ax_rat.spines.values(): sp.set_visible(False)
    ax_rat.set_facecolor(PANEL)

    l1, l2 = make_day_rationale(spreads, sess)
    ax_rat.text(0.010, 0.80, l1, transform=ax_rat.transAxes,
                color=TEXT, fontsize=8.0, va='top', fontweight='bold')
    ax_rat.text(0.010, 0.28, l2, transform=ax_rat.transAxes,
                color=TEXT2, fontsize=7.2, va='top')

    # Regime badge
    if sess:
        rc  = '#ef5350' if sess['trending'] else '#26a69a'
        rtx = (f"{'TRENDING' if sess['trending'] else 'RANGE-BOUND'}"
               f"  {sess['direction']}  {sess['range']:.0f}pt range")
        ax_rat.text(0.992, 0.5, rtx, transform=ax_rat.transAxes,
                    color=rc, fontsize=8.0, va='center', ha='right',
                    fontweight='bold',
                    bbox=dict(boxstyle='round,pad=0.32', fc=BG, ec=rc,
                              linewidth=1.2, alpha=0.96))

    # ── axes cosmetics ─────────────────────────────────────────────────────────
    for a in (ax, ax_vol):
        a.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        a.xaxis.set_major_locator(mdates.HourLocator(interval=1))
        a.xaxis.set_minor_locator(mdates.MinuteLocator(byminute=[0,15,30,45]))
    ax_vol.tick_params(axis='x', colors=TEXT2, labelsize=8)

    x_lo = mdates.date2num(day_df['et'].min() - datetime.timedelta(minutes=15))
    x_hi = mdates.date2num(day_df['et'].max() + datetime.timedelta(minutes=10))
    ax.set_xlim(x_lo, x_hi)

    ax.grid(True, which='major', color=GRID,  linewidth=0.5, zorder=1)
    ax.grid(True, which='minor', color=GRID2, linewidth=0.2, alpha=0.5, zorder=1)
    ax_vol.grid(True, color=GRID, linewidth=0.3, zorder=1)
    ax.set_ylabel('NDX', color=TEXT2, fontsize=9)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x,_: f'{x:,.0f}'))
    ax.tick_params(axis='y', colors=TEXT2, labelsize=8)
    plt.setp(ax.get_xticklabels(), visible=False)
    plt.setp(ax_rat.get_xticklabels(), visible=False)

    # Role legend (price pane top-right)
    rl = [mpatches.Patch(color=ENTRY_C, label='Entry ◆'),
          mpatches.Patch(color=EXIT_C,  label='Exit ■'),
          mpatches.Patch(color=SCALE_C, label='Scale ●'),
          mpatches.Patch(color=VWAP_C,  label='VWAP')]
    ax.legend(handles=rl, loc='upper right', fontsize=7,
              facecolor=PANEL, edgecolor=GRID, labelcolor=TEXT,
              framealpha=0.95, ncol=4, handlelength=0.85,
              borderpad=0.5, columnspacing=0.7)

    # ── spread legend table ────────────────────────────────────────────────────
    ax_leg.set_facecolor(PANEL)
    ax_leg.axis('off')

    # Header
    hdr = (f"{'Spread':10s}  {'Strikes':>15s}  {'DTE':8s}  "
           f"{'P&L':>9s}  {'Hold':7s}  {'Adds':3s}  {'Q':5s}  {'Why (trade rationale)'}")
    ax_leg.text(0.012, 0.97, hdr, transform=ax_leg.transAxes,
                color=TEXT3, fontsize=6.8, va='top', fontfamily='monospace')
    ax_leg.plot([0.01, 0.99], [0.88, 0.88], color=GRID, linewidth=0.5,
                transform=ax_leg.transAxes)

    n_cols = 2
    row_h  = 0.85 / max(len(spreads_sorted), 1) if len(spreads_sorted) <= n_cols else \
             0.85 / ((len(spreads_sorted)+1)//n_cols)
    row_h  = max(row_h, 0.14)

    for i, sp in enumerate(spreads_sorted):
        sc    = SPREAD_COLORS[i % len(SPREAD_COLORS)]
        sign  = '+' if sp['net'] >= 0 else ''
        dte_s = f"{sp['dte']}DTE" if sp['dte'] is not None else '?DTE'
        if sp['is_edt']: dte_s += ' EDT'
        hold_s = (f"{sp['hold']:.0f}min" if sp['hold'] < 120
                  else f"{sp['hold']/60:.1f}h")
        q_col = quality_color(sp['q_score'])
        q_s   = f"Q{sp['q_score']}" if sp['q_score'] is not None else "Q?"

        col_idx = i % n_cols
        row_idx = i // n_cols
        x_off   = 0.012 + col_idx * 0.50
        y_off   = 0.83 - row_idx * row_h * 2

        row_txt = (f"{sp['direction']:10s}  "
                   f"{sp['lo']:>7,.0f}/{sp['hi']:>7,.0f}  "
                   f"{dte_s:8s}  ${sign}{sp['net']:>8,.0f}  "
                   f"{hold_s:7s}  +{sp['n_adds']}  {q_s:4s}  "
                   f"{sp['why_head']}")
        ax_leg.text(x_off, y_off, '■  ' + row_txt,
                    transform=ax_leg.transAxes,
                    color=sc, fontsize=6.8, va='top', fontfamily='monospace')

        # Why detail on second sub-line
        detail = sp['why_detail']
        if len(detail) > 130: detail = detail[:127] + '…'
        ax_leg.text(x_off + 0.012, y_off - row_h * 0.9, detail,
                    transform=ax_leg.transAxes,
                    color=TEXT2, fontsize=6.0, va='top')

    # ── title ─────────────────────────────────────────────────────────────────
    accounts  = ', '.join(sorted(set(t['account'] for t in day_trades)))
    total_net = sum(s['net'] for s in spreads)
    cum_net   = cum_pnl_by_date.get(date_str, 0)
    dow       = datetime.date.fromisoformat(date_str).strftime('%A')
    n_adds_max= max((s['n_adds'] for s in spreads), default=0)
    edt_flag  = '  ⚠ EDT' if any(s['is_edt'] for s in spreads) else ''
    fig.suptitle(
        f'NDX 5-min  ·  {date_str} ({dow})  ·  {len(spreads)} spread(s)  ·  '
        f'Day: ${total_net:+,.0f}  ·  Cumulative: ${cum_net:+,.0f}  ·  '
        f'Max adds: {n_adds_max}{edt_flag}  ·  {accounts}',
        color=TEXT, fontsize=10.5, y=0.963, fontweight='bold'
    )

    out_path = OUT / f'{date_str}.png'
    fig.savefig(out_path, dpi=96, facecolor=BG)
    plt.close(fig)
    print(f'  {date_str}: {len(spreads)} spread(s), {len(tagged)} legs → {out_path.name}')

print(f'\nDone. {len(list(OUT.glob("*.png")))} charts in {OUT}')
