# analyze_backtest_features.py - 特征分析脚本

## 功能概述

`analyze_backtest_features.py` 是Z哥B1战法盈利股票特征分析工具，用于分析回测结果中盈利股票的共同特征，帮助理解哪些因素影响交易胜率和收益率。

## 主要功能

### 1. 板块分布分析
- 统计主板、创业板、科创板、北交所的交易次数和胜率
- 计算各板块的平均收益率
- 识别最佳表现的板块

### 2. 技术指标分布对比
- 对比盈利组与亏损组的技术指标差异
- 分析指标与收益率的相关性
- 涵盖指标：J值、RSI、SHORT、LONG、砖型图、黄柱

### 3. B1条件类型分析
- 统计各B1买入条件的触发次数
- 计算每个条件的胜率和平均收益
- 识别高胜率的B1条件

### 4. K线形态分析
- 阳线 vs 阴线的胜率对比
- 十字星的胜率分析
- 缩量与放量的胜率差异

### 5. 高收益股票特征分析
- 分析收益率≥10%的股票特征
- 统计高收益股的板块分布和B1类型分布
- 提供大赢股的技术指标区间

## 核心类和数据结构

### StockFeatures 数据类

```python
@dataclass
class StockFeatures:
    code: str           # 股票代码
    select_date: pd.Timestamp  # 选股日期
    return_pct: float   # 收益率（%）
    is_profit: bool     # 是否盈利

    # 板块信息
    board_type: str     # main/gem/star/bj

    # 技术指标（选股当日T的值）
    j: float            # KDJ的J值
    rsi: float          # RSI指标
    short: float        # SHORT指标
    long: float         # LONG指标
    brick_type: float   # 砖型图
    trend_white: float  # 趋势白线
    yellow_line: float  # 大哥黄线
    bbi: float          # BBI指标

    # 动能指标
    j_momentum: float        # J - REF(J,1)
    rsi_momentum: float      # RSI - REF(RSI,1)
    yellow_pillar: float     # 黄柱 (SHORT - LONG)
    x_momentum: float        # X动能 (砖型图)

    # K线形态
    is_red: bool            # 是否阳线
    is_doji: bool           # 是否十字星
    body_pct: float         # 实体占比
    upper_shadow_pct: float # 上影线占比
    day_amp: float          # 当日振幅
    day_change: float       # 涨跌幅

    # 成交量特征
    vol_ratio_20: float     # 成交量/20日最高量
    vol_ratio_50: float     # 成交量/50日最高量
    is_shrink: bool         # 是否缩量

    # 振幅特征
    recent_amp: float       # 近期振幅（20日）
    far_amp: float          # 远期振幅（50日）

    # B1条件类型
    b1_type: str            # 触发的B1条件类型
```

### FeatureAnalyzer 类

```python
class FeatureAnalyzer:
    def __init__(self, data_dir: Path, backtest_dir: Path, workers: int = None)

    # 加载回测结果
    def load_backtest_results(self) -> List[dict]

    # 并行提取所有股票特征
    def extract_all_features_parallel(self, transactions: List[dict]) -> List[StockFeatures]

    # 板块分布分析
    def analyze_board_distribution(self) -> Dict

    # 技术指标分布对比
    def analyze_indicator_distribution(self) -> Dict

    # B1条件类型分析
    def analyze_b1_type_distribution(self) -> Dict

    # K线形态分析
    def analyze_pattern_distribution(self) -> Dict

    # 高收益股票特征分析
    def analyze_high_profit_stocks(self, threshold: float = 10) -> Dict

    # 生成分析报告
    def generate_report(self) -> str
```

## 复用的技术指标函数

脚本复用了 `zgnb_zk_selector.py` 中的技术指标计算函数：

- `compute_brick_type()` - 砖型图
- `compute_rsi()` - RSI指标
- `compute_short_long()` - SHORT/LONG指标
- `compute_trend_white_line()` - 趋势白线
- `compute_big_brother_yellow_line()` - 大哥黄线
- `compute_kdj_custom()` - KDJ指标
- `compute_bbi()` - BBI指标

## B1条件判断函数

