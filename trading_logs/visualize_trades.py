"""
NDX vertical spread trade visualizer — comprehensive edition.
One 1920×1080 PNG per trading day → trading_logs/viz/YYYY-MM-DD.png

Layout (top→bottom):
  [PRICE]   candlestick + time-bounded spread bands + trade markers   58%
  [STATS]   rationale / entry-quality / regime strip                   9%
  [VOL]     volume bars + VWAP                                        16%
  [LEGEND]  per-spread legend with DTE, hold, scale-in, entry quality 17%
"""

import json, datetime, warnings, statistics
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.ticker as mticker
import matplotlib.dates as mdates
from matplotlib.patches import Rectangle

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
BG      = '#131722'
PANEL   = '#1a1e2d'
GRID    = '#252a3d'
GRID2   = '#1c2130'
TEXT    = '#d1d4dc'
TEXT2   = '#8a92a8'
UP      = '#26a69a'
DOWN    = '#ef5350'
ENTRY_C = '#f5a623'
EXIT_C  = '#7b61ff'
SCALE_C = '#666e87'
VWAP_C  = '#e040fb'

SPREAD_COLORS = [
    '#26a69a','#ef5350','#f5a623','#7b61ff',
    '#00bcd4','#ff7043','#a8e063','#f06292',
    '#4fc3f7','#ffb300',
]

# Session phase bands (ET hours)
SESSION_PHASES = [
    (9.50, 10.00, '#1d2840', 'Open'),
    (10.00,10.50, '#203050', ''),        # prime window — slightly brighter
    (10.50,12.00, '#131722', ''),
    (12.00,14.00, '#171d2b', 'Lunch'),
    (14.00,15.00, '#131722', ''),
    (15.00,16.00, '#1d2840', 'EDT'),
]

# ── helpers ───────────────────────────────────────────────────────────────────
def to_dt(date_str, time_str):
    return datetime.datetime.strptime(f'{date_str} {time_str}', '%Y-%m-%d %H:%M:%S')

def nearest_bar(day_df, dt):
    diffs = (day_df['et'] - dt).abs()
    if diffs.empty: return None, None
    idx = diffs.idxmin()
    return day_df.loc[idx, 'close'], day_df.loc[idx, 'et']

def draw_candles(ax, day_df):
    bw_num = (mdates.date2num(datetime.datetime(2000,1,2))
            - mdates.date2num(datetime.datetime(2000,1,1))) * (3.5/(24*60))
    for _, r in day_df.iterrows():
        x = mdates.date2num(r['et'])
        o, h, l, c = r['open'], r['high'], r['low'], r['close']
        col = UP if c >= o else DOWN
        ax.plot([x, x], [l, h], color=col, linewidth=0.85, zorder=2, solid_capstyle='butt')
        ax.add_patch(Rectangle((x - bw_num/2, min(o,c)), bw_num,
                                max(abs(c-o), 0.4),
                                facecolor=col, edgecolor='none', zorder=3))

def classify_legs(day_trades):
    groups = defaultdict(list)
    for t in sorted(day_trades, key=lambda x: x['time']):
        groups[(t['expiry'], t['option_type'], t['strike'])].append(t)
    result = []
    for _, legs in groups.items():
        for i, leg in enumerate(legs):
            role = ('ENTRY' if i == 0
                    else ('EXIT' if i == len(legs)-1 and len(legs) > 1
                          else 'SCALE'))
            result.append({**leg, 'role': role})
    return result

