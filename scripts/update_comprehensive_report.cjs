/**
 * 更新综合分析报告，覆盖全部46个板块
 * 读取更新后的数据文件，重新生成综合分析报告
 */
const fs = require('fs');
const path = require('path');

// 读取数据
const stockReports = JSON.parse(fs.readFileSync('reports/new_business_analysis/stock_reports.json', 'utf-8'));
const risingStocks = JSON.parse(fs.readFileSync('reports/new_business_analysis/rising_stocks.json', 'utf-8'));
const keyLevels = JSON.parse(fs.readFileSync('reports/new_business_analysis/key_levels.json', 'utf-8'));
const sectors = JSON.parse(fs.readFileSync('reports/new_business_analysis/sector_list.json', 'utf-8'));
const existingReport = fs.readFileSync('reports/comprehensive_analysis_report.md', 'utf-8');

console.log(`数据加载完成:`);
console.log(`  个股报告: ${stockReports.length} 条`);
console.log(`  上涨形态个股: ${risingStocks.length} 条`);
console.log(`  关键位数据: ${keyLevels.length} 条`);
console.log(`  板块列表: ${sectors.length} 个`);

// 板块分类
const sectorCategories = {
  'AI相关': ['AI应用', 'AIGC概念', 'AI智能体', '多模态AI', 'AI语料', '智谱AI概念', 'AI芯片', 'AI制药（医疗）', 'AI手机', 'AIPC', 'AI眼镜'],
  '机器人': ['虚拟机器人', '机器人执行器', '人形机器人', '机器人概念'],
  '芯片半导体': ['第四代半导体', '第三代半导体', '汽车芯片', '存储芯片', '国产芯片', '半导体概念', '半导体'],
  '数据算力': ['数据要素', '时空大数据', '数字经济', '大数据', '云计算', '算力概念'],
  '新能源': ['新能源', '光伏概念', '新能源车', '光伏设备'],
  '储能氢能': ['熔盐储能', '氢能源', '储能概念'],
  '通信': ['F5G概念', '量子科技', '物联网', '5G概念'],
  '生物医药': ['转基因', '基因测序'],
  '其他': ['区块链', '跨境电商', '元宇宙概念', '低空经济', '人工智能']
};

// 按板块统计上涨形态个股
const sectorRisingMap = {};
for (const stock of risingStocks) {
  const sector = stock.sector_name;
  if (!sectorRisingMap[sector]) sectorRisingMap[sector] = [];
  sectorRisingMap[sector].push(stock);
}

// 按板块统计分析报告数
const sectorReportCount = {};
for (const report of stockReports) {
  const sector = report.sector_name;
  sectorReportCount[sector] = (sectorReportCount[sector] || 0) + 1;
}

// 统计不重复个股数
const uniqueRisingSymbols = new Set(risingStocks.map(s => s.symbol));

// 统计形态分布
const patternCounts = {};
for (const s of risingStocks) {
  const p = s.pattern_cn || s.pattern;
  patternCounts[p] = (patternCounts[p] || 0) + 1;
}

// === 更新第一章 ===
let updatedReport = existingReport;

// 替换数字
updatedReport = updatedReport.replace(
  /新业态板块个股报告 \| \d+ 份/,
  `新业态板块个股报告 | ${stockReports.length} 份`
);
updatedReport = updatedReport.replace(
  /上涨形态个股 \| \d+ 只/,
  `上涨形态个股 | ${risingStocks.length} 只`
);
updatedReport = updatedReport.replace(
  /关键位数据 \| \d+ 条/,
  `关键位数据 | ${keyLevels.length} 条`
);

// === 生成新的第五章 ===
const chapter5Lines = [];
chapter5Lines.push('## 五、新业态板块个股分析');
chapter5Lines.push('');
chapter5Lines.push('### 5.1 各板块上涨形态个股分布');
chapter5Lines.push('');
chapter5Lines.push('按板块类别分组展示全部46个板块的上涨形态个股分布：');
chapter5Lines.push('');

// 按分类生成表格
for (const [category, sectorNames] of Object.entries(sectorCategories)) {
  chapter5Lines.push(`#### ${category}（${sectorNames.length}个板块）`);
  chapter5Lines.push('');
  chapter5Lines.push('| 板块 | 上涨形态个股数 | 分析报告数 | 代表个股 |');
  chapter5Lines.push('|------|--------------|-----------|---------|');

  for (const sectorName of sectorNames) {
    const rising = sectorRisingMap[sectorName] || [];
    const reportCount = sectorReportCount[sectorName] || 0;

    // 获取代表个股（取前3个不重复的）
    const seenNames = new Set();
    const representatives = [];
    for (const s of rising) {
      if (!seenNames.has(s.name) && representatives.length < 3) {
        seenNames.add(s.name);
        representatives.push(s.name);
      }
    }
    // 如果上涨个股不足3个，从报告中补充
    if (representatives.length < 3) {
      for (const r of stockReports) {
        if (r.sector_name === sectorName && !seenNames.has(r.name)) {
          seenNames.add(r.name);
          representatives.push(r.name);
        }
        if (representatives.length >= 3) break;
      }
    }

    const repStr = representatives.length > 0 ? representatives.join('、') : '-';
    chapter5Lines.push(`| ${sectorName} | ${rising.length} | ${reportCount} | ${repStr} |`);
  }
  chapter5Lines.push('');
}

