"""
backtest.py
基于每日选股结果的历史回测。

优化：数据只预处理一次，在内存中复用。支持多进程并行评分（--workers）。

用法：
    python backtest.py --start 2025-01-01 --end 2025-12-31
    python backtest.py --start 2025-06-01 --end 2025-12-31 --score 4.0 --target 0.10 --hold 10
"""
from __future__ import annotations

import argparse
import logging
import os
import pickle
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from tqdm import tqdm

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "pipeline"))
sys.path.insert(0, str(ROOT / "agent"))

logging.basicConfig(level=logging.WARNING, format="%(message)s")
logger = logging.getLogger("backtest")


# ── 数据结构 ────────────────────────────────────────────────────────────────

@dataclass
class Trade:
    code: str
    select_date: str
    buy_date: str
    sell_date: str
    buy_price: float
    sell_price: float
    return_pct: float
    hold_days: int
    status: str
    total_score: float = 0.0
    signal_type: str = ""


# ── 数据加载 ────────────────────────────────────────────────────────────────

def load_all_data(data_dir: str) -> Dict[str, pd.DataFrame]:
    data: Dict[str, pd.DataFrame] = {}
    if not os.path.isdir(data_dir):
        raise FileNotFoundError(f"data_dir 不存在: {data_dir}")
    for fname in os.listdir(data_dir):
        if not fname.lower().endswith(".csv"):
            continue
        code = fname.rsplit(".", 1)[0]
        df = pd.read_csv(os.path.join(data_dir, fname))
        df.columns = [c.lower() for c in df.columns]
        if "date" not in df.columns:
            continue
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)
        if not df.empty:
            data[code] = df
    return data


def get_trading_dates(data: Dict[str, pd.DataFrame], start: str, end: str) -> List[pd.Timestamp]:
    all_dates: set = set()
    for df in data.values():
        all_dates.update(df["date"].tolist())
    start_ts = pd.to_datetime(start)
    end_ts = pd.to_datetime(end)
    return sorted(d for d in all_dates if start_ts <= d <= end_ts)


def build_date_index(df: pd.DataFrame) -> dict:
    return {str(d.date()): i for i, d in enumerate(df["date"])}


# ── 一次性预处理 + 逐日选股 ────────────────────────────────────────────────

def prepare_data_once(
    data: Dict[str, pd.DataFrame],
    end_date: str,
    selector=None,
) -> Dict[str, pd.DataFrame]:
    """对所有股票做一次预处理（turnover_n + set_index + B1指标），返回可复用的 prepared 数据。"""
    from pipeline_core import MarketDataPreparer

    preparer = MarketDataPreparer(
        end_date=pd.to_datetime(end_date),
        warmup_bars=500,
        n_turnover_days=43,
        selector=selector,
    )
    return preparer.prepare(data)


def preselect_on_date(
    pick_date: pd.Timestamp,
    prepared: Dict[str, pd.DataFrame],
    pool_dict: dict,
    selector,
) -> List[str]:
    """在已预处理数据上做单日选股（纯内存操作，无多进程开销）。"""
    pool_codes = pool_dict.get(pick_date, [])
    if not pool_codes:
        return []

    codes = []
    for code in pool_codes:
        df = prepared.get(code)
        if df is None or pick_date not in df.index:
            continue
        try:
            if selector.vec_picks_from_prepared(df, start=pick_date, end=pick_date):
                codes.append(code)
        except Exception:
            pass

    return codes


# ── 交易模拟 ────────────────────────────────────────────────────────────────