def build_spreads(day_trades, trade_date_str):
    by_exp_type = defaultdict(list)
    for t in day_trades:
        by_exp_type[(t['expiry'], t['option_type'])].append(t)
    spreads = []
    seen = set()
    for (exp, otype), legs in by_exp_type.items():
        strikes = sorted(set(l['strike'] for l in legs))
        for i in range(len(strikes)-1):
            lo, hi = strikes[i], strikes[i+1]
            if hi-lo > 200: continue
            key = (exp, otype, lo, hi)
            if key in seen: continue
            seen.add(key)
            lo_legs = [l for l in legs if l['strike']==lo]
            hi_legs = [l for l in legs if l['strike']==hi]
            all_legs = sorted(lo_legs + hi_legs, key=lambda x: x['time'])
            lo_net = sum(l['quantity'] for l in lo_legs)
            if otype=='P': direction = 'Bull Put' if lo_net>0 else 'Bear Put'
            else:          direction = 'Bear Call' if lo_net<0 else 'Bull Call'
            t_open  = to_dt(all_legs[0]['date'],  all_legs[0]['time'])
            t_close = to_dt(all_legs[-1]['date'], all_legs[-1]['time'])
            hold    = (t_close - t_open).total_seconds() / 60
            net     = sum(l['quantity']*l['price']*100 for l in all_legs)
            # distinct entry times = scale-in events
            times_seen = defaultdict(int)
            for l in all_legs: times_seen[l['time']] += 1
            n_adds = len(times_seen) - 1
            exp_date = parse_exp(exp)
            trade_date = datetime.date.fromisoformat(trade_date_str)
            dte = (exp_date - trade_date).days if exp_date else None
            is_edt = (t_open.hour > 14 or (t_open.hour==14 and t_open.minute>=45)) and dte==1
            spreads.append(dict(
                exp=exp, dte=dte, type=otype, direction=direction,
                lo=lo, hi=hi, t_open=t_open, t_close=t_close,
                hold=hold, legs=all_legs, net=round(net,0),
                n_adds=n_adds, is_edt=is_edt,
            ))
    return spreads

def session_summary(day_df):
    if day_df.empty: return None
    o = day_df.iloc[0]['open'];  c = day_df.iloc[-1]['close']
    h = day_df['high'].max();    l = day_df['low'].min()
    rng = h-l
    avg_bar = (day_df['high']-day_df['low']).mean()
    vol = day_df['volume'].sum()
    vwap = (day_df['close']*day_df['volume']).sum()/vol if vol else (h+l)/2
    return {'open':o,'close':c,'high':h,'low':l,'range':rng,
            'avg_bar':avg_bar,'vwap':vwap,
            'trending': rng > 2.5*avg_bar,
            'direction':'UP' if c>=o else 'DOWN',
            'range_pos': (c-l)/rng if rng else 0.5}

def entry_quality(sp, sess, day_df, open_et):
    """Score the quality of an entry using backtest criteria. Returns (score 0-100, flags list)."""
    if not sess or sp['dte'] is None: return None, []
    flags = []
    score = 50  # neutral start

    # 1. Time window: 30-60min after open is optimal
    mins_since_open = (sp['t_open'] - open_et).total_seconds()/60
    if 30 <= mins_since_open <= 60:
        score += 20; flags.append('✓ Prime window')
    elif mins_since_open < 30:
        score -= 10; flags.append('⚠ Too early')
    elif mins_since_open > 300:
        score -= 25; flags.append('✗ Late (EDT risk)')

    # 2. DTE: 0DTE best
    if sp['dte'] == 0:
        score += 15; flags.append('✓ 0DTE')
    elif sp['dte'] == 1 and sp['is_edt']:
        score -= 30; flags.append('✗ EDT overnight')
    elif sp['dte'] >= 2:
        score -= 15; flags.append('✗ 2+DTE')

    # 3. Direction: Bear Put only is positive EV
    if sp['direction'] == 'Bear Put':
        score += 15; flags.append('✓ Bear Put (pos EV)')
    elif sp['direction'] in ('Bull Put',):
        score -= 30; flags.append('✗ Bull Put (neg EV)')
    elif sp['direction'] == 'Bear Call':
        score -= 20; flags.append('✗ Bear Call (neg EV)')

    # 4. OTM distance
    entry_bar_before = day_df[day_df['et'] <= sp['t_open']]
    if not entry_bar_before.empty:
        ep = entry_bar_before.iloc[-1]['close']
        if sp['type']=='P': dist = ep - sp['hi']
        else:               dist = sp['lo'] - ep
        if dist >= 100:
            score += 10; flags.append(f'✓ OTM {dist:.0f}pt')
        elif dist < 50:
            score -= 15; flags.append(f'⚠ Too close ({dist:.0f}pt OTM)')

    # 5. Trending regime — bad for this strategy
    if sess['trending']:
        score -= 20; flags.append('⚠ Trending day')
    else:
        score += 10; flags.append('✓ Range regime')

    # 6. Scale-in depth
    if sp['n_adds'] >= 5:
        score -= 25; flags.append('✗ Over-averaged (5+)')
    elif sp['n_adds'] <= 2:
        score += 5;  flags.append(f'✓ {sp["n_adds"]} add(s)')

    score = max(0, min(100, score))
    return score, flags

def quality_color(score):
    if score is None: return TEXT2
    if score >= 65: return '#26a69a'
    if score >= 45: return '#f5a623'
    return '#ef5350'

