# 回测系统 (Backtest)

## 1. Purpose

基于每日 B1 选股结果的历史回测工具。对指定区间内的每个交易日执行：数据预处理 -> 流动性池构建 -> B1 选股 -> 量化评分 -> 模拟交易。支持多进程并行评分以加速回测。

## 2. How it Works

### 整体流程

```
加载 CSV 数据 (load_all_data)
    |
    v
一次性预处理 (prepare_data_once) -- MarketDataPreparer, 最耗时的步骤, 只做一次
    |
    v
逐日循环:
    preselect_on_date -- TopTurnoverPool + B1Selector 纯内存操作
        |
        v
    评分阶段 (并行/串行) -- quant_scorer.score_stock 四维加权评分
        |
        v
    模拟交易 (simulate_trade) -- 串行, T+1 买入, 目标价止盈/最大持仓天数卖出
        |
        v
    明细 CSV 落盘
    |
    v
汇总报告 (print_summary + save_summary_log)
```

### 并行评分机制

- `--workers N` 参数控制并行进程数，默认 `os.cpu_count()`，设 `1` 关闭并行
- 并行模式下使用 `ProcessPoolExecutor`，通过 `pickle` 序列化 DataFrame 传递给子进程
- 子进程 worker (`_score_stock_worker`) 反序列化后调用 `quant_scorer.score_stock`
- `_score_codes_parallel` 提交所有候选股票的评分 future，用 `as_completed` 收集结果
- 模拟交易阶段始终串行（执行很快，无需并行）

### 评分模块

`quant_scorer.score_stock(code, df)` 返回与 Gemini 视觉分析同格式的 dict，四维加权评分：

| 维度 | 权重 | 评分函数 | 核心逻辑 |
|------|------|----------|----------|
| 趋势结构 | 20% | `score_trend` | MA 多头排列 + 均线斜率 |
| 价格位置 | 20% | `score_position` | 价格相对 60/120 日高点位置 |
| 量价行为 | 30% | `score_volume` | 上涨放量/回调缩量比 |
| 前期异动 | 30% | `score_abnormal` | 最大量能异动 + 区间涨幅 |

输出含 `total_score`、`signal_type`（trend_start / rebound / distribution_risk）、`verdict`（PASS / WATCH / FAIL）。

### CLI 参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--start` | 2025-01-01 | 回测起始日期 |
| `--end` | 2025-12-31 | 回测结束日期 |
| `--score` | 4.0 | 评分门槛，低于此分数的股票不参与交易 |
| `--target` | 0.10 | 止盈比例（0.10 = +10%） |
| `--hold` | 10 | 最大持仓天数，到期未止盈则收盘价卖出 |
| `--source` | tdx | 数据源 (tdx / csv) |
| `--data` | ./data/raw | CSV 数据目录 |
| `--workers` | cpu_count | 并行进程数，设 1 关闭并行 |

### 用法示例

```bash
# 基本用法：全量回测（使用默认参数 + 自动检测 CPU 核心数并行）
python backtest.py --start 2025-01-01 --end 2025-12-31

# 缩短回测区间（快速验证）
python backtest.py --start 2025-06-01 --end 2025-09-30

# 调整策略参数：放宽评分门槛、提高止盈目标、延长持仓
python backtest.py --start 2025-01-01 --end 2025-12-31 --score 3.5 --target 0.15 --hold 15

# 指定并行进程数（4 进程）
python backtest.py --start 2025-01-01 --end 2025-12-31 --workers 4

# 关闭并行（调试时用）
python backtest.py --start 2025-01-01 --end 2025-12-31 --workers 1

# 使用已有 CSV 数据（跳过 TDX 检查）
python backtest.py --source csv --data ./data/raw

# 组合使用：指定数据源 + 自定义参数 + 4 进程
python backtest.py --source tdx --start 2025-03-01 --end 2025-12-31 \
    --score 3.0 --target 0.08 --hold 7 --workers 4
```

### 参数组合建议

| 场景 | 推荐参数 |
|------|----------|
| 日常回测 | 默认值即可 |
| 快速验证 | `--start` 缩短区间 + `--workers` 设为 CPU 核心数 |
| 保守策略 | `--score 4.5` `--target 0.08` `--hold 7` |
| 激进策略 | `--score 3.0` `--target 0.15` `--hold 15` |
| 调试排查 | `--workers 1`（串行，便于定位问题） |

## 3. Relevant Code Modules

- `backtest.py` -- 回测主入口，含数据加载、选股、评分调度、交易模拟、报告输出
- `agent/quant_scorer.py` -- 纯代码量价评分器，四维加权评分
- `pipeline/pipeline_core.py` -- `MarketDataPreparer` 和 `TopTurnoverPoolBuilder`
- `select_stock.py` -- B1 选股配置加载 (`load_config`) 及辅助函数 (`_sorted_zx`)
- `Selector.py` -- `B1Selector` 选股策略实现
- `backtest_results/` -- 回测明细 CSV 和汇总日志的输出目录

## 4. Attention

- 数据预处理 (`prepare_data_once`) 只执行一次，后续逐日选股在内存中复用 prepared 数据
- TDX 数据源要求 `data/raw/` 下至少有 100 个 CSV 文件，否则报错并提示先运行 `run_all.py --source tdx --stop-at 1`
- 并行评分通过 pickle 传递 DataFrame，子进程独立执行 `score_stock`，无需共享状态
- `ProcessPoolExecutor` 在 `try/finally` 中管理生命周期，确保回测结束后正确 shutdown
- 评分阈值 (`--score`) 和止盈比例 (`--target`) 是影响回测结果的核心参数