脚本实现了6种B1买入条件的判断函数：

1. `check_chaomai_suoliang_guantou()` - 超卖缩量拐头B
2. `check_chaomai_suoliang()` - 超卖缩量B
3. `check_yuanshi_b1()` - 原始B1
4. `check_chaomai_chaosuoliang()` - 超卖超缩量B
5. `check_huicai_baixian()` - 回踩白线B
6. `check_huicai_chaoji()` - 回踩超级B

`identify_b1_type()` 函数按优先级顺序检查每个B1条件，返回第一个触发的条件类型。

## 使用方式

### 基本用法

```bash
# 使用默认参数运行（4进程并行）
python analyze_backtest_features.py --data-dir ./data --backtest-dir ./backtest_results
```

### 高级用法

```bash
# 使用10进程并行加速
python analyze_backtest_features.py --data-dir ./data --backtest-dir ./backtest_results --workers 10

# 指定输出文件
python analyze_backtest_features.py --data-dir ./data --backtest-dir ./backtest_results --output my_report.txt
```

## 命令行参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--data-dir` | `./data` | K线数据目录 |
| `--backtest-dir` | `./backtest_results` | 回测结果目录 |
| `--output` | `feature_analysis_report.txt` | 输出报告文件路径 |
| `--workers` | `4` | 并行进程数 |

## 输出报告格式

```
============================================================
Z哥B1战法盈利股票特征分析报告
============================================================

一、整体统计
------------------------------------------------------------
总交易次数: 2244
盈利次数: 1010
亏损次数: 1234
整体胜率: 45.0%
平均收益: 0.03%

二、板块分布分析
------------------------------------------------------------
板块       交易次数     盈利次数     亏损次数     胜率       平均收益
------------------------------------------------------------
主板       1350     632      718      46.8%   +0.08%
创业板      615      247      368      40.2%   -0.46%
科创板      279      131      148      47.0%   +0.85%

三、技术指标分布对比
------------------------------------------------------------
指标           盈利组均值        亏损组均值        差异         相关性
------------------------------------------------------------
J值           70.10        51.95        18.15      +0.318
RSI          75.13        57.69        17.44      +0.466
SHORT        92.15        67.21        24.94      +0.440
...
```

## 性能说明

| 处理方式 | 股票数量 | 预计耗时 |
|---------|---------|---------|
| 单线程 | 2244 | ~15-20分钟 |
| 4进程 | 2244 | ~4-5分钟 |
| 10进程 | 2244 | ~2分钟 |

## 数据流程

```
回测日志文件
    ↓
解析交易数据（代码、日期、收益率）
    ↓
多进程并行读取K线数据
    ↓
计算技术指标（J、RSI、SHORT/LONG等）
    ↓
判断B1条件类型
    ↓
提取K线形态特征（阳线/阴线、十字星等）
    ↓
统计分析生成报告
```

## 关键发现示例

基于2244笔交易数据的分析发现：

1. **板块表现**：科创板胜率最高（47.0%），平均收益+0.85%
2. **K线形态**：阳线胜率（67.3%）远高于阴线胜率（24.9%）
3. **技术指标**：RSI与收益率正相关系数+0.466
4. **B1条件**：超卖缩量拐头B虽然触发次数少（9次），但胜率高达77.8%

## 注意事项

1. **数据依赖**：需要先运行回测脚本生成 `backtest_summary_all.log` 文件
2. **内存占用**：处理大量交易时，建议使用适度的进程数（4-10个）
3. **B1条件判断**：由于选股时的参数可能与当前判断函数不完全一致，部分股票可能显示为"未知"类型
4. **指标计算一致性**：复用 `zgnb_zk_selector.py` 的函数确保指标计算一致

## 日志文件

- `analyze_backtest_features.log` - 脚本执行日志
- `feature_analysis_report.txt` - 分析报告输出

## 扩展方向

1. 支持自定义收益分组分析（如微利0-3%、中利3-10%、大利>10%）
2. 添加时间维度分析（不同月份/季度的表现差异）
3. 支持导出CSV格式数据供进一步分析
4. 添加可视化图表生成功能