def make_rationale(spreads, sess):
    if not sess: return "No NDX context available", ""
    bull_n = sum(1 for s in spreads if 'Bull' in s['direction'])
    bear_n = sum(1 for s in spreads if 'Bear' in s['direction'])
    pnl = sum(s['net'] for s in spreads)

    bias = ("Bullish bias — fading dips" if bull_n > bear_n
            else "Bearish bias — fading rallies" if bear_n > bull_n
            else "Neutral — both directions")

    rng = sess['range']; dirn = sess['direction']
    rpos = sess['range_pos']; trnd = sess['trending']

    if trnd and dirn=='DOWN' and bull_n >= bear_n:
        ctx = f"NDX trended DOWN {rng:.0f}pt (closed {100*rpos:.0f}% from low) — bull fades got run over"
        risk = "HIGH"
    elif trnd and dirn=='UP' and bear_n >= bull_n:
        ctx = f"NDX trended UP {rng:.0f}pt (closed {100*rpos:.0f}% from low) — bear fades got run over"
        risk = "HIGH"
    elif trnd:
        ctx = f"NDX trended {dirn} {rng:.0f}pt — bias aligned; theta captured"
        risk = "MED"
    elif rng < 180:
        ctx = f"Tight range {rng:.0f}pt — low-vol, theta decay favorable"
        risk = "LOW"
    else:
        ctx = f"Choppy {rng:.0f}pt range — mixed mean-reversion"
        risk = "MED"

    outcome = "WIN" if pnl > 0 else "LOSS"
    line1 = f"Bias: {bias}  |  Outcome: {outcome} ${pnl:+,.0f}"
    line2 = f"Market: {ctx}  |  Regime: {'TRENDING' if trnd else 'RANGE'}  |  Risk: {risk}"
    return line1, line2

# ── cumulative P&L pre-computation ─────────────────────────────────────────────
by_day_all = defaultdict(list)
for t in trades: by_day_all[t['date']].append(t)

cum = 0.0
cum_pnl_by_date = {}
for d in sorted(by_day_all.keys()):
    sp = build_spreads(by_day_all[d], d)
    cum += sum(s['net'] for s in sp)
    cum_pnl_by_date[d] = cum

