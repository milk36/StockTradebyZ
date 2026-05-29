# 通达信本地数据源 (TDX Fetch)

## 1. Purpose

通过 mootdx 库读取通达信客户端本地行情文件，作为 Tushare 的离线替代方案。输出格式与 Tushare 完全一致（`date, open, close, high, low, volume`），使下游流程（初选、图表导出、AI 评审）无需任何修改即可使用。支持两条路径：CSV 落盘（供 run_all 全流程）和内存直读（供回测等下游模块跳过 CSV 中转）。

## 2. How it Works

### 架构设计

项目采用双数据源策略，`fetch_kline.py`（Tushare）和 `tdx_fetch.py`（TDX）共享同一份配置文件 `config/fetch_kline.yaml` 和相同的工具函数（`load_codes_from_stocklist`、`setup_logging`、`_resolve_cfg_path`），仅数据获取层不同。

### 数据流

**路径 A: CSV 落盘（run_all 全流程）**

```
通达信本地数据文件 (.day)
    |
    v
mootdx Reader.factory(market, tdxdir).daily(code)
    |
    v
TdxKlineFetcher._normalize() -- 列名对齐、日期过滤
    |
    v
CSV 文件 ({code}.csv) -- 输出到 data/raw/
```

**路径 B: 内存直读（回测等下游模块）**

```
通达信本地数据文件 (.day)
    |
    v
mootdx Reader -> TdxKlineFetcher.fetch_batch()
    |
    v
dict[str, DataFrame]  -- 直接传递给回测等下游模块
```

### 核心组件

- **`TdxKlineFetcher`**: 封装 mootdx Reader，提供 `fetch_one(code, start, end)` 方法返回标准化 DataFrame
- **`TdxKlineFetcher.fetch_batch(codes, start, end, workers)`**: 批量读取多只股票到内存 `dict[str, DataFrame]`，内部使用 `ThreadPoolExecutor` 并行调用 `fetch_one`，跳过 CSV 中转
- **`load_tdx_to_dict(config_path)`**: 顶层便捷函数，从配置文件读取参数（股票池、日期、tdxdir 等），创建 `TdxKlineFetcher` 并调用 `fetch_batch()`，返回 `dict[str, DataFrame]`
- **`_normalize()`**: 静态方法，将 mootdx 原始列映射到 Tushare 格式（`vol` -> `volume`），执行日期范围过滤
- **`fetch_one_to_csv()`**: 单只股票读取 + CSV 落盘的工作单元，供线程池调度
- **`main()`**: 从 `fetch_kline.yaml` 读取 `tdx` 配置节，多线程批量读取并输出 CSV

### 运行方式

| 方式 | 命令 | 场景 |
|------|------|------|
| 独立运行 | `python -m pipeline.tdx_fetch` | 单独获取行情数据 |
| 全流程集成 | `python run_all.py --source tdx` | 从步骤 1 开始使用 TDX 数据 |
| 回测直读 | `python backtest.py --source tdx` | 回测直接从 TDX 读取，跳过 CSV（默认即 tdx） |

`run_all.py` 通过 `--source` 参数选择数据源（默认 `tushare`），步骤 1 根据此参数分发到 `pipeline.tdx_fetch` 或 `pipeline.fetch_kline`。`backtest.py` 的 `--source` 默认值为 `tdx`，使用 `load_tdx_to_dict()` 直接加载到内存。

## 3. Relevant Code Modules

- `pipeline/tdx_fetch.py` -- TDX 数据读取核心模块
- `pipeline/fetch_kline.py` -- Tushare 数据源（与 TDX 共享配置和工具函数）
- `config/fetch_kline.yaml` -- 数据源配置文件（含 `tdx` 配置节）
- `run_all.py` -- 全流程入口（`--source` 参数选择数据源）
- `backtest.py` -- 回测入口（`--source tdx` 直读模式，默认调用 `load_tdx_to_dict()`）
- `requirements.txt` -- 包含 `mootdx==0.11.7` 依赖

## 4. Attention

- `tdxdir` 路径必须指向通达信安装目录（包含 `vipdoc` 子目录），默认 `D:\Tools\tdx_64`
- 本地数据仅包含通达信已下载的品种和时段，未下载的股票会跳过（日志中记录 debug 级别）
- 线程数默认上限为 4（本地文件 IO 不需要过多线程），可在 YAML 中通过 `workers` 调整
- 输出 CSV 与 Tushare 格式一致，`data/raw/` 目录为两种数据源的共享输出位置
- `fetch_batch()` 和 `load_tdx_to_dict()` 提供内存直读路径，`backtest.py` 已默认使用该模式（`--source tdx`），无需 CSV 中转
