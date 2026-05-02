#!/usr/bin/env python3
"""Plot NDX 1-minute bars for today."""

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

df = pd.read_csv('/tmp/NDX_1m_7d.csv', index_col=0, parse_dates=True)
df.columns = ['Open', 'High', 'Low', 'Close', 'Adj Close', 'Volume']

today = df[df.index.date == pd.Timestamp('2026-05-01').date()]

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), gridspec_kw={'height_ratios': [3, 1]}, sharex=True)
fig.suptitle('NDX — 1-Min Bars — 2026-05-01', fontsize=14, fontweight='bold')

# Candlestick-style OHLC using bar chart
width = pd.Timedelta(seconds=40)
up   = today[today['Close'] >= today['Open']]
down = today[today['Close'] <  today['Open']]

ax1.bar(up.index,   up['Close']   - up['Open'],   width, bottom=up['Open'],   color='#26a69a', linewidth=0)
ax1.bar(up.index,   up['High']    - up['Close'],   width * 0.15, bottom=up['Close'],  color='#26a69a', linewidth=0)
ax1.bar(up.index,   up['Open']    - up['Low'],     width * 0.15, bottom=up['Low'],    color='#26a69a', linewidth=0)
ax1.bar(down.index, down['Open']  - down['Close'], width, bottom=down['Close'], color='#ef5350', linewidth=0)
ax1.bar(down.index, down['High']  - down['Open'],  width * 0.15, bottom=down['Open'],  color='#ef5350', linewidth=0)
ax1.bar(down.index, down['Close'] - down['Low'],   width * 0.15, bottom=down['Low'],   color='#ef5350', linewidth=0)

ax1.set_ylabel('Price')
ax1.grid(True, alpha=0.3)
ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'{x:,.0f}'))

# Volume
ax2.bar(today.index, today['Volume'], width=width, color=['#26a69a' if c >= o else '#ef5350'
        for c, o in zip(today['Close'], today['Open'])], alpha=0.7)
ax2.set_ylabel('Volume')
ax2.grid(True, alpha=0.3)
ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'{x/1e6:.0f}M'))

ax2.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
ax2.xaxis.set_major_locator(mdates.MinuteLocator(byminute=range(0, 60, 30)))
plt.xticks(rotation=45)

plt.tight_layout()
plt.savefig('/tmp/NDX_today.png', dpi=150, bbox_inches='tight')
print(f"Saved chart to /tmp/NDX_today.png ({len(today)} bars)")
print(f"Open: {today['Open'].iloc[0]:,.2f}  High: {today['High'].max():,.2f}  Low: {today['Low'].min():,.2f}  Last: {today['Close'].iloc[-1]:,.2f}")
plt.show()
