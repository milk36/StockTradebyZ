# select_stock.py - 选股执行模块

## 概述

选股执行模块负责批量加载股票数据，根据配置文件执行选股策略，并输出选股结果。

## 架构设计

```
select_stock.py
├── 配置加载
│   └── load_config() - 从JSON加载策略配置
│
├── 数据加载
│   └── load_data() - 从CSV目录加载股票数据
│
├── 选股执行
│   ├── run_selector() - 执行单个策略
│   └── main() - 主函数，解析参数并执行
│
└── 结果输出
    └── 输出到控制台和日志文件
```

## 配置文件格式

`configs.json` 示例：

```json
{
  "selectors": [
    {
      "class": "BBIKDJSelector",
      "alias": "少妇战法",
      "activate": true,
      "params": {
        "j_threshold": -5,
        "bbi_min_window": 90,
        "max_window": 90,
        "price_range_pct": 100.0,
        "bbi_q_threshold": 0.05,
        "j_q_threshold": 0.10
      }
    },
    {
      "class": "SuperB1Selector",
      "alias": "SuperB1战法",
      "activate": true,
      "params": {
        "lookback_n": 60,
        "close_vol_pct": 0.05,
        "price_drop_pct": 0.03,
        "j_threshold": -5,
        "j_q_threshold": 0.10,
        "B1_params": {
          "j_threshold": -5,
          "bbi_min_window": 90,
          "max_window": 90
        }
      }
    },
    {
      "class": "PeakKDJSelector",
      "alias": "填坑战法",
      "activate": false,
      "params": {
        "j_threshold": -5,
        "max_window": 90,
        "fluc_threshold": 0.03,
        "gap_threshold": 0.02,
        "j_q_threshold": 0.10
      }
    },
    {
      "class": "BBIShortLongSelector",
      "alias": "补票战法",
      "activate": false,
      "params": {
        "n_short": 3,
        "n_long": 21,
        "m": 3,
        "bbi_min_window": 90,
        "max_window": 150,
        "bbi_q_threshold": 0.05,
        "upper_rsv_threshold": 75,
        "lower_rsv_threshold": 25
      }
    },
    {
      "class": "MA60CrossVolumeWaveSelector",
      "alias": "TePu战法",
      "activate": false,
      "params": {
        "lookback_n": 60,
        "vol_multiple": 1.5,
        "j_threshold": -5.0,
        "j_q_threshold": 0.10,
        "ma60_slope_days": 5,
        "max_window": 120
      }
    },
    {
      "class": "B1TrendSelector",
      "alias": "B1趋势战法",
      "activate": false,
      "params": {
        "j_threshold": 13,
        "max_window": 120
      }
    },
    {
      "class": "BigBullishVolumeSelector",
      "alias": "暴力K战法",
      "activate": false,
      "params": {
        "up_pct_threshold": 0.04,
        "upper_wick_pct_max": 0.5,
        "vol_lookback_n": 20,
        "vol_multiple": 1.5,
        "require_bullish_close": true,
        "ignore_zero_volume": true,
        "close_lt_zxdq_mult": 1.0
      }
    }
  ]
}
```

## 支持的策略类

| 类名 | 别名 | 说明 |
|------|------|------|
| BBIKDJSelector | 少妇战法 | BBI上升+KDJ低位 |
| SuperB1Selector | SuperB1战法 | 盘整后B1买点 |
| PeakKDJSelector | 填坑战法 | 双峰之间买入 |
| BBIShortLongSelector | 补票战法 | 短长期RSV+KDJ |
| MA60CrossVolumeWaveSelector | TePu战法 | MA60金叉+量能 |
| B1TrendSelector | B1趋势战法 | 知行线+KDJ |
| BigBullishVolumeSelector | 暴力K战法 | 长阳+放量 |

## 命令行参数