def simulate_trade(
    code: str,
    select_date: pd.Timestamp,
    data: Dict[str, pd.DataFrame],
    date_indices: Dict[str, dict],
    target_pct: float,
    max_hold: int,
    total_score: float = 0.0,
    signal_type: str = "",
) -> Optional[Trade]:
    df = data.get(code)
    if df is None or len(df) < 2:
        return None

    idx_map = date_indices.get(code)
    if idx_map is None:
        idx_map = build_date_index(df)
        date_indices[code] = idx_map

    sel_str = str(select_date.date())
    sel_idx = idx_map.get(sel_str)
    if sel_idx is None:
        return None

    buy_idx = sel_idx + 1
    if buy_idx >= len(df):
        return None

    buy_date = df.iloc[buy_idx]["date"]
    buy_price = float(df.iloc[buy_idx]["open"])
    if buy_price <= 0:
        return None

    target_price = buy_price * (1 + target_pct)

    for offset in range(max_hold):
        check_idx = buy_idx + offset
        if check_idx >= len(df):
            break
        row = df.iloc[check_idx]
        if float(row["high"]) >= target_price:
            return Trade(
                code=code, select_date=sel_str,
                buy_date=str(buy_date.date()),
                sell_date=str(row["date"].date()),
                buy_price=buy_price, sell_price=target_price,
                return_pct=target_pct * 100,
                hold_days=offset + 1, status="profit",
                total_score=total_score, signal_type=signal_type,
            )

    last_idx = min(buy_idx + max_hold - 1, len(df) - 1)
    last_row = df.iloc[last_idx]
    sell_price = float(last_row["close"])
    ret = (sell_price - buy_price) / buy_price * 100
    return Trade(
        code=code, select_date=sel_str,
        buy_date=str(buy_date.date()),
        sell_date=str(last_row["date"].date()),
        buy_price=buy_price, sell_price=sell_price,
        return_pct=ret, hold_days=last_idx - buy_idx + 1,
        status="profit" if ret > 0 else "loss",
        total_score=total_score, signal_type=signal_type,
    )


# ── 并行评分 ────────────────────────────────────────────────────────────────

def _score_stock_worker(code: str, df_bytes: bytes) -> tuple:
    """子进程 worker：反序列化 DataFrame 并调用 score_stock。"""
    df = pickle.loads(df_bytes)
    from quant_scorer import score_stock
    return code, score_stock(code, df)


def _score_codes_parallel(
    pool: ProcessPoolExecutor,
    codes: List[str],
    enriched: Dict[str, pd.DataFrame],
    date: pd.Timestamp,
) -> List[tuple]:
    """并行评分多只股票，返回 [(code, result_dict), ...]。"""
    futures = []
    for code in codes:
        df = enriched.get(code)
        if df is None:
            continue
        df_slice = df.loc[:date]
        futures.append(pool.submit(_score_stock_worker, code, pickle.dumps(df_slice)))
    results = []
    for f in as_completed(futures):
        try:
            results.append(f.result())
        except Exception:
            pass
    return results


# ── 汇总输出 ────────────────────────────────────────────────────────────────

def print_summary(all_trades: List[Trade], dates_run: int) -> None:
    if not all_trades:
        print("\n无交易记录。")
        return

    profits = [t for t in all_trades if t.status == "profit"]
    losses = [t for t in all_trades if t.status == "loss"]
    total = len(all_trades)

    win_rate = len(profits) / total * 100
    avg_ret = np.mean([t.return_pct for t in all_trades])
    avg_hold = np.mean([t.hold_days for t in all_trades])
    avg_profit = np.mean([t.return_pct for t in profits]) if profits else 0
    avg_loss = np.mean([t.return_pct for t in losses]) if losses else 0
    profit_loss_ratio = abs(avg_profit / avg_loss) if avg_loss != 0 else float("inf")
    target_hits = sum(1 for t in all_trades if t.return_pct >= 10.0)
    hit_rate = target_hits / total * 100

    print("\n" + "=" * 60)
    print("  回测汇总报告")
    print("=" * 60)
    print(f"  回测区间     ：{all_trades[0].select_date} ~ {all_trades[-1].select_date}")
    print(f"  回测交易日   ：{dates_run} 天")
    print(f"  总交易笔数   ：{total}")
    print(f"  盈利 / 亏损  ：{len(profits)} / {len(losses)}")
    print(f"  胜率         ：{win_rate:.1f}%")
    print(f"  平均收益     ：{avg_ret:.2f}%")
    print(f"  盈利平均收益 ：{avg_profit:.2f}%")
    print(f"  亏损平均收益 ：{avg_loss:.2f}%")
    print(f"  盈亏比       ：{profit_loss_ratio:.2f}")
    print(f"  平均持仓天数 ：{avg_hold:.1f}")
    print(f"  止盈命中率   ：{hit_rate:.1f}%（达到+10%的比例）")
    print("=" * 60)


