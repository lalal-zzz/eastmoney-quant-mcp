import asyncio
import json
from pathlib import Path

import pandas as pd
from eastmoney_quant_mcp.tools.research import prepare_stock_analysis
from eastmoney_quant_mcp.strategies.patterns import prepare_df

OUT = Path(__file__).resolve().parent

async def main():
    candidates = json.loads((OUT / 'candidates.json').read_text(encoding='utf-8'))
    packets = []
    for candidate in candidates['results']:
        symbol = candidate['symbol']
        try:
            packet = await prepare_stock_analysis(symbol, days=500, include_chart=True, refresh_if_stale=False)
            df = prepare_df('stocks', symbol, tail=500)
            df.to_csv(OUT / f'{symbol}_ohlcv.csv', index=False, encoding='utf-8-sig')
            c = df.close
            v = df.volume
            packet['review_metrics'] = {
                'ma': {str(w): float(c.tail(w).mean()) if len(c)>=w else None for w in (20,60,120,250)},
                'ma20_change_5_pct': float((c.tail(20).mean()/c.iloc[-25:-5].mean()-1)*100),
                'ma60_change_5_pct': float((c.tail(60).mean()/c.iloc[-65:-5].mean()-1)*100),
                'volume5_over20': float(v.tail(5).mean()/v.tail(20).mean()),
                'last_volume_over_previous20': float(v.iloc[-1]/v.iloc[-21:-1].mean()),
                'distance_ma20_pct': float((c.iloc[-1]/c.tail(20).mean()-1)*100),
                'distance_ma60_pct': float((c.iloc[-1]/c.tail(60).mean()-1)*100),
                'last20_high': float(df.high.tail(20).max()),
                'last20_low': float(df.low.tail(20).min()),
                'last60_high': float(df.high.tail(60).max()),
                'last60_low': float(df.low.tail(60).min()),
                'return20_pct': float((c.iloc[-1]/c.iloc[-21]-1)*100),
            }
            packet['screen_signal'] = candidate
            packets.append(packet)
            (OUT / f'{symbol}_evidence.json').write_text(json.dumps(packet,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
            print(symbol, candidate.get('name'), packet['data_quality'], packet['warnings'], flush=True)
        except Exception as exc:
            print(symbol, 'ERROR',repr(exc),flush=True)
    (OUT / 'evidence.json').write_text(json.dumps(packets,ensure_ascii=False,indent=2,default=str),encoding='utf-8')

asyncio.run(main())
