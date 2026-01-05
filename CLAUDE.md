# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

这是一个基于Z哥战法的A股量化选股系统，使用Python实现。主要功能包括：
- 从多个数据源（AkShare/Tushare/Mootdx）获取A股历史K线数据
- 基于技术指标实现多种选股策略
- 支持多线程增量数据更新

## 核心架构

### 主要模块

1. **fetch_kline.py** - 数据获取模块
   - 支持三种数据源：AkShare、Tushare、Mootdx
   - 按市值筛选A股股票
   - 多线程下载历史K线数据
   - 自动增量更新机制

2. **select_stock.py** - 选股执行模块
   - 读取本地CSV数据
   - 根据配置批量执行选股策略
   - 输出结果到日志文件

3. **Selector.py** - 策略实现模块
   - 实现多种技术指标计算（KDJ、BBI、RSV等）
   - 包含5种选股策略：少妇战法、填坑战法、补票战法、TePu战法、SuperB1战法
   - 基于分位数统计和窗口分析的策略框架

### 数据流程

```
数据源 → fetch_kline.py → CSV存储 → select_stock.py → 选股结果
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
# 下载历史K线数据
python fetch_kline.py --datasource tushare --frequency 4 --min-mktcap 5e9 --max-mktcap +inf --start 20200101 --end today --out ./data --workers 10

或者:

python fetch_kline.py --start 20250101 --end today --stocklist ./stocklist.csv --exclude-boards gem star bj --out ./data --workers 6

# 下载市值在100-2000亿之间的股票数据
python fetch_kline.py --start 20250101 --end today --stocklist ./stocklist.csv --exclude-boards gem star bj --out ./data --workers 2 --rate-limit-interval 2.0 --min-market-cap 100 --max-market-cap 2000

# 使用Mootdx数据源（需先运行探测最佳IP）
python -m mootdx bestip -vv
python fetch_kline.py --datasource mootdx --frequency 4 --out ./data --workers 10
```

### 选股执行
```bash
# 执行选股策略
python select_stock.py --data-dir ./data --config ./configs.json --date 2025-07-02

# 指定股票池
python select_stock.py --data-dir ./data --config ./configs.json --tickers "600000,600001,600002"
```

## 配置管理

### 策略配置
配置文件 `configs.json` 包含所有选股策略的参数：
- 每个策略可独立启用/禁用
- 支持自定义参数调整
- 包含5种内置策略

### 数据源配置
- **Tushare**: 需要在 `fetch_kline.py` 第307行设置Token
- **AkShare**: 免费开源数据源
- **Mootdx**: 需要先运行最佳IP探测

## 数据格式

### K线数据CSV格式
```
date,open,high,low,close,volume
2025-01-01,10.5,10.8,10.3,10.6,1000000
```

### 选股配置JSON结构
```json
{
  "selectors": [
    {
      "class": "BBIKDJSelector",
      "alias": "少妇战法",
      "activate": true,
      "params": {
        "j_threshold": 10,
        "bbi_min_window": 20
      }
    }
  ]
}
```

## 开发注意事项

### 性能优化
- 数据获取使用多线程并发
- 支持增量更新，避免重复下载
- 使用pandas进行高效数据处理

### 扩展性
- 新策略需在 `Selector.py` 中实现继承基类
- 配置文件支持动态策略加载
- 可轻松添加新的数据源

### 日志系统
- 数据获取日志：`fetch.log`
- 选股结果日志：`select_results.log`
- 使用标准logging模块，支持控制台和文件输出

## 故障排除

### 常见问题
1. **Tushare Token问题**: 检查Token是否正确设置
2. **数据源连接失败**: 尝试切换不同的数据源
3. **内存不足**: 减少并发线程数或分批处理
4. **数据更新异常**: 检查日期范围和增量逻辑

### 调试技巧
- 使用 `--verbose` 参数查看详细日志
- 检查 `fetch.log` 和 `select_results.log`
- 验证CSV数据文件的完整性

### 下载历史k线数据

```bash
python fetch_kline.py --start 20250101 --end today --stocklist ./stocklist.csv --exclude-boards gem star bj --out ./data --workers 6 --min-market-cap 50 --max-market-cap 1500

// 排除北交所
python fetch_kline.py --start 20250101 --end today --stocklist ./stocklist.csv --exclude-boards bj --out ./data --workers 6 --min-market-cap 50 --max-market-cap 2500
```

### 选股指令

```bash
python select_stock.py --data-dir ./data --config ./configs.json --date 2025-10-28
```