def _trade_to_row(t: Trade) -> dict:
    return {
        "code": t.code, "select_date": t.select_date,
        "buy_date": t.buy_date, "sell_date": t.sell_date,
        "buy_price": f"{t.buy_price:.2f}", "sell_price": f"{t.sell_price:.2f}",
        "return_pct": f"{t.return_pct:.2f}", "hold_days": t.hold_days,
        "status": t.status, "score": t.total_score,
    }


def save_detail_csv(all_trades: List[Trade], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = [_trade_to_row(t) for t in all_trades]
    pd.DataFrame(rows).to_csv(out_dir / "backtest_detail_all.csv", index=False)


def save_summary_log(all_trades: List[Trade], dates_run: int, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / "backtest_summary_all.log"

    by_date: Dict[str, List[Trade]] = defaultdict(list)
    for t in all_trades:
        by_date[t.select_date].append(t)

    with open(log_path, "w", encoding="utf-8") as f:
        f.write("=" * 60 + "\n")
        f.write("汇总报告 - 所有日期回测结果\n")
        f.write("=" * 60 + "\n")
        f.write(f"{'日期':<12} {'总数':>6} {'盈利':>6} {'亏损':>6} {'平均收益':>10} {'胜率':>8}\n")
        f.write("-" * 60 + "\n")

        total_all, profit_all, loss_all = 0, 0, 0
        ret_sum = 0.0

        for date_str in sorted(by_date.keys()):
            trades = by_date[date_str]
            n = len(trades)
            p = sum(1 for t in trades if t.status == "profit")
            l = n - p
            avg = np.mean([t.return_pct for t in trades])
            wr = p / n * 100 if n > 0 else 0
            f.write(f"{date_str:<12} {n:>6} {p:>6} {l:>6} {avg:>9.2f}% {wr:>7.1f}%\n")
            total_all += n
            profit_all += p
            loss_all += l
            ret_sum += sum(t.return_pct for t in trades)

        f.write("-" * 60 + "\n")
        avg_all = ret_sum / total_all if total_all > 0 else 0
        wr_all = profit_all / total_all * 100 if total_all > 0 else 0
        f.write(f"{'总计':<12} {total_all:>6} {profit_all:>6} {loss_all:>6} {avg_all:>9.2f}% {wr_all:>7.1f}%\n")
        f.write("=" * 60 + "\n")

        # 每笔交易明细
        f.write("\n")
        f.write("=" * 100 + "\n")
        f.write("交易明细\n")
        f.write("=" * 100 + "\n")
        header = (
            f"{'选股日':<12} {'代码':<8} {'买入日':<12} {'卖出日':<12} "
            f"{'买入价':>8} {'卖出价':>8} {'收益':>8} {'持仓':>4} "
            f"{'结果':<4} {'评分':>5}\n"
        )
        f.write(header)
        f.write("-" * 100 + "\n")

        for date_str in sorted(by_date.keys()):
            for t in sorted(by_date[date_str], key=lambda x: -x.return_pct):
                f.write(
                    f"{t.select_date:<12} {t.code:<8} {t.buy_date:<12} {t.sell_date:<12} "
                    f"{t.buy_price:>8.2f} {t.sell_price:>8.2f} "
                    f"{t.return_pct:>+7.2f}% {t.hold_days:>4} "
                    f"{'盈' if t.status == 'profit' else '亏':<4} {t.total_score:>5.1f}\n"
                )

    print(f"\n明细和汇总已保存至 {out_dir}/")


# ── 主入口 ──────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="基于选股结果的回测")
    parser.add_argument("--start", default="2025-01-01", help="回测起始日期")
    parser.add_argument("--end", default="2025-12-31", help="回测结束日期")
    parser.add_argument("--score", type=float, default=4.0, help="评分门槛（默认 4.0）")
    parser.add_argument("--target", type=float, default=0.10, help="止盈比例（默认 0.10）")
    parser.add_argument("--hold", type=int, default=10, help="最大持仓天数（默认 10）")
    parser.add_argument("--source", choices=["tdx", "csv"], default="tdx",
                        help="数据源：tdx（默认）或 csv（已有数据）")
    parser.add_argument("--data", default="./data/raw", help="CSV 数据目录")
    parser.add_argument("--workers", type=int, default=os.cpu_count() or 4,
                        help=f"并行进程数（默认 {os.cpu_count() or 4}，设 1 关闭并行）")
    args = parser.parse_args()

    # 加载原始数据
    if args.source == "tdx":
        print("[INFO] 数据源: 通达信本地（直接读取，跳过 CSV）")
        from tdx_fetch import load_tdx_to_dict
        data = load_tdx_to_dict()
    else:
        print(f"[INFO] 数据源: CSV（{args.data}）")
        data = load_all_data(args.data)
    print(f"[INFO] 加载 {len(data)} 只股票")

    # 预计算评分指标 + 设置日期索引（用于按日切片）
    print("[INFO] 预计算评分指标...")
    from quant_scorer import precompute_score_columns
    enriched: Dict[str, pd.DataFrame] = {}
    for code, df in data.items():
        df = precompute_score_columns(df)
        df = df.set_index("date").sort_index()
        enriched[code] = df
    print(f"[INFO] 预计算完成，{len(enriched)} 只股票")

    trading_dates = get_trading_dates(data, args.start, args.end)
    print(f"[INFO] 回测区间: {args.start} ~ {args.end}，共 {len(trading_dates)} 个交易日")
    print(f"[INFO] 参数: 评分≥{args.score}, 止盈+{args.target*100:.0f}%, 最大持仓{args.hold}天")

    # 加载选股配置 + 创建 B1 selector（循环外一次性创建）
    from select_stock import load_config, _sorted_zx
    from Selector import B1Selector
    cfg = load_config()
    g = cfg.get("global", {})
    top_m = int(g.get("top_m", 20))
    cfg_b1 = cfg.get("b1", {})
    zx_m1, zx_m2, zx_m3, zx_m4 = _sorted_zx(
        cfg_b1["zx_m1"], cfg_b1["zx_m2"], cfg_b1["zx_m3"], cfg_b1["zx_m4"]
    )
    b1_selector = B1Selector(
        j_threshold=float(cfg_b1["j_threshold"]),
        j_q_threshold=float(cfg_b1["j_q_threshold"]),
        zx_m1=zx_m1, zx_m2=zx_m2, zx_m3=zx_m3, zx_m4=zx_m4,
    ) if cfg_b1.get("enabled", True) else None

    # 一次性预处理（含 B1 指标预计算 + 流动性池构建）
    print("[INFO] 预处理数据（含 B1 指标预计算）...")
    prepared = prepare_data_once(data, args.end, selector=b1_selector)
    print(f"[INFO] 预处理完成，{len(prepared)} 只股票")

    from pipeline_core import TopTurnoverPoolBuilder
    pool_dict = TopTurnoverPoolBuilder(top_m=top_m).build(prepared)
    print(f"[INFO] 流动性池已构建")

    date_indices: Dict[str, dict] = {}
    all_trades: List[Trade] = []
    use_parallel = args.workers > 1

    pool = ProcessPoolExecutor(max_workers=args.workers) if use_parallel else None
    if use_parallel:
        print(f"[INFO] 并行模式: {args.workers} 进程评分")

    try:
        for date in tqdm(trading_dates, desc="回测进度", ncols=80):
            codes = preselect_on_date(date, prepared, pool_dict, b1_selector)
            if not codes:
                continue

            # 评分阶段（并行 or 串行），按日期切片避免未来数据泄漏
            if use_parallel:
                scored = _score_codes_parallel(pool, codes, enriched, date)
            else:
                from quant_scorer import score_stock
                scored = [
                    (c, score_stock(c, enriched[c].loc[:date]))
                    for c in codes if c in enriched
                ]

            # 模拟交易（串行，很快）
            day_trades: List[Trade] = []
            for code, result in scored:
                ts = result.get("total_score", 0)
                if ts < args.score:
                    continue
                trade = simulate_trade(
                    code, date, data, date_indices,
                    args.target, args.hold,
                    total_score=ts,
                    signal_type=result.get("signal_type", ""),
                )
                if trade:
                    day_trades.append(trade)

            if day_trades:
                all_trades.extend(day_trades)
    finally:
        if pool is not None:
            pool.shutdown(wait=True)

    # 汇总
    print_summary(all_trades, len(trading_dates))
    if all_trades:
        out_dir = ROOT / "backtest_results"
        save_detail_csv(all_trades, out_dir)
        save_summary_log(all_trades, len(trading_dates), out_dir)


if __name__ == "__main__":
    main()