```
usage: select_stock.py [-h] [--data-dir DATA_DIR] [--config CONFIG]
                       [--date DATE] [--tickers TICKERS]

选项:
  -h, --help            显示帮助信息
  --data-dir DATA_DIR   CSV数据目录 (默认: ./data)
  --config CONFIG       配置文件路径 (默认: ./configs.json)
  --date DATE           选股日期 YYYY-MM-DD (默认: 今天)
  --tickers TICKERS     股票代码，逗号分隔 (默认: all)
```

## 使用示例

### 基本用法

```bash
# 使用默认配置选股
python select_stock.py --data-dir ./data --config ./configs.json --date 2026-01-27

# 指定股票池
python select_stock.py --data-dir ./data --config ./configs.json --tickers "600000,600001,600002"

# 使用今日日期
python select_stock.py --data-dir ./data --config ./configs.json --date today
```

### 配置策略激活

在 `configs.json` 中设置 `"activate": true` 来激活策略：

```json
{
  "selectors": [
    {
      "class": "BBIKDJSelector",
      "alias": "少妇战法",
      "activate": true,    <!-- 激活此策略 -->
      "params": {...}
    },
    {
      "class": "PeakKDJSelector",
      "alias": "填坑战法",
      "activate": false,   <!-- 不激活 -->
      "params": {...}
    }
  ]
}
```

## 数据格式要求

CSV文件格式（每只股票一个文件）：

```csv
date,open,close,high,low,volume
2025-01-01,10.5,10.8,10.3,10.6,1000000
2025-01-02,10.6,10.9,10.5,10.7,1100000
...
```

文件命名规则：`{股票代码}.csv`，如 `600000.csv`

## 输出格式

### 控制台输出

```
========================================
选股执行开始
========================================
数据目录: ./data
配置文件: ./configs.json
选股日期: 2026-01-27
股票池: 全部

========================================
少妇战法 (BBIKDJSelector)
========================================
参数: j_threshold=-5, bbi_min_window=90, ...
检测股票数: 5000
符合条件: 15

结果: 600000, 600001, 600003, ...

========================================
SuperB1战法 (SuperB1Selector)
========================================
参数: lookback_n=60, close_vol_pct=0.05, ...
检测股票数: 5000
符合条件: 8

结果: 600005, 600010, 600015, ...

========================================
选股执行完成
========================================
总检测: 5000
总结果: 23
========================================
```

### 日志文件

选股结果同时保存在 `select_results.log` 文件中。

## 执行流程

```
1. 加载配置文件
   ↓
2. 加载股票数据
   - 扫描data目录下所有CSV文件
   - 读取并解析CSV数据
   - 按日期排序
   ↓
3. 遍历激活的策略
   - 初始化策略实例
   - 执行策略.select()方法
   - 收集选股结果
   ↓
4. 输出结果
   - 控制台打印
   - 写入日志文件
```

## 注意事项

1. **数据完整性**: 确保所有CSV文件格式正确，包含必需的列
2. **日期格式**: 日期参数支持 `YYYY-MM-DD` 格式或 `today`
3. **股票代码**: 股票代码不需要前缀（如不需要加sz/sh）
4. **策略参数**: 修改配置文件后需重启程序
5. **并发限制**: 当前为单线程顺序执行，大量股票时可能较慢
6. **内存使用**: 全部数据加载到内存，注意内存容量

## 常见问题

### Q: 为什么没有选股结果？

A: 可能原因：
1. 数据不足（某些策略需要120天以上数据）
2. 市场条件不满足策略要求
3. 参数设置过于严格
4. 日期格式错误或数据未更新

### Q: 如何调整策略参数？

A: 编辑 `configs.json` 文件中对应策略的 `params` 字段。

### Q: 如何添加新策略？

A:
1. 在 `Selector.py` 中实现新策略类
2. 在 `configs.json` 中添加配置项
3. 重启程序

### Q: 支持实时选股吗？

A: 不支持。需要先使用 `fetch_kline.py` 更新数据。
