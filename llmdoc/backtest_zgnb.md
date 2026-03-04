# backtest_zgnb.py - Z哥B1战法回测脚本

## 概述

基于 `zgnb_zk_results.log` 选股结果日志文件进行T+1买入、T+2卖出的回测验证工具，完全独立运行，不依赖任何选股策略实现。

## 回测逻辑

### 交易时间线

```
T    (选股日期): 从 zgnb_zk_results.log 读取选股结果
T+1  (买入日期): 下一个交易日开盘价买入
T+2  (卖出日期): 再下一个交易日收盘价卖出
```

### 收益率计算

```
收益率 = (卖出价 - 买入价) / 买入价 × 100%
```

## 架构设计

```
backtest_zgnb.py
├── 数据类
│   └── BacktestResult - 单次回测结果数据结构
│
├── 日志解析函数
│   └── parse_log_file() - 解析 zgnb_zk_results.log
│
├── BacktestEngine类 (核心引擎)
│   ├── __init__(data_dir, log_file) - 初始化
│   ├── parse_log_file() - 解析日志文件
│   ├── run_backtest() - 执行批量回测
│   ├── backtest_single_stock() - 单股回测逻辑
│   ├── generate_summary_stats() - 生成统计摘要
│   ├── save_results_to_csv() - 导出CSV结果
│   └── print_console_report() - 打印控制台报告
│
└── main() - 命令行入口
```

## 日志文件解析

### zgnb_zk_results.log 格式

```
========================================
Z哥B1战法选股结果
========================================
交易日: 2026-01-20
数据目录: ./data
检测股票数: 4894
符合条件: 40

符合条件的股票:
000069, 000538, 000776, 000786, ...
========================================
```

### 解析逻辑

1. **选股日期提取**: 查找 `交易日:` 开头的行，解析日期
2. **股票代码提取**: 查找 `符合条件的股票:` 后的逗号分隔列表
3. **容错处理**: 文件不存在或格式错误时抛出异常

## 核心类设计

### BacktestResult 数据类

```python
@dataclass
class BacktestResult:
    """单次回测结果"""
    code: str                    # 股票代码
    select_date: pd.Timestamp    # 选股日期
    buy_date: Optional[pd.Timestamp]    # 买入日期
    sell_date: Optional[pd.Timestamp]   # 卖出日期
    buy_price: Optional[float]   # 买入价
    sell_price: Optional[float]  # 卖出价
    return_pct: Optional[float]  # 收益率(%)
    status: str                  # 状态: success/no_data/no_t1/no_t2
```

### 状态码说明

| 状态 | 说明 |
|------|------|
| `success` | 回测成功，已计算收益率 |
| `no_data` | 股票数据文件不存在或格式错误 |
| `no_t1` | 选股日期后没有下一个交易日数据 |
| `no_t2` | 选股日期后没有第二个交易日数据 |

### BacktestEngine 方法

| 方法 | 说明 |
|------|------|
| `run_backtest()` | 执行所有股票的回测 |
| `backtest_single_stock(code, select_date)` | 单股回测核心逻辑 |
| `generate_summary_stats()` | 生成统计摘要 |
| `save_results_to_csv(output_dir)` | 保存结果到CSV |
| `save_results_to_log(output_dir)` | 保存结果到日志文件 |
| `print_console_report()` | 打印控制台报告 |

## 使用示例

### 基本用法

```bash
# 使用默认配置（data目录，zgnb_zk_results.log）
python backtest_zgnb.py --data-dir ./data

# 指定日志文件
python backtest_zgnb.py --data-dir ./data --log-file zgnb_zk_results.log

# 指定输出目录
python backtest_zgnb.py --data-dir ./data --output-dir ./my_results
```

### 命令行参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--data-dir` | `./data` | K线数据目录 |
| `--log-file` | `zgnb_zk_results.log` | 选股结果日志文件 |
| `--output-dir` | `./backtest_results` | 输出目录 |

### 完整工作流

```bash
# 1. 运行选股脚本生成日志文件
python zgnb_zk_selector.py --data-dir ./data --date 2026-01-27

# 2. 检查日志文件生成
cat zgnb_zk_results.log

# 3. 运行回测脚本
python backtest_zgnb.py --data-dir ./data

# 4. 查看回测结果
ls -la backtest_results/
```

## 输出格式

