# 0_zgnb_StockTradebyZ 项目文档索引

> 本文档系统记录项目的代码设计实现、架构和模块划分，仅供开发人员参考。

## 项目概述

基于Z哥战法的A股量化选股系统，使用Python实现。主要功能包括从多个数据源获取A股历史K线数据，基于技术指标实现多种选股策略。

## 核心模块

| 模块 | 文档链接 | 说明 |
|------|----------|------|
| `fetch_kline.py` | [数据获取模块](./fetch_kline.md) | 多数据源K线数据获取，支持增量更新 |
| `select_stock.py` | [选股执行模块](./select_stock.md) | 批量执行选股策略 |
| `Selector.py` | [策略实现模块](./Selector.md) | 技术指标计算和选股策略实现 |
| `zgnb_zk_selector.py` | [ZGNB-ZK选股脚本](./zgnb_zk_selector.md) | 基于通达信公式的独立B1战法选股工具 |
| `backtest_zgnb.py` | [回测脚本](./backtest_zgnb.md) | Z哥B1战法T+1/T+2回测验证工具 |

## 模块架构

```
┌─────────────────────────────────────────────────────────┐
│                    数据获取层                             │
│  fetch_kline.py (AkShare/Tushare/Mootdx)               │
└────────────────────┬────────────────────────────────────┘
                     │ CSV数据
                     ▼
┌─────────────────────────────────────────────────────────┐
│                    选股执行层                             │
│  select_stock.py / zgnb_zk_selector.py                  │
└────────────────────┬────────────────────────────────────┘
                     │ 选股结果
                     ▼
┌─────────────────────────────────────────────────────────┐
│                    回测验证层                             │
│  backtest_zgnb.py (T+1买入/T+2卖出回测)                 │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│                    策略实现层                             │
│  Selector.py (7种选股策略)                              │
│  ├── BBIKDJSelector         - 少妇战法                   │
│  ├── SuperB1Selector        - SuperB1战法                │
│  ├── PeakKDJSelector        - 填坑战法                   │
│  ├── BBIShortLongSelector   - 补票战法                   │
│  ├── MA60CrossVolume...     - TePu战法                   │
│  ├── B1TrendSelector        - B1趋势战法                 │
│  └── BigBullishVolume...    - 暴力K战法                  │
└─────────────────────────────────────────────────────────┘
```

## 数据格式

K线数据CSV格式（每只股票一个文件）：
```csv
date,open,high,low,close,volume
2025-01-01,10.5,10.8,10.3,10.6,1000000
```

## 常用命令

### 环境准备
```bash
# 创建Python 3.12虚拟环境
conda create -n stock python=3.12
conda activate stock

# 安装依赖
pip install -r requirements.txt
```

### 数据获取
```bash
# 首次全量下载（50-2500亿市值）
python fetch_kline.py --start 20250101 --end today --stocklist ./stocklist.csv \
    --exclude-boards bj --out ./data --workers 15 --min-market-cap 50 --max-market-cap 2500

# 日常增量更新（2-5分钟）
python fetch_kline.py --start 20250101 --end today --stocklist ./stocklist.csv \
    --exclude-boards bj --out ./data --workers 15

# 排除创业板和科创板
python fetch_kline.py --start 20250101 --end today --stocklist ./stocklist.csv \
    --exclude-boards gem star bj --out ./data --workers 15

# 使用东方财富数据源
python fetch_kline.py --start 20250101 --end today --stocklist ./stocklist.csv \
    --exclude-boards bj --out ./data --workers 10 --akshare-source em

# 强制全量重新下载（覆盖已有数据）
python fetch_kline.py --start 20250101 --end today --stocklist ./stocklist.csv \
    --exclude-boards bj --out ./data --workers 15 --force-reload --akshare-source cdr
```

### 选股执行

**方式一：使用 select_stock.py**
```bash
python select_stock.py --data-dir ./data --config ./configs.json --date 2026-01-27

# 指定股票池
python select_stock.py --data-dir ./data --config ./configs.json --tickers "600000,600001"
```

**方式二：使用 zgnb_zk_selector.py**
```bash
# 默认10进程并行
python zgnb_zk_selector.py --data-dir ./data --date 2026-01-27

# 指定股票池
python zgnb_zk_selector.py --data-dir ./data --date 2026-01-27 --tickers "600000,600001"

# 输出到文件
python zgnb_zk_selector.py --data-dir ./data --date 2026-01-27 --output results.txt

# 使用20进程加速
python zgnb_zk_selector.py --data-dir ./data --date 2026-01-27 --workers 20
```

