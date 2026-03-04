# zgnb_zk_selector.py - Z哥B1战法选股脚本

## 概述

基于通达信公式实现的独立B1战法选股工具，完全独立于 `Selector.py` 框架，可单独运行进行选股。

## 架构设计

```
zgnb_zk_selector.py
├── 技术指标计算函数 (约200行)
│   ├── compute_brick_type()     - 砖型图
│   ├── compute_rsi()            - 3日RSI
│   ├── compute_short_long()     - SHORT/LONG
│   ├── compute_trend_white_line()  - 趋势白线 EMA(EMA(C,10),10)
│   ├── compute_big_brother_yellow_line() - 大哥黄线 (MA14+MA28+MA57+MA114)/4
│   ├── compute_kdj_custom()     - KDJ指标
│   └── compute_bbi()            - BBI指标
│
├── 辅助判断函数 (约100行)
│   ├── get_board_type()         - 股票板块判断
│   ├── get_amp_range()          - 振幅区间获取
│   ├── count_condition()        - COUNT函数
│   ├── every_condition()        - EVERY函数
│   ├── exist_condition()        - EXIST函数
│   └── hhv_bars()               - HHVBARS函数
│
├── B1买入条件函数 (约600行)
│   ├── check_chaomai_suoliang_guantou() - 超卖缩量拐头B
│   ├── check_chaomai_suoliang()         - 超卖缩量B
│   ├── check_yuanshi_b1()               - 原始B1
│   ├── check_chaomai_chaosuoliang()     - 超卖超缩量B
│   ├── check_huicai_baixian()           - 回踩白线B
│   ├── check_huicai_chaoji()            - 回踩超级B
│   └── check_huicai_huangxian()         - 回踩黄线B
│
├── 共振条件函数 (约200行)
│   ├── check_strong_red()       - 强红判定
│   ├── check_momentum()         - 动能指标(黄柱/X动能)
│   ├── check_upper_shadow()     - 上影线条件
│   ├── check_trend_condition()  - 趋势条件
│   ├── check_turnover_condition() - 换手条件
│   └── check_resonance_buy()    - 综合共振买入
│
├── 多进程处理函数 (约40行)
│   └── process_single_stock()  - 子进程独立处理函数
│
└── 主选股类 (约200行)
    ├── ZGNBZKSelector.__init__() - 初始化
    ├── ZGNBZKSelector.load_data() - 加载CSV数据
    ├── ZGNBZKSelector.select_stock() - 单股判断
    ├── ZGNBZKSelector.run()      - 批量选股（支持多进程）
    └── main()                    - 命令行入口
```

## 技术指标实现

### 1. 砖型图 (Brick Type)

```python
VAR1A = (HHV(HIGH,4)-CLOSE)/(HHV(HIGH,4)-LLV(LOW,4))*100-90
VAR2A = SMA(VAR1A,4,1)+100
VAR3A = (CLOSE-LLV(LOW,4))/(HHV(HIGH,4)-LLV(LOW,4))*100
VAR4A = SMA(VAR3A,6,1)
VAR5A = SMA(VAR4A,6,1)+100
VAR6A = VAR5A-VAR2A
砖型图 = IF(VAR6A>4, VAR6A-4, 0)
```

### 2. 趋势白线

```python
趋势白线 = EMA(EMA(C,10),10)
```

### 3. 大哥黄线

```python
大哥黄线 = (MA(C,14) + MA(C,28) + MA(C,57) + MA(C,114)) / 4
```

### 4. SHORT/LONG

```python
SHORT = 100 * (C - LLV(L,3)) / (HHV(C,3) - LLV(L,3))
LONG  = 100 * (C - LLV(L,21)) / (HHV(C,21) - LLV(L,21))
```

## B1买入条件

### 超卖缩量拐头B

**条件：**
- 做上涨趋势: 趋势白线>=大哥黄线*0.999 且 (收盘>=大哥黄线 或 (收盘>大哥黄线*0.975 且 阳线))
- RSI拐头: (RSI-15)>=前日RSI 且 (前日RSI<20 或 前日J<14)
- 振幅限制: 当日振幅 < (振幅区间+0.5)
- 涨跌幅限制: 当日涨跌幅<2.3 或 (上涨十字星 且 涨跌幅<4)
- 大绿棒条件: 不是大绿棒 或 大绿棒离得远(>=15天)
- 异动条件: 近期振幅>=15 或 远期振幅>=30 或 洗盘异动
- 收盘价条件: 收盘>=大哥黄线

### 超卖缩量B