### 输出文件

回测脚本会在输出目录（默认 `backtest_results/`）生成两个文件：

| 文件 | 说明 |
|------|------|
| `backtest_results.log` | 回测报告日志文件 |
| `backtest_detail_YYYYMMDD.csv` | 回测明细CSV文件 |

### 控制台输出

```
========================================
回测报告 - Z哥B1战法
========================================
选股日期: 2026-01-20 (来自 zgnb_zk_results.log)
数据目录: data

总交易次数: 40
  - 成功执行: 40
  - 无数据: 0
  - 无T+1: 0
  - 无T+2: 0

平均收益率: 1.66%
收益率中位数: 0.70%
最大收益: 18.62%
最大亏损: -6.86%
胜率: 60.00%
盈利股票: 24 只
亏损股票: 16 只

个股明细 (按收益率排序):
代码         买入日期         卖出日期         买入价      卖出价      收益率
----------------------------------------------------------------------
601212     2026-01-21   2026-01-22   7.95     9.43     +18.62%
603608     2026-01-21   2026-01-22   10.38    12.05    +16.09%
300179     2026-01-21   2026-01-22   16.20    18.31    +13.02%
...
603916     2026-01-21   2026-01-22   12.54    11.68    -6.86%
========================================
```

### 日志文件输出 (backtest_results.log)

格式与控制台输出相同，便于历史记录查看：

```
========================================
回测报告 - Z哥B1战法
========================================
选股日期: 2026-01-20 (来自 zgnb_zk_results.log)
数据目录: data

总交易次数: 40
  - 成功执行: 40
  - 无数据: 0
  - 无T+1: 0
  - 无T+2: 0

平均收益率: 1.66%
收益率中位数: 0.70%
最大收益: 18.62%
最大亏损: -6.86%
胜率: 60.00%

个股明细:
代码         买入日期         卖出日期         买入价      卖出价      收益率
----------------------------------------------------------------------
000069     2026-01-21   2026-01-22   2.70     2.70     +0.00%
...
========================================
```

### CSV输出文件

文件名格式: `backtest_detail_YYYYMMDD.csv`

```csv
code,select_date,buy_date,sell_date,buy_price,sell_price,return_pct,status
000069,2026-01-20,2026-01-21,2026-01-22,2.7,2.7,0.0,success
000538,2026-01-20,2026-01-21,2026-01-22,57.1,56.65,-0.788091068301231,success
...
```

## 边界情况处理

| 场景 | 处理方式 |
|------|----------|
| 日志文件不存在 | 抛出 `FileNotFoundError`，退出码1 |
| 无法解析选股日期 | 抛出 `ValueError`，退出码1 |
| CSV文件不存在 | 返回 `status='no_data'` |
| 选股日期不在数据中 | 返回 `status='no_data'` |
| 数据最后一天（无T+1） | 返回 `status='no_t1'` |
| 倒数第二天（无T+2） | 返回 `status='no_t2'` |
| 读取CSV失败 | 返回 `status='no_data'`，记录警告日志 |

## 注意事项

1. **不考虑交易成本**: 收益率计算不包含手续费、印花税、滑点等
2. **T+1/T+2逻辑**: 严格按顺序交易日，不考虑隔夜跳空影响
3. **数据边界**: 选股日期需要有至少2个后续交易日数据才能回测
4. **每支股票单独统计**: 不分组合交易，单独计算每支股票收益
5. **日志文件依赖**: 依赖 `zgnb_zk_results.log` 存在且格式正确
6. **日期格式**: 支持YYYY-MM-DD格式的日期解析

## 日志记录

执行日志保存在 `backtest_zgnb.log`，记录内容包括：
- 选股日期和股票数量
- 回测执行进度
- 错误和警告信息
- 结果文件保存路径

## 统计指标说明

| 指标 | 计算方式 |
|------|----------|
| 平均收益率 | 所有成功交易收益率的算术平均值 |
| 收益率中位数 | 所有成功交易收益率的中位数 |
| 最大收益 | 所有成功交易中的最高收益率 |
| 最大亏损 | 所有成功交易中的最低收益率 |
| 胜率 | 收益率>0的交易数 / 总成功交易数 × 100% |
| 盈利股票 | 收益率>0的股票数量 |
| 亏损股票 | 收益率≤0的股票数量 |
