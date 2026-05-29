# Project Documentation Index

## Feature

- [通达信本地数据源 (TDX Fetch)](feature/tdx-local-data-source.md): 通过 mootdx 读取通达信本地行情数据的模块设计、数据流（CSV 落盘 + 内存直读两条路径）、配置说明及与 Tushare 数据源的切换机制。包含 fetch_batch/load_tdx_to_dict 内存直读 API 说明。当需要理解双数据源架构、维护 tdx_fetch 模块或对接回测直读模式时查阅。
- [回测系统 (Backtest)](feature/backtest-system.md): 基于每日选股结果的历史回测工具，含多进程并行评分、量化评分器四维加权模型、模拟交易逻辑及 CLI 参数说明。当需要维护 backtest.py 或 quant_scorer.py 时查阅。

## Other

- [zgnb_zk_selector_optimized.md](zgnb_zk_selector_optimized.md): Z哥B1战法优化版选股脚本的完整参考文档，包含优化策略、核心函数签名、技术指标计算和命令行用法。