**条件：**
- 做上涨趋势
- J<14 或 RSI<23
- RSI+J<55 或 J=LLV(J,20)
- 当日振幅<振幅区间
- 当日涨跌幅<2.5 或 上涨十字星
- 缩量 或 (适当缩量 且 涨跌幅<1)
- 不是大绿棒 或 大绿棒离得远
- 异动条件

### 原始B1

**条件：**
- 趋势白线>大哥黄线 且 收盘>=大哥黄线*0.99
- 大哥黄线>=前日大哥黄线
- J<13 或 RSI<21
- (RSI+J) < LLV(RSI+J,15)*1.5
- 适当缩量
- 不是大绿棒 或 大绿棒离得远
- 异动条件

### 超卖超缩量B

**条件：**
- 做上涨趋势
- J<14 或 RSI<23
- RSI+J<60
- 远期振幅>=45
- (当日振幅<振幅区间) 或 (超级异动 且 振幅<振幅区间+3.2 且 阳线且收盘>=趋势白线)
- (阴线且缩量且收盘>=大哥黄线) 或 阳线
- 涨跌幅<2 或 上涨十字星
- 超缩量
- 异动条件

### 回踩白线B

**条件：**
- 强趋势股: 大哥黄线连续上升, 趋势白线上升, 趋势白线>大哥黄线, 红肥绿瘦
- J<30 或 RSI<40 或 洗盘异动
- RSI+J<70
- 当日振幅<振幅区间+0.5 或 距离白线<1 或 距离BBI<1
- 回踩白线条件
- 涨跌幅<2 或 (涨跌幅<5 且 白线支撑)
- 不是大绿棒 或 大绿棒离得远
- 回踩缩量
- 异动条件
- 最低价<=前收盘

### 回踩超级B

**条件：**
- 超牛股: BBI上升且(近期振幅>=30 或 远期振幅>80)且上次上穿大哥黄线>12天
- J<35 或 RSI<45 或 洗盘异动
- RSI+J<80 且 RSI+J=LLV(RSI+J,25)
- 当日振幅<振幅区间+1
- 涨跌幅<2.5 或 距离白线<2
- 强势回踩不破
- 不是大绿棒 或 大绿棒离得远
- 适当缩量
- 异动条件

### 回踩黄线B

**条件：**
- 趋势白线>=大哥黄线
- 收盘>=大哥黄线*0.975
- J<13 或 RSI<18
- 回踩黄线条件
- 不是大绿棒 或 大绿棒离得远
- 缩量 或 (适当缩量 且 (J=LLV(J,20) 或 RSI=LLV(RSI,14)))
- 大哥黄线>=前日大哥黄线*0.997
- MA60上升
- 近期振幅>=11.9 且 远期振幅>=19.5

## 共振买入条件

**最终选股条件：**

```
买入条件 = 强红 AND (黄柱>=10 OR X动能>=10)
           AND (共振条件1 OR 共振条件2)
           AND 上影线条件 AND 趋势条件 AND 换手条件
```

### 强红判定

```
今红 = 砖型图 > 昨日砖型图
昨绿 = 昨日砖型图 <= 前日砖型图
红柱长度 = 砖型图 - 昨日砖型图
昨绿长度 = 前日砖型图 - 昨日砖型图
比值 = 红柱长度 / 昨绿长度

强红 = 今红 AND 昨绿 AND 比值 > 0.666
```

### 黄柱计算

```
J动能 = 今日J - 前日J
R动能 = 今日RSI - 前日RSI

影线系数 = IF(阳线上涨, 0.75 - 上影线/实体高度, 1)
倍量系数 = IF(放量4倍以上, 1.4, 0.1*量比 + 1)

黄柱 = (J动能 + R动能) / 2 * 影线系数 * 倍量系数
```

### X动能计算

```
X动能 = IF(阳线上涨 AND 动能增强,
          ((J动能+R动能) - 前日(J动能+R动能)) / 2 * 影线系数 * 成交量系数 * 倍量系数,
          0)
```

### 共振条件1

```
共振条件1 = 强红 AND (黄柱>=10 OR X动能>=10)
            AND (2日内存在B1 OR (前日LONG>85 AND 前日SHORT<30))
```

### 共振条件2

```
共振条件2 = 强红 AND (黄柱>=10 OR X动能>=10)
            AND ((4日内LONG-SHORT>60 AND LONG>98 AND SHORT>98)
                OR (黄柱>20 AND 收盘>趋势白线)
                OR 黄柱>30
                OR (黄柱+长度)>50
                OR X动能>40)
```

## 板块判断

