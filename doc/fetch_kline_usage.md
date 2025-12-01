# fetch_kline.py 脚本使用说明

## 📋 概述

`fetch_kline.py` 是一个简洁高效的股票历史数据获取脚本，通过Tushare API获取A股日线数据（前复权）。脚本支持市值筛选和ST股票剔除功能，专注于核心数据获取功能。

## 🚀 核心特性

### 📊 数据获取
- **前复权数据**: 获取日线K线数据，自动进行前复权处理
- **数据验证**: 自动检查数据完整性和有效性
- **CSV格式输出**: 标准化数据格式，便于后续分析

### 🎯 股票筛选
- **市值筛选**: 支持按市值范围筛选股票
- **ST股票剔除**: 自动剔除ST股票，提高数据质量
- **板块过滤**: 可排除创业板、科创板、北交所等特定板块

### ⚡ 并发处理
- **多线程下载**: 支持并发下载，提高获取效率
- **简单可靠**: 保持简单的设计，减少复杂性和潜在问题

## 🛠️ 环境准备

### 1. 安装依赖
```bash
pip install -r requirements.txt
```

### 2. 设置Tushare Token
```bash
# Windows (PowerShell)
setx TUSHARE_TOKEN "你的token"

# macOS / Linux (bash)
export TUSHARE_TOKEN=你的token
```

### 3. 准备股票池
确保 `stocklist.csv` 文件存在，格式如下：
```csv
ts_code,symbol,name,area,industry
000001.SZ,000001,平安银行,深圳,银行
000002.SZ,000002,万科A,深圳,全国地产
...
```

## 📖 使用方法

### 基础用法

#### 1. 默认使用
```bash
# 常用模式
python fetch_kline.py --start 20250101 --end today --workers 6 --min-market-cap 50 --max-market-cap 2000

# 使用默认设置获取数据
python fetch_kline.py --start 20240101 --end today

# 排除特定板块
python fetch_kline.py --start 20240101 --end today --exclude-boards gem star bj
```

#### 2. 市值筛选
```bash
# 只选择市值100-2000亿的股票
python fetch_kline.py --min-market-cap 100 --max-market-cap 2000

# 只选择市值500亿以上的股票
python fetch_kline.py --min-market-cap 500
```

#### 3. ST股票处理
```bash
# 默认剔除ST股票
python fetch_kline.py --start 20240101 --end today

# 包含ST股票
python fetch_kline.py --start 20240101 --end today --include-st
```

#### 4. 自定义设置
```bash
# 自定义输出目录和并发数
python fetch_kline.py --start 20240101 --end today --out ./my_data --workers 8
```

## 📋 参数详解

### 基础参数
| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--start` | `20190101` | 起始日期 (YYYYMMDD 或 'today') |
| `--end` | `today` | 结束日期 (YYYYMMDD 或 'today') |
| `--stocklist` | `./stocklist.csv` | 股票清单CSV路径 |
| `--out` | `./data` | 输出目录 |

### 板块过滤
| 参数 | 选项 | 说明 |
|------|------|------|
| `--exclude-boards` | `gem`, `star`, `bj` | 排除板块（可多选） |

### 市值筛选
| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--min-market-cap` | `None` | 最小市值筛选（亿元） |
| `--max-market-cap` | `None` | 最大市值筛选（亿元） |

### ST股票处理
| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--exclude-st` | `True` | 剔除ST股票（默认启用） |
| `--include-st` | `False` | 包含ST股票 |

### 性能参数
| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--workers` | `6` | 并发线程数 |

## 📊 输出文件

### 数据文件
- **位置**: `./data/` 目录
- **格式**: `{股票代码}.csv`
- **内容**: date, open, close, high, low, volume

### 日志文件
- **文件**: `./fetch.log`
- **内容**: 详细的运行日志和错误信息

## 🎯 使用场景

### 1. 基础数据获取
```bash
# 获取指定日期范围的数据
python fetch_kline.py --start 20240101 --end today
```

### 2. 特定板块分析
```bash
# 只分析主板股票
python fetch_kline.py --exclude-boards gem star bj --start 20240101 --end today
```

### 3. 大盘股筛选
```bash
# 只选择市值500亿以上的股票
python fetch_kline.py --min-market-cap 500 --start 20240101 --end today
```

### 4. 中小盘股分析
```bash
# 选择市值50-500亿的股票
python fetch_kline.py --min-market-cap 50 --max-market-cap 500 --start 20240101 --end today
```

### 5. 包含ST股票分析
```bash
# 包含ST股票进行特殊分析
python fetch_kline.py --include-st --start 20240101 --end today
```

## ⚡ 性能优化建议

### 1. 并发控制
- **小规模** (< 100只股票): `--workers 4`
- **中等规模** (100-500只): `--workers 6` (默认)
- **大规模** (> 500只): `--workers 8-10`

### 2. 市值筛选
- 尽早使用市值筛选减少处理股票数量
- 结合板块过滤进一步提高效率

### 3. 数据管理
- 定期清理旧数据释放存储空间
- 根据分析需求选择合适的时间范围

## 🔧 故障排除

### 1. API限制问题
- **现象**: 日志显示API调用失败或数据获取错误
- **解决**: 检查Tushare Token是否正确设置
- **预防**: 确保API配额充足

### 2. 数据缺失
- **现象**: 某些股票数据为空
- **原因**: 股票停牌、退市或日期范围内无交易
- **解决**: 检查股票代码和日期范围

### 3. 内存不足
- **现象**: 大量股票时内存溢出
- **解决**: 减少 `--workers` 参数值

### 4. 网络问题
- **现象**: 连接超时或网络错误
- **解决**: 检查网络连接，必要时重新运行

## 📈 性能统计

脚本运行完成后会显示详细统计：
```
==================================================
抓取完成统计:
总股票数: 1000
成功更新: 950
失败数量: 50
总耗时: 300.0秒
平均速度: 3.33只/秒
==================================================
```

## 💡 最佳实践

1. **市值筛选**: 尽早使用市值筛选减少处理量
2. **板块过滤**: 根据分析需求排除不需要的板块
3. **并发控制**: 根据系统性能调整并发数
4. **监控日志**: 定期检查 `fetch.log` 文件
5. **备份数据**: 定期备份 `./data` 目录

---

*本脚本专注于核心数据获取功能，提供简洁高效的股票数据下载体验。如有问题，请检查日志文件或确认环境配置。*