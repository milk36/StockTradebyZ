# Selector.py - 策略实现模块

## 概述

实现多种技术指标计算和选股策略的核心模块。采用面向对象设计，每个策略类独立实现，支持灵活的参数配置。

## 架构设计

```
Selector.py
├── 通用指标计算函数
│   ├── compute_kdj()              - KDJ指标
│   ├── compute_bbi()              - BBI指标
│   ├── compute_rsv()              - RSV指标
│   ├── compute_dif()              - MACD的DIF
│   ├── compute_zx_lines()         - 知行线(趋势白线/大哥黄线)
│   ├── bbi_deriv_uptrend()        - BBI上升趋势判定
│   ├── last_valid_ma_cross_up()   - 有效上穿MA判定
│   ├── passes_day_constraints_today() - 当日约束
│   └── zx_condition_at_positions() - 知行条件判定
│
└── 选股策略类
    ├── BBIKDJSelector             - BBI+KDJ选股
    ├── SuperB1Selector            - SuperB1选股
    ├── PeakKDJSelector            - 峰值+KDJ选股
    ├── BBIShortLongSelector       - BBI+短长期RSV选股
    ├── MA60CrossVolumeWaveSelector - MA60金叉+量能选股
    ├── B1TrendSelector            - B1趋势选股
    └── BigBullishVolumeSelector   - 暴力K选股
```

## 通用指标函数

### compute_kdj()

计算KDJ指标，返回包含K、D、J三个值的DataFrame。

```python
def compute_kdj(df: pd.DataFrame, n: int = 9) -> pd.DataFrame
```

**参数：**
- `df`: K线数据，需包含high、low、close列
- `n`: RSV计算周期，默认9

**返回：**
- 添加K、D、J三列的DataFrame

### compute_bbi()

计算BBI（多空指标）。

```python
def compute_bbi(df: pd.DataFrame) -> pd.Series
```

**公式：**
```
BBI = (MA3 + MA6 + MA12 + MA24) / 4
```

### compute_rsv()

计算RSV（未成熟随机值）。

```python
def compute_rsv(df: pd.DataFrame, n: int) -> pd.Series
```

**公式：**
```
RSV(N) = 100 * (C - LLV(L,N)) / (HHV(C,N) - LLV(L,N))
```

**注意：** 使用close的最高值而非high的最高值。

### compute_dif()

计算MACD中的DIF（快线-慢线）。

```python
def compute_dif(df: pd.DataFrame, fast: int = 12, slow: int = 26) -> pd.Series
```

**公式：**
```
DIF = EMA(fast) - EMA(slow)
```

### compute_zx_lines()

计算知行线（趋势白线和大哥黄线）。

```python
def compute_zx_lines(df: pd.DataFrame, m1=14, m2=28, m3=57, m4=114) -> tuple
```

**返回：**
- `zxdq`: 趋势白线 = EMA(EMA(C,10),10)
- `zxdkx`: 大哥黄线 = (MA14 + MA28 + MA57 + MA114) / 4

### bbi_deriv_uptrend()

判断BBI是否整体上升。

```python
def bbi_deriv_uptrend(bbi: pd.Series, min_window: int, max_window: int = None,
                      q_threshold: float = 0.0) -> bool
```

**参数：**
- `bbi`: BBI序列
- `min_window`: 最小检测窗口
- `max_window`: 最大检测窗口，None表示不设上限
- `q_threshold`: 允许一阶差分为负的比例（0-1），0表示全程单调不降

**算法：**
1. 从最长窗口向下搜索
2. 归一化：BBI_norm(t) = BBI(t) / BBI(T-w+1)
3. 计算一阶差分
4. 检查差分的q_threshold分位数是否>=0

### last_valid_ma_cross_up()

查找最近一次"有效上穿MA"的位置。

```python
def last_valid_ma_cross_up(close: pd.Series, ma: pd.Series,
                           lookback_n: int = None) -> Optional[int]
```

**有效上穿定义：**
```
close[T-1] < ma[T-1] AND close[T] >= ma[T]
```

**返回：** 整数位置（iloc用），None表示未找到

### passes_day_constraints_today()

当日统一过滤条件。

```python
def passes_day_constraints_today(df: pd.DataFrame,
                                 pct_limit: float = 0.02,
                                 amp_limit: float = 0.07) -> bool
```

**条件：**
1. 相对于前一日涨跌幅 < pct_limit（绝对值）
2. 当日振幅 < amp_limit

### zx_condition_at_positions()

在指定位置检查知行条件。

```python
def zx_condition_at_positions(df: pd.DataFrame,
                              require_close_gt_long: bool = True,
                              require_short_gt_long: bool = True,
                              pos: int = None) -> bool
```

**条件：**
- 收盘 > 长期线（可选）
- 短期线 > 长期线（可选）

## 选股策略类

### BBIKDJSelector

自适应BBI(导数) + KDJ选股器。

**初始化参数：**
```python
BBIKDJSelector(
    j_threshold: float = -5,        # J值阈值
    bbi_min_window: int = 90,       # BBI最小窗口
    max_window: int = 90,           # 最大窗口
    price_range_pct: float = 100.0, # 价格波动范围
    bbi_q_threshold: float = 0.05,  # BBI回撤比例
    j_q_threshold: float = 0.10     # J值分位阈值
)
```

**选股条件：**
1. BBI上升（允许部分回撤）
2. J < j_threshold 或 J <= 历史J的j_q_threshold分位
3. DIF > 0
4. 收盘价波动 <= price_range_pct
5. 当日：收盘>长期线 且 短期线>长期线

### SuperB1Selector

SuperB1选股器 - 寻找盘整后的B1买点。