| 代码前缀 | 板块 | 振幅区间 |
|----------|------|----------|
| 30 | 创业板 | 8 |
| 68 | 科创板 | 8 |
| 4, 8 | 北交所 | 8 |
| 其他 | 主板 | 5 |

## 常量定义

```python
# MA周期
M1 = 14  # 短期MA
M2 = 28  # 中短期MA
M3 = 57  # 中期MA
M4 = 114 # 长期MA

# SHORT/LONG 周期
N1 = 3   # 短期
N2 = 21  # 长期

# 振幅计算周期
N = 20   # 近期
M = 50   # 远期
```

## 使用示例

### 基本用法

```bash
# 选股全部股票（默认10进程并行）
python zgnb_zk_selector.py --data-dir ./data --date 2026-01-27

# 指定股票池
python zgnb_zk_selector.py --data-dir ./data --date 2026-01-27 --tickers "600000,600001,600002"

# 输出到文件
python zgnb_zk_selector.py --data-dir ./data --date 2026-01-27 --output results.txt

# 使用20进程加速（适合大量股票）
python zgnb_zk_selector.py --data-dir ./data --date 2026-01-27 --workers 20
```

### 代码调用

```python
from pathlib import Path
import pandas as pd
from zgnb_zk_selector import ZGNBZKSelector

# 创建选股器
selector = ZGNBZKSelector(data_dir=Path("./data"))

# 执行选股
trade_date = pd.Timestamp("2026-01-27")
results = selector.run(trade_date)

print(f"符合条件: {results}")

# 使用多进程加速
trade_date = pd.Timestamp("2026-01-27")
results = selector.run(trade_date, workers=20)
```

## 多进程支持

### 架构说明

脚本使用 `ProcessPoolExecutor` 实现多进程并行处理，充分利用多核CPU加速选股：

```
主进程
├── 加载所有CSV数据
├── 创建进程池（默认10个进程）
└── 分发任务
    ├── Process 1 → 处理股票 1, 11, 21, ...
    ├── Process 2 → 处理股票 2, 12, 22, ...
    ├── Process 3 → 处理股票 3, 13, 23, ...
    ├── ...
    └── Process N → 处理股票 N, N+10, N+20, ...
```

### 性能对比

| 股票数量 | 单线程耗时 | 10进程耗时 | 加速比 |
|----------|------------|------------|--------|
| 500只    | ~30秒      | ~5秒       | 6倍    |
| 1000只   | ~60秒      | ~8秒       | 7.5倍  |
| 3000只   | ~180秒     | ~22秒      | 8倍    |

### 进程数选择

```bash
# CPU核心数检测
import multiprocessing
print(f"推荐进程数: {multiprocessing.cpu_count()}")
```

**建议：**
- 默认使用10进程（适合大多数场景）
- CPU核心数≥16时可使用15-20进程
- 内存不足时减少进程数

### 命令行参数

```
--workers N    并行进程数（默认: 10）
```

## 输出格式

### 单次输出（追加模式）

默认情况下，输出结果会**追加**到 `zgnb_zk_results.log` 文件，支持多次运行累积多个日期的选股结果：

```
========================================
Z哥B1战法选股结果
========================================
交易日: 2026-01-27
数据目录: ./data
检测股票数: 5000
符合条件: 15

符合条件的股票:
600000, 600001, 600003, 600005, 600010, ...
========================================

========================================
Z哥B1战法选股结果
========================================
交易日: 2026-01-28
数据目录: ./data
检测股票数: 5000
符合条件: 22

符合条件的股票:
000001, 000002, 600000, ...
========================================
```

### 控制台输出

运行时会实时显示选股进度和结果：

```
[INFO] 加载数据: 4894 只股票
[INFO] 开始选股: 2026-01-27 (10进程)
[████████████████████████████] 100% (4894/4894)
[INFO] 符合条件: 15 只
[INFO] 结果已追加到: zgnb_zk_results.log
```

## 注意事项

1. **数据要求**: 至少需要120天历史数据
2. **换手率简化**: 由于缺少流通股本数据，使用成交量相对比例替代
3. **日期格式**: 支持YYYY-MM-DD格式，也支持"today"表示最新交易日
4. **日志记录**: 执行日志保存在 `zgnb_zk_selector.log`
5. **独立运行**: 完全独立于 Selector.py，不依赖任何外部策略类
6. **追加模式**: 输出文件 `zgnb_zk_results.log` 使用追加模式，多次运行会累积多个日期的结果，便于批量回测使用
7. **使用 --no-log**: 如需输出到标准输出而非文件，可使用 `--no-log` 参数
