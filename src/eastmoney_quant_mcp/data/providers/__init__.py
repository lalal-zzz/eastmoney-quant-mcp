"""
多数据源 provider 层

数据分工(降级链, 主库键始终为东财代码):
- 个股 K 线:   腾讯 fqkline/mkline → 东财 akshare → 搜狐 hisHq(不复权, 最后兜底)
- 多周期 K 线: 腾讯 mkline/fqkline → 东财 push2his(熔断保护)
- 板块 K 线:   东财单源(腾讯仅当日1根且成分口径不同, 跨源混写有断层; 带熔断)
- 板块成分股:  新浪 getHQNodeData → 东财 clist → 搜狐 HTML(+腾讯批量行情)
- 板块列表+四档资金流/人气排名: 东财(无替代)

腾讯/搜狐/新浪均无四档(超大/大/中/小单)资金流明细, 该数据仅东财提供。

接入坑(实测 2026-08):
- 腾讯日K行序为 [时间, open, close, high, low, volume], 第2列开盘第3列收盘
- 腾讯 fqkline 单次最多 640 根(count 更大反而异常), 深历史按日期区间翻页
- 腾讯板块(pt)K线一律只返回最新 1 根
- 搜狐 WAF: 拒绝新版 edge 指纹(用 edge99)、拒绝携带域外 Cookie、
  拒绝 end>今天 的日期; hisHq 对高频 IP 会间歇性 503
- 新浪接口必须带 Referer: https://finance.sina.com.cn
"""

from . import boardmap, sina, sohu, tencent

__all__ = ["boardmap", "sina", "sohu", "tencent"]