// 统计概要
const patternSummary = Object.entries(patternCounts)
  .map(([k, v]) => `${k}${v}条（占比${(v / risingStocks.length * 100).toFixed(1)}%）`)
  .join('，');

chapter5Lines.push(`**统计概要：** 共${risingStocks.length}条上涨形态记录，涉及${uniqueRisingSymbols.size}只不重复个股，覆盖${Object.keys(sectorRisingMap).length}个板块。形态分布：${patternSummary}。`);
chapter5Lines.push('');

// === 5.2 重点个股技术特征 ===
chapter5Lines.push('### 5.2 重点个股技术特征');
chapter5Lines.push('');
chapter5Lines.push(`在${stockReports.length}份分析报告中，有${risingStocks.length}只个股处于多头排列状态。`);
chapter5Lines.push('');

// 按板块类别展示重点个股
for (const [category, sectorNames] of Object.entries(sectorCategories)) {
  // 收集该分类下的多头排列个股
  const categoryStocks = [];
  for (const sectorName of sectorNames) {
    const rising = sectorRisingMap[sectorName] || [];
    for (const s of rising) {
      // 从stockReports中找详细信息
      const report = stockReports.find(r => r.symbol === s.symbol && r.sector_name === sectorName);
      if (report) {
        categoryStocks.push({ ...s, report });
      }
    }
  }

  if (categoryStocks.length === 0) continue;

  chapter5Lines.push(`#### ${category}`);
  chapter5Lines.push('');
  chapter5Lines.push('| 代码 | 名称 | 板块 | 最新价 | RSI | MACD信号 | 趋势方向 | 风险等级 |');
  chapter5Lines.push('|------|------|------|--------|-----|---------|---------|---------|');

  // 每个分类最多展示10个
  const shown = new Set();
  let count = 0;
  for (const s of categoryStocks) {
    if (shown.has(s.symbol)) continue;
    if (count >= 10) break;
    shown.add(s.symbol);
    const r = s.report;
    chapter5Lines.push(`| ${r.symbol} | ${r.name} | ${r.sector_name} | ${r.latest_price} | ${r.rsi?.toFixed(1) || '-'} | ${r.macd_signal || '-'} | ${r.trend_direction || '-'} | ${r.risk_level || '-'} |`);
    count++;
  }
  chapter5Lines.push('');
}

const newChapter5 = chapter5Lines.join('\n');

// === 生成新的第八章 8.2 和 8.3 ===
// 8.2 重点关注板块
const sector82Lines = [];
sector82Lines.push('### 8.2 重点关注板块');
sector82Lines.push('');
sector82Lines.push('| 优先级 | 板块 | 上涨个股数 | 理由 |');
sector82Lines.push('|--------|------|-----------|------|');

// 按上涨个股数排序板块
const sectorRisingSorted = Object.entries(sectorRisingMap)
  .map(([name, stocks]) => ({ name, count: stocks.length, uniqueCount: new Set(stocks.map(s => s.symbol)).size }))
  .sort((a, b) => b.count - a.count);

// 获取板块资金信息
const sectorInflowMap = {};
for (const s of sectors) {
  sectorInflowMap[s.sector_name] = s.main_net_inflow;
}

// 生成优先级
const top5 = sectorRisingSorted.slice(0, 5);
const mid5 = sectorRisingSorted.slice(5, 10);
const rest = sectorRisingSorted.slice(10);

for (const s of top5) {
  const inflow = sectorInflowMap[s.name];
  const inflowStr = inflow ? `主力净流入${(inflow / 1e8).toFixed(1)}亿` : '';
  sector82Lines.push(`| ★★★★★ | ${s.name} | ${s.count} | 上涨个股最多，${inflowStr} |`);
}
for (const s of mid5) {
  sector82Lines.push(`| ★★★★ | ${s.name} | ${s.count} | 上涨个股较多，形态信号活跃 |`);
}
for (const s of rest.slice(0, 5)) {
  sector82Lines.push(`| ★★★ | ${s.name} | ${s.count} | 有个股机会，需结合资金面判断 |`);
}
sector82Lines.push('');

const newSection82 = sector82Lines.join('\n');

