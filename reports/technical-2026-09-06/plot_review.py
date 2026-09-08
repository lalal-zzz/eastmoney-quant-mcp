import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import pandas as pd
OUT=Path(__file__).resolve().parent
plt.rcParams['font.sans-serif']=['Microsoft YaHei']
plt.rcParams['axes.unicode_minus']=False
packets=json.loads((OUT/'evidence.json').read_text(encoding='utf-8'))
for page in range(5):
    group=packets[page*4:page*4+4]
    fig,axes=plt.subplots(len(group),3,figsize=(21,4*len(group)),squeeze=False)
    for row,p in enumerate(group):
        s=p['screen_signal']; df=pd.read_csv(OUT/f"{s['symbol']}_ohlcv.csv")
        df['date']=pd.to_datetime(df.date); df=df.set_index('date')
        for col,(rule,label,tail) in enumerate([('ME','月',26),('W-FRI','周',70),(None,'日',100)]):
            d=df.resample(rule).agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'}).dropna() if rule else df
            d=d.copy()
            for w in (5,20,60): d[f'ma{w}']=d.close.rolling(w).mean()
            d=d.tail(tail); ax=axes[row,col]
            for i,b in enumerate(d.itertuples()):
                color='#cf353c' if b.close>=b.open else '#16856a'
                ax.vlines(i,b.low,b.high,color=color,lw=.7)
                ax.add_patch(Rectangle((i-.3,min(b.open,b.close)),.6,max(abs(b.close-b.open),.001),facecolor=color,edgecolor=color,lw=.4))
            for w,color in [(5,'#d09c22'),(20,'#345ddd'),(60,'#932bbb')]: ax.plot(range(len(d)),d[f'ma{w}'],lw=1,color=color,label=f'MA{w}')
            av=ax.twinx(); av.bar(range(len(d)),d.volume,color='#9aafba',alpha=.16); av.set_ylim(0,d.volume.max()*5); av.set_yticks([])
            ticks=list(range(0,len(d),max(1,len(d)//5))); ax.set_xticks(ticks,[d.index[i].strftime('%y-%m-%d') for i in ticks],fontsize=8)
            ax.set_title(f"{s['symbol']} {s['name']} {label}K | 收 {d.close.iloc[-1]:.2f}",fontsize=11)
            ax.grid(alpha=.15); ax.legend(fontsize=7,loc='upper left')
    fig.suptitle('截至2026-09-04：月 → 周 → 日（9月月线未收盘）；淡灰柱为成交量',fontsize=16)
    fig.tight_layout(rect=(0,0,1,.97)); fig.savefig(OUT/f'review_{page+1}.png',dpi=130); plt.close(fig)