**初始化参数：**
```python
SuperB1Selector(
    lookback_n: int = 60,           # 回看窗口
    close_vol_pct: float = 0.05,    # 盘整波动率上限
    price_drop_pct: float = 0.03,   # 当日跌幅要求
    j_threshold: float = -5,        # J值阈值
    j_q_threshold: float = 0.10,    # J值分位阈值
    B1_params: Dict = None          # 嵌套BBIKDJSelector参数
)
```

**选股逻辑：**
1. 在lookback_n个交易日内，至少存在一日满足BBIKDJSelector
2. [t_m, date-1]区间收盘价波动率 <= close_vol_pct
3. 当日相对前一日跌幅 >= price_drop_pct
4. J值极低

### PeakKDJSelector

峰值+KDJ选股器 - 寻找双峰之间的买入机会。

**初始化参数：**
```python
PeakKDJSelector(
    j_threshold: float = -5,        # J值阈值
    max_window: int = 90,           # 最大窗口
    fluc_threshold: float = 0.03,   # 波动率上限
    gap_threshold: float = 0.02,    # 间隔阈值
    j_q_threshold: float = 0.10     # J值分位阈值
)
```

**选股逻辑：**
1. 识别OC_MAX的峰值
2. 寻找peak_t > peak_(t-n)的峰对
3. 当日收盘价波动率 <= fluc_threshold
4. J值极低
5. 当日：收盘>长期线 且 短期线>长期线

### BBIShortLongSelector

BBI上升 + 短/长期RSV条件选股器。

**初始化参数：**
```python
BBIShortLongSelector(
    n_short: int = 3,               # 短期RSV周期
    n_long: int = 21,               # 长期RSV周期
    m: int = 3,                     # 检测天数
    bbi_min_window: int = 90,       # BBI最小窗口
    max_window: int = 150,          # 最大窗口
    bbi_q_threshold: float = 0.05,  # BBI回撤比例
    upper_rsv_threshold: float = 75,# RSV上限
    lower_rsv_threshold: float = 25 # RSV下限
)
```

**选股条件：**
1. BBI上升
2. 最近m天长期RSV全部 >= upper_rsv_threshold
3. 最近m天内：先有RSV_short >= upper，后有RSV_short < lower
4. 最后一天RSV_short >= upper
5. DIF > 0

### MA60CrossVolumeWaveSelector

MA60金叉+量能选股器。

**初始化参数：**
```python
MA60CrossVolumeWaveSelector(
    lookback_n: int = 60,           # 回看窗口
    vol_multiple: float = 1.5,      # 放量倍数
    j_threshold: float = -5.0,      # J值阈值
    j_q_threshold: float = 0.10,    # J值分位阈值
    ma60_slope_days: int = 5,       # MA60斜率计算天数
    max_window: int = 120           # 最大窗口
)
```

**选股逻辑：**
1. J值极低
2. 最近lookback_n内存在有效上穿MA60
3. [T, Tmax]上涨波段日均成交量 >= 上穿前等长窗口 * vol_multiple
4. MA60斜率 > 0

### B1TrendSelector

B1趋势选股策略 - 基于知行线的简单策略。

**初始化参数：**
```python
B1TrendSelector(
    j_threshold: float = 13,        # J值阈值
    max_window: int = 120           # 最大窗口
)
```

**选股条件：**
1. KDJ.J < 13
2. 趋势白线(短期) > 大哥黄线(多空线)

### BigBullishVolumeSelector

暴力K选股器 - 长阳+放量+上影线控制。

**初始化参数：**
```python
BigBullishVolumeSelector(
    up_pct_threshold: float = 0.04,      # 长阳阈值
    upper_wick_pct_max: float = 0.5,     # 上影线比例上限
    vol_lookback_n: int = 20,            # 放量比较天数
    vol_multiple: float = 1.5,           # 放量倍数
    min_history: int = None,             # 最少历史长度
    require_bullish_close: bool = True,  # 要求收阳
    ignore_zero_volume: bool = True,     # 忽略零成交量
    close_lt_zxdq_mult: float = 1.0      # 收盘<趋势白线倍数
)
```

**选股条件：**
1. 涨幅 > up_pct_threshold
2. 上影线比例 < upper_wick_pct_max
3. 成交量 > 前n日均量 * vol_multiple
4. 收盘 < 趋势白线 * close_lt_zxdq_mult

## 策略接口

所有策略类都实现了统一的 `select()` 方法：

```python
def select(self, date: pd.Timestamp, data: Dict[str, pd.DataFrame]) -> List[str]
```

**参数：**
- `date`: 选股日期
- `data`: 股票数据字典，key为股票代码，value为K线数据

**返回：** 符合条件的股票代码列表

## 使用示例

```python
from Selector import BBIKDJSelector
import pandas as pd

# 创建选股器
selector = BBIKDJSelector(
    j_threshold=-5,
    bbi_min_window=90,
    bbi_q_threshold=0.05
)

# 准备数据
data = {
    "600000": pd.read_csv("data/600000.csv"),
    "600001": pd.read_csv("data/600001.csv"),
    # ...
}

# 执行选股
date = pd.Timestamp("2026-01-27")
results = selector.select(date, data)

print(f"符合条件: {results}")
```

## 注意事项

1. **数据格式**: 所有DataFrame必须包含date, open, high, low, close, volume列
2. **日期格式**: date列需转换为pd.Timestamp类型
3. **数据量**: 某些策略需要足够的历史数据（如需要114日均线）
4. **参数调优**: 各策略参数可根据市场情况调整
5. **异常处理**: 数据缺失或不足时，策略会自动跳过该股票