// 8.3 重点关注个股 - 补充新板块强势个股
const sector83Lines = [];
sector83Lines.push('### 8.3 重点关注个股');
sector83Lines.push('');
sector83Lines.push('基于综合评分和多维度分析，重点关注以下个股：');
sector83Lines.push('');
sector83Lines.push('| 排名 | 代码 | 名称 | 评分 | 形态 | 核心亮点 |');
sector83Lines.push('|------|------|------|------|------|---------|');

// 保留原有的TOP5
sector83Lines.push('| 1 | 601658 | 邮储银行 | 77.5 | 平台放量突破 | 平台放量突破，横盘突破确认，量能2.63倍 |');
sector83Lines.push('| 2 | 002386 | 天原股份 | 74.11 | M形颈线支撑 | 形态标准度满分，多周期共振 |');
sector83Lines.push('| 3 | 600845 | 宝信软件 | 71.87 | M形颈线支撑 | M形颈线支撑，上升趋势确认 |');
sector83Lines.push('| 4 | 600674 | 川投能源 | 71.22 | 平台放量突破 | 平台放量突破，量能充沛 |');
sector83Lines.push('| 5 | 600177 | 雅戈尔 | 70.18 | 平台放量突破 | W底右底形成，趋势向好 |');
sector83Lines.push('');

// 新业态板块跟踪个股 - 按板块分类展示
sector83Lines.push('新业态板块中以下个股值得跟踪（按板块分类）：');
sector83Lines.push('');
sector83Lines.push('| 代码 | 名称 | 所属板块 | 形态 | 趋势 |');
sector83Lines.push('|------|------|---------|------|------|');

// 从每个主要板块选几个代表性个股
const shownSymbols = new Set();
for (const sectorInfo of sectorRisingSorted.slice(0, 15)) {
  const sectorName = sectorInfo.name;
  const rising = sectorRisingMap[sectorName] || [];
  let added = 0;
  for (const s of rising) {
    if (shownSymbols.has(s.symbol)) continue;
    if (added >= 2) break;
    shownSymbols.add(s.symbol);
    const report = stockReports.find(r => r.symbol === s.symbol);
    const trend = report?.trend_direction || s.trend || '-';
    sector83Lines.push(`| ${s.symbol} | ${s.name} | ${sectorName} | ${s.variant || s.pattern_cn} | ${trend} |`);
    added++;
  }
}
sector83Lines.push('');

const newSection83 = sector83Lines.join('\n');

// === 替换报告中的内容 ===

// 替换第五章（从 "## 五、" 到 "## 六、"）
const ch5Start = updatedReport.indexOf('## 五、新业态板块个股分析');
const ch5End = updatedReport.indexOf('## 六、回测验证');
if (ch5Start !== -1 && ch5End !== -1) {
  updatedReport = updatedReport.substring(0, ch5Start) + newChapter5 + '\n\n' + updatedReport.substring(ch5End);
}

// 替换8.2（从 "### 8.2" 到 "### 8.3"）
const s82Start = updatedReport.indexOf('### 8.2 重点关注板块');
const s82End = updatedReport.indexOf('### 8.3 重点关注个股');
if (s82Start !== -1 && s82End !== -1) {
  updatedReport = updatedReport.substring(0, s82Start) + newSection82 + '\n\n' + updatedReport.substring(s82End);
}

// 替换8.3（从 "### 8.3" 到 "### 8.4"）
const s83Start = updatedReport.indexOf('### 8.3 重点关注个股');
const s83End = updatedReport.indexOf('### 8.4 风险提示');
if (s83Start !== -1 && s83End !== -1) {
  updatedReport = updatedReport.substring(0, s83Start) + newSection83 + '\n' + updatedReport.substring(s83End);
}

// 写入文件
fs.writeFileSync('reports/comprehensive_analysis_report.md', updatedReport, 'utf-8');

// 输出统计
const lineCount = updatedReport.split('\n').length;
const sectorWithRising = Object.keys(sectorRisingMap).length;
console.log('\n=== 更新完成 ===');
console.log(`报告总行数: ${lineCount}`);
console.log(`覆盖板块数: ${sectors.length} 个`);
console.log(`有上涨个股的板块: ${sectorWithRising} 个`);
console.log(`个股报告数: ${stockReports.length}`);
console.log(`上涨形态个股: ${risingStocks.length}`);
console.log(`关键位数据: ${keyLevels.length}`);

// 验证46个板块都有数据
const allSectorNames = sectors.map(s => s.sector_name);
const missingSectors = allSectorNames.filter(name => !sectorReportCount[name]);
if (missingSectors.length > 0) {
  console.log(`\n警告: 以下板块缺少个股报告: ${missingSectors.join(', ')}`);
} else {
  console.log('\n✓ 全部46个板块均有数据');
}