**方式三：回测验证**
```bash
# 默认回测（使用日志中最后一个日期）
python backtest_zgnb.py --data-dir ./data

# 指定回测日期
python backtest_zgnb.py --data-dir ./data --date 2026-01-20

# 回测所有可用日期（简洁模式）
python backtest_zgnb.py --all

# 回测所有可用日期（详细模式）
python backtest_zgnb.py --all --detail

# 列出所有可用日期
python backtest_zgnb.py --list-dates

# 指定输出目录
python backtest_zgnb.py --data-dir ./data --output-dir ./my_results
```

## 配置文件

### configs.json

选股策略配置文件，位于项目根目录：

```json
{
  "selectors": [
    {
      "class": "BBIKDJSelector",
      "alias": "少妇战法",
      "activate": true,
      "params": {
        "j_threshold": -5,
        "bbi_min_window": 90
      }
    }
  ]
}
```

### stocklist.csv

股票列表文件（可选），用于指定下载的股票：

```csv
code,name
600000,浦发银行
600001,邯郸钢铁
```

## 日志文件

| 日志文件 | 说明 |
|----------|------|
| `fetch.log` | 数据获取日志 |
| `select_results.log` | 选股结果日志 |
| `zgnb_zk_selector.log` | ZGNB选股脚本执行日志 |
| `zgnb_zk_results.log` | ZGNB选股结果（供回测使用，支持多日期追加） |
| `backtest_zgnb.log` | 回测脚本执行日志 |
| `backtest_results/backtest_results.log` | 单日回测结果报告 |
| `backtest_results/backtest_summary_all.log` | 批量回测汇总报告 |

## 技术栈

- **Python**: 3.12+
- **数据处理**: pandas, numpy
- **数据源**: AkShare, Tushare, Mootdx
- **技术指标**: 自研实现（KDJ、BBI、RSI、MACD等）

## 更新日志

| 日期 | 更新内容 |
|------|----------|
| 2026-03-04 | backtest_zgnb.py 新增多日期批量回测支持（--all、--detail、--list-dates参数） |
| 2026-03-04 | zgnb_zk_selector.py 新增多进程并行支持，默认10进程 |
| 2026-03-04 | fetch_kline.py 新增AkShare多数据源支持（腾讯/东财/新浪） |
| 2026-03-04 | 新增 backtest_zgnb.py 回测脚本及完整文档 |
| 2026-03-04 | 新增 zgnb_zk_selector.py 独立选股脚本及完整文档 |
| 2025-XX-XX | 新增暴力K战法和B1趋势战法 |
| 2025-XX-XX | 新增MA60金叉量能战法 |

## 项目结构

```
0_zgnb_StockTradebyZ/
├── data/                   # K线数据目录
│   ├── 000001.csv
│   ├── 600000.csv
│   └── ...
├── backtest_results/       # 回测结果目录
│   ├── backtest_detail_YYYYMMDD.csv  # 单日回测明细
│   ├── backtest_results.log          # 单日回测报告
│   └── backtest_summary_all.log      # 批量回测汇总报告
├── llmdoc/                 # 文档目录
│   ├── index.md
│   ├── fetch_kline.md
│   ├── select_stock.md
│   ├── Selector.md
│   ├── zgnb_zk_selector.md
│   └── backtest_zgnb.md
├── configs.json            # 选股配置
├── stocklist.csv           # 股票列表（可选）
├── fetch_kline.py          # 数据获取模块
├── select_stock.py         # 选股执行模块
├── Selector.py             # 策略实现模块
├── zgnb_zk_selector.py     # ZGNB独立选股脚本
├── backtest_zgnb.py        # 回测脚本
└── requirements.txt        # Python依赖
```

## 开发指南

### 添加新策略

1. 在 `Selector.py` 中实现新策略类
2. 继承基础接口，实现 `select()` 方法
3. 在 `configs.json` 中添加配置项
4. 更新文档

### 数据格式约定

- 所有DataFrame必须包含: date, open, high, low, close, volume
- date列需转换为 pd.Timestamp 类型
- 数据按日期升序排列

### 命名规范

- 策略类: `XxxSelector`
- 指标函数: `compute_xxx()`
- 辅助函数: `check_xxx()`
