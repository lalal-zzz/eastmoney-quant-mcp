import sys
import os

# Redirect output to file for reliable capture
out_file = r'c:\Users\20127\Desktop\opensource_project\stock-analysis-mcp\scripts\run_output.txt'

sys.stdout = open(out_file, 'w', encoding='utf-8')
sys.stderr = sys.stdout

print("=== Phase 4: Rising Candidates ===")
sys.stdout.flush()

sys.path.insert(0, r'c:\Users\20127\Desktop\opensource_project\stock-analysis-mcp\src')

print("Step 0: Imports...")
sys.stdout.flush()

from stock_analysis_mcp.tools.research import screen_rising_candidates, prepare_stock_analysis
print("Imports OK")
sys.stdout.flush()

import json
import asyncio

os.makedirs('reports/rising_candidates', exist_ok=True)

# Step 1: Screen
print("=" * 60)
print("Step 1: screen_rising_candidates")
print("=" * 60)
sys.stdout.flush()

result = screen_rising_candidates(top_n=20)
print(f"universe={result['universe_size']}, scanned={result['scanned']}")
print(f"candidates: {len(result['results'])}")
print(f"warning: {result.get('warning')}")
sys.stdout.flush()

candidates = result['results']

for i, r in enumerate(candidates):
    sym = r.get('symbol', '?')
    name = r.get('name', '?')
    score = r['score']
    pattern = r.get('pattern', '?')
    sig_date = r.get('signal_date', '?')
    bd = r.get('score_breakdown', {})
    print(f"{i+1:2d}. {sym} {name} score={score:.1f} pattern={pattern} date={sig_date}")
    print(f"    pat={bd.get('pattern',0):.1f} daily={bd.get('daily',0):.1f} "
          f"higher={bd.get('higher_timeframe',0):.1f} vol={bd.get('volume',0):.1f} "
          f"sector={bd.get('sector',0):.1f} conf={bd.get('confluence',0):.1f} "
          f"risk={bd.get('risk_penalty',0):.1f}")
sys.stdout.flush()

with open('reports/rising_candidates/candidates.json', 'w', encoding='utf-8') as f:
    json.dump(result, f, ensure_ascii=False, indent=2, default=str)
print("Saved: reports/rising_candidates/candidates.json")
sys.stdout.flush()

# Step 2: Evidence
print()
print("=" * 60)
print("Step 2: prepare_stock_analysis (evidence)")
print("=" * 60)
sys.stdout.flush()

top_n_ev = min(10, len(candidates))
all_evidence = {}
chart_paths = {}

async def gen_evidence(sym, name):
    try:
        ev = await prepare_stock_analysis(symbol=sym, days=500, include_chart=True)
        return sym, ev, None
    except Exception as e:
        return sym, None, f"{sym} {name}: {e}"

async def main_ev():
    tasks = [gen_evidence(c.get('symbol','?'), c.get('name','?')) for c in candidates[:top_n_ev]]
    return await asyncio.gather(*tasks)

results_ev = asyncio.run(main_ev())

for sym, ev, err in results_ev:
    if err:
        print(f"  [ERROR] {err}")
        sys.stdout.flush()
        continue
    all_evidence[sym] = ev
    charts = ev.get('charts', {})
    if charts:
        chart_paths[sym] = charts
    stock_info = ev.get('stock', {})
    dq = ev.get('data_quality', {})
    tf = ev.get('timeframes', {})
    daily = tf.get('daily', {})
    weekly = tf.get('weekly', {})
    monthly = tf.get('monthly', {})
    patterns = ev.get('patterns', [])
    
    print(f"\n  {sym} {stock_info.get('name', '?')}:")
    print(f"    data: {dq.get('bars',0)} bars, {dq.get('first_date','?')} ~ {dq.get('last_date','?')}")
    print(f"    daily: close={daily.get('close','?')} trend={daily.get('trend','?')}")
    print(f"    weekly: trend={weekly.get('trend','?')}  monthly: trend={monthly.get('trend','?')}")
    print(f"    patterns: {len(patterns)}")
    for p in patterns[:3]:
        print(f"      - {p.get('pattern','?')} score={p.get('score',0):.1f} stage={p.get('stage','?')}")
    if charts:
        print(f"    chart: daily={charts.get('daily','N/A')}")
    if ev.get('warnings'):
        print(f"    warnings: {ev['warnings']}")
    sys.stdout.flush()

with open('reports/rising_candidates/evidence.json', 'w', encoding='utf-8') as f:
    json.dump(all_evidence, f, ensure_ascii=False, indent=2, default=str)
print(f"\nSaved: reports/rising_candidates/evidence.json ({len(all_evidence)} stocks)")
sys.stdout.flush()

# Step 3: Charts
print()
print("=" * 60)
print("Step 3: Chart paths")
print("=" * 60)
if chart_paths:
    for sym, paths in chart_paths.items():
        print(f"  {sym}:")
        for k, v in paths.items():
            if k != 'bars':
                print(f"    {k}: {v}")
else:
    print("  No charts generated")
sys.stdout.flush()

# Step 4: File list
print()
print("=" * 60)
print("Saved files")
print("=" * 60)
saved = ['reports/rising_candidates/candidates.json', 'reports/rising_candidates/evidence.json']
for sym, paths in chart_paths.items():
    for k, v in paths.items():
        if k != 'bars' and isinstance(v, str):
            saved.append(v)
for f in saved:
    e = os.path.exists(f)
    print(f"  {'[OK]' if e else '[MISS]'} {f}")

print()
print("Phase 4 DONE!")
sys.stdout.flush()
sys.stdout.close()