# ── main render loop ───────────────────────────────────────────────────────────
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

    # ── figure layout ─────────────────────────────────────────────────────────
    fig = plt.figure(figsize=(20, 11.25), dpi=96, facecolor=BG)
    gs  = fig.add_gridspec(4, 1, height_ratios=[5.6, 0.85, 1.4, 1.15],
                            hspace=0.0, left=0.055, right=0.975,
                            top=0.924, bottom=0.04)
    ax     = fig.add_subplot(gs[0])
    ax_rat = fig.add_subplot(gs[1], sharex=ax)
    ax_vol = fig.add_subplot(gs[2], sharex=ax)
    ax_leg = fig.add_subplot(gs[3])

    for a in (ax, ax_rat, ax_vol):
        a.set_facecolor(BG)
        a.tick_params(colors=TEXT2, labelsize=8)
        for sp in a.spines.values(): sp.set_edgecolor(GRID)
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
                    color=TEXT2, fontsize=6.5, ha='center', va='top')
    # Highlight prime entry window 10:00-10:30 with subtle top bar
    prime0 = mdates.date2num(datetime.datetime.combine(trade_date, datetime.time(10,0)))
    prime1 = mdates.date2num(datetime.datetime.combine(trade_date, datetime.time(10,30)))
    ax.axvspan(prime0, prime1, facecolor='#26a69a', alpha=0.04, zorder=0)
    ax.text(prime0+(prime1-prime0)*0.5, 0.988, '★ Prime',
            transform=ax.get_xaxis_transform(),
            color='#26a69a', fontsize=6.0, ha='center', va='top', alpha=0.8)

    # ── candlesticks ──────────────────────────────────────────────────────────
    draw_candles(ax, day_df)

    # ── VWAP ──────────────────────────────────────────────────────────────────
    if sess:
        cum_vol = day_df['volume'].cumsum()
        cum_vwp = (day_df['close'] * day_df['volume']).cumsum()
        vwap_ser = cum_vwp / cum_vol
        ax_vol.plot(day_df['et'].map(mdates.date2num), vwap_ser,
                    color=VWAP_C, linewidth=1.0, alpha=0.6, zorder=4, label='VWAP')
        # VWAP line on price pane too
        ax.plot(day_df['et'].map(mdates.date2num), vwap_ser,
                color=VWAP_C, linewidth=0.8, linestyle=':', alpha=0.4, zorder=2)

    # ── volume bars ────────────────────────────────────────────────────────────
    bw_vol = (mdates.date2num(datetime.datetime(2000,1,1,0,3,30))
            - mdates.date2num(datetime.datetime(2000,1,1,0,0,0)))
    for _, r in day_df.iterrows():
        col = UP if r['close'] >= r['open'] else DOWN
        ax_vol.bar(mdates.date2num(r['et']), r['volume'], width=bw_vol,
                   color=col, alpha=0.7, linewidth=0)
    ax_vol.set_ylabel('Vol', color=TEXT2, fontsize=7)
    ax_vol.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x,_: f'{x/1e6:.1f}M'))
    ax_vol.yaxis.set_major_locator(mticker.MaxNLocator(3))
    ax_vol.tick_params(axis='y', labelsize=7)

    # ── price range (include all strikes) ─────────────────────────────────────
    all_lo = [s['lo'] for s in spreads]; all_hi = [s['hi'] for s in spreads]
    px_lo  = day_df['low'].min();        px_hi  = day_df['high'].max()
    data_lo = min(px_lo, min(all_lo)); data_hi = max(px_hi, max(all_hi))
    pad = (data_hi - data_lo) * 0.20
    ax.set_ylim(data_lo - pad*0.3, data_hi + pad + pad*0.95)

    # ── spread bands (time-bounded) ────────────────────────────────────────────
    legend_items = []
    entry_quality_data = []  # (spread, score, flags) for legend

    for idx, sp in enumerate(spreads):
        sc = SPREAD_COLORS[idx % len(SPREAD_COLORS)]
        win = sp['net'] > 0

        # Time bounds: from first leg to last + 5-min padding each side
        x0 = mdates.date2num(sp['t_open']  - datetime.timedelta(minutes=4))
        x1 = mdates.date2num(sp['t_close'] + datetime.timedelta(minutes=4))
        # Fallback to day bounds if same-time (single tick)
        if x1 <= x0:
            x0 = mdates.date2num(day_df['et'].min() - datetime.timedelta(minutes=5))
            x1 = mdates.date2num(day_df['et'].max() + datetime.timedelta(minutes=5))

        band_h = max(sp['hi'] - sp['lo'], 1)
        ax.add_patch(Rectangle(
            (x0, sp['lo']), x1-x0, band_h,
            facecolor=sc, alpha=0.20 if win else 0.10, edgecolor='none', zorder=2
        ))
        # Border on the rectangle (win=solid, loss=dashed)
        border_ls = '-' if win else '--'
        ax.add_patch(Rectangle(
            (x0, sp['lo']), x1-x0, band_h,
            facecolor='none', edgecolor=sc, linewidth=0.8,
            linestyle=border_ls, alpha=0.7, zorder=3
        ))

        # Strike lines (short = dashed, long = dotted)
        short_strike = sp['hi'] if sp['type']=='P' else sp['lo']
        long_strike  = sp['lo'] if sp['type']=='P' else sp['hi']
        for strike, ls, lw, label_side in (
            (short_strike, '--', 1.0, 'short'),
            (long_strike,  ':',  0.7, 'long')
        ):
            ax.hlines(strike, x0, x1, color=sc, linewidth=lw, linestyle=ls, alpha=0.85, zorder=3)

        # Strike price labels (left side)
        x_lbl = mdates.date2num(day_df['et'].min() - datetime.timedelta(minutes=3))
        ax.text(x_lbl, short_strike, f'{short_strike:,.0f} S',
                color=sc, fontsize=6.5, va='center', ha='right', zorder=6)
        ax.text(x_lbl, long_strike, f'{long_strike:,.0f} L',
                color=sc, fontsize=6.0, va='center', ha='right', zorder=6, alpha=0.75)

        # DTE badge inside the band
        dte_txt = f"{sp['dte']}DTE" if sp['dte'] is not None else '?DTE'
        if sp['is_edt']: dte_txt += ' EDT'
        band_mid_x = (x0 + x1) / 2
        band_mid_y = (sp['lo'] + sp['hi']) / 2
        ax.text(band_mid_x, band_mid_y, dte_txt,
                color=sc, fontsize=6.0, ha='center', va='center',
                alpha=0.65, fontweight='bold', zorder=4)

        # Entry quality score
        q_score, q_flags = entry_quality(sp, sess, day_df, open_et)
        entry_quality_data.append((sp, q_score, q_flags))

        # Legend entry
        dte_str  = f"{sp['dte']}DTE" if sp['dte'] is not None else '?DTE'
        hold_str = f"{sp['hold']:.0f}min" if sp['hold'] < 180 else f"{sp['hold']/60:.1f}h"
        adds_str = f"+{sp['n_adds']}adds" if sp['n_adds'] > 0 else "no adds"
        q_str    = f"Q:{q_score}" if q_score is not None else ""
        sign = '+' if sp['net'] >= 0 else ''
        label = (f"{sp['direction']}  {sp['lo']:,.0f}/{sp['hi']:,.0f}  "
                 f"{dte_str}  ${sign}{sp['net']:,.0f}  {hold_str}  {adds_str}  {q_str}")
        legend_items.append(mpatches.Patch(facecolor=sc, alpha=0.8, label=label))

    # ── trade markers ─────────────────────────────────────────────────────────
    role_cfg = {
        'ENTRY': dict(color=ENTRY_C, marker='D', ms=7.5, lw=1.5, ls='--', prefix='E', zo=9),
        'EXIT':  dict(color=EXIT_C,  marker='s', ms=7.5, lw=1.3, ls='-.', prefix='X', zo=9),
        'SCALE': dict(color=SCALE_C, marker='o', ms=5.0, lw=0.8, ls=':',  prefix='S', zo=8),
    }
    label_data = []
    for leg in sorted(tagged, key=lambda x: x['time']):
        try: leg_dt = to_dt(leg['date'], leg['time'])
        except: continue
        ndx_px, _ = nearest_bar(day_df, leg_dt)
        if ndx_px is None: continue
        role = leg['role']; cfg = role_cfg[role]
        ax.axvline(mdates.date2num(leg_dt), color=cfg['color'],
                   linewidth=cfg['lw'], linestyle=cfg['ls'], alpha=0.55, zorder=cfg['zo'])
        ax.scatter(mdates.date2num(leg_dt), ndx_px,
                   marker=cfg['marker'], color=cfg['color'],
                   s=cfg['ms']**2, zorder=cfg['zo']+1,
                   edgecolors='white', linewidths=0.6)
        side = 'B' if leg['quantity'] > 0 else 'S'
        qty  = int(abs(leg['quantity']))
        label_data.append((leg_dt, ndx_px, cfg, leg, side, qty))

    # Staggered label placement (5 rows from top)
    label_data.sort(key=lambda x: x[0])
    ylim = ax.get_ylim(); y_span = ylim[1] - ylim[0]
    y_top = ylim[1] - y_span * 0.004
    n_rows = 5; row_h = y_span * 0.048
    row_last_x = [None] * n_rows

    for leg_dt, ndx_px, cfg, leg, side, qty in label_data:
        xn = mdates.date2num(leg_dt)
        best_row, best_dist = 0, -1
        for r in range(n_rows):
            if row_last_x[r] is None: best_row = r; break
            d = abs(xn - row_last_x[r])
            if d > best_dist: best_dist = d; best_row = r
        row_last_x[best_row] = xn
        label_y = y_top - best_row * row_h

        txt = f"{cfg['prefix']}  {leg['strike']:,.0f}{leg['option_type']}  {side}{qty} @{leg['price']:.1f}"
        ax.annotate(txt, xy=(xn, ndx_px), xytext=(xn, label_y),
                    color=cfg['color'], fontsize=6.5, va='bottom', ha='center',
                    arrowprops=dict(arrowstyle='-|>', color=cfg['color'],
                                    alpha=0.45, lw=0.65, mutation_scale=5.5),
                    bbox=dict(boxstyle='round,pad=0.2', fc=PANEL,
                              ec=cfg['color'], alpha=0.92, linewidth=0.85),
                    zorder=10)

    # ── rationale strip ────────────────────────────────────────────────────────
    ax_rat.set_ylim(0,1); ax_rat.set_yticks([])
    ax_rat.tick_params(bottom=False, labelbottom=False)
    for sp in ax_rat.spines.values(): sp.set_visible(False)
    ax_rat.set_facecolor(PANEL)

    line1, line2 = make_rationale(spreads, sess)
    ax_rat.text(0.010, 0.82, line1, transform=ax_rat.transAxes,
                color=TEXT, fontsize=8.0, va='top', fontweight='bold')
    ax_rat.text(0.010, 0.32, line2, transform=ax_rat.transAxes,
                color=TEXT2, fontsize=7.3, va='top')

    # Entry quality summary (one badge per spread, reading left to right)
    q_x_start = 0.58
    for qi, (sp, q_score, q_flags) in enumerate(entry_quality_data):
        sc = SPREAD_COLORS[qi % len(SPREAD_COLORS)]
        q_col = quality_color(q_score)
        q_txt = f"Q{q_score}" if q_score is not None else "Q?"
        top_flag = q_flags[0] if q_flags else ""
        ax_rat.text(q_x_start + qi*0.09, 0.82, f"{sp['direction'][:2]}P  {q_txt}",
                    transform=ax_rat.transAxes,
                    color=q_col, fontsize=7.0, va='top', fontweight='bold',
                    bbox=dict(boxstyle='round,pad=0.25', fc=BG, ec=q_col,
                              linewidth=0.9, alpha=0.9))
        ax_rat.text(q_x_start + qi*0.09, 0.28, top_flag,
                    transform=ax_rat.transAxes,
                    color=q_col, fontsize=6.2, va='top', alpha=0.85)

    # Regime badge (far right)
    if sess:
        rng_txt = f"{'TREND' if sess['trending'] else 'RANGE'}  {sess['direction']}  {sess['range']:.0f}pt"
        rc = '#ef5350' if sess['trending'] else '#26a69a'
        ax_rat.text(0.993, 0.5, rng_txt, transform=ax_rat.transAxes,
                    color=rc, fontsize=8.5, va='center', ha='right', fontweight='bold',
                    bbox=dict(boxstyle='round,pad=0.3', fc=BG, ec=rc, linewidth=1.2, alpha=0.95))

    # ── axes cosmetics ─────────────────────────────────────────────────────────
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=1))
    ax.xaxis.set_minor_locator(mdates.MinuteLocator(byminute=[0,15,30,45]))
    ax_vol.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    ax_vol.xaxis.set_major_locator(mdates.HourLocator(interval=1))
    ax_vol.xaxis.set_minor_locator(mdates.MinuteLocator(byminute=[0,15,30,45]))
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

    # Role legend (top-right)
    rl = [mpatches.Patch(color=ENTRY_C, label='E Entry ◆'),
          mpatches.Patch(color=EXIT_C,  label='X Exit ■'),
          mpatches.Patch(color=SCALE_C, label='S Scale ●'),
          mpatches.Patch(color=VWAP_C,  label='VWAP')]
    ax.legend(handles=rl, loc='upper right', fontsize=7,
              facecolor=PANEL, edgecolor=GRID, labelcolor=TEXT,
              framealpha=0.95, ncol=4, handlelength=0.9,
              borderpad=0.5, columnspacing=0.7)

    # Spread legend strip
    ax_leg.legend(handles=legend_items, loc='center', fontsize=7.5,
                  facecolor=PANEL, edgecolor=GRID, labelcolor=TEXT,
                  framealpha=0.95, ncol=min(len(legend_items), 4),
                  handlelength=0.9, borderpad=0.5, columnspacing=0.8)

    # Title
    accounts  = ', '.join(sorted(set(t['account'] for t in day_trades)))
    total_net = sum(s['net'] for s in spreads)
    cum_net   = cum_pnl_by_date.get(date_str, 0)
    dow       = datetime.date.fromisoformat(date_str).strftime('%A')
    n_adds_max= max((s['n_adds'] for s in spreads), default=0)
    edt_flag  = '  ⚠ EDT' if any(s['is_edt'] for s in spreads) else ''
    fig.suptitle(
        f'NDX 5-min  ·  {date_str} ({dow})  ·  {len(spreads)} spread(s)  ·  '
        f'Day: ${total_net:+,.0f}  ·  Cumulative: ${cum_net:+,.0f}  ·  '
        f'Max add-ins: {n_adds_max}{edt_flag}  ·  {accounts}',
        color=TEXT, fontsize=10.5, y=0.962, fontweight='bold'
    )

    out_path = OUT / f'{date_str}.png'
    fig.savefig(out_path, dpi=96, facecolor=BG)
    plt.close(fig)
    print(f'  {date_str}: {len(spreads)} spread(s), {len(tagged)} legs → {out_path.name}')

print(f'\nDone. {len(list(OUT.glob("*.png")))} charts in {OUT}')
