"""通达信本地数据读取模块

通过 mootdx 读取通达信本地行情文件，输出与 Tushare 格式一致的 CSV：
  date, open, close, high, low, volume

用法：
    python -m pipeline.tdx_fetch
    python -m pipeline.tdx_fetch --config config/fetch_kline.yaml
"""
from __future__ import annotations

import datetime as dt
import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

import pandas as pd
import yaml
from mootdx.reader import Reader
from tqdm import tqdm

# 复用 fetch_kline 中的工具函数
sys.path.insert(0, str(Path(__file__).parent))
from fetch_kline import (
    load_codes_from_stocklist,
    setup_logging,
    _resolve_cfg_path,
    _CONFIG_PATH,
)

logger = logging.getLogger("tdx_fetch")

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


class TdxKlineFetcher:
    """封装 mootdx Reader，读取本地通达信行情数据并输出 CSV。"""

    def __init__(self, tdxdir: str, market: str = "std"):
        self._reader = Reader.factory(market=market, tdxdir=tdxdir)

    def fetch_one(self, code: str, start: Optional[str] = None, end: Optional[str] = None) -> pd.DataFrame:
        """读取单只股票日线数据。

        Args:
            code: 6位股票代码
            start: 起始日期 YYYYMMDD（None=不限制）
            end: 结束日期 YYYYMMDD（None=不限制）

        Returns:
            DataFrame [date, open, close, high, low, volume]，空数据时返回空 DataFrame。
        """
        try:
            df = self._reader.daily(symbol=code)
        except Exception as e:
            logger.warning("读取 %s 失败: %s", code, e)
            return pd.DataFrame()

        if df is None or df.empty:
            return pd.DataFrame()

        df = self._normalize(df, start, end)
        return df

    @staticmethod
    def _normalize(df: pd.DataFrame, start: Optional[str], end: Optional[str]) -> pd.DataFrame:
        """标准化列名和日期格式，与 Tushare 输出格式对齐。"""
        # 确保日期为列
        if isinstance(df.index, pd.DatetimeIndex):
            df = df.reset_index()
            df.rename(columns={"index": "date"}, inplace=True)

        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])

        # 列名映射: mootdx 用 vol，统一为 volume
        if "vol" in df.columns and "volume" not in df.columns:
            df.rename(columns={"vol": "volume"}, inplace=True)

        # 只保留需要的列
        keep = [c for c in ["date", "open", "close", "high", "low", "volume"] if c in df.columns]
        df = df[keep].copy()

        # 日期过滤
        if "date" in df.columns:
            if start:
                start_ts = pd.to_datetime(start)
                df = df[df["date"] >= start_ts]
            if end:
                end_ts = pd.to_datetime(end)
                df = df[df["date"] <= end_ts]

        df = df.sort_values("date").reset_index(drop=True)
        return df


def fetch_one_to_csv(
    fetcher: TdxKlineFetcher,
    code: str,
    start: Optional[str],
    end: Optional[str],
    out_dir: Path,
) -> bool:
    """读取单只股票并保存为 CSV。"""
    csv_path = out_dir / f"{code}.csv"
    try:
        df = fetcher.fetch_one(code, start, end)
        if df.empty:
            logger.debug("%s 无数据", code)
            return False
        df.to_csv(csv_path, index=False)
        return True
    except Exception as e:
        logger.warning("%s 处理失败: %s", code, e)
        return False


def main(config_path: Optional[Path] = None, log_path: Optional[Path] = None) -> None:
    """主入口：从配置文件读取参数，批量读取通达信本地数据并输出 CSV。"""
    if config_path is None:
        config_path = _CONFIG_PATH

    if not config_path.exists():
        raise FileNotFoundError(f"找不到配置文件：{config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    # 日志
    if log_path is None:
        log_dir = _PROJECT_ROOT / "data" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / f"tdx_fetch_{dt.date.today().strftime('%Y-%m-%d')}.log"
    setup_logging(log_path)

    # TDX 配置
    tdx_cfg = cfg.get("tdx", {})
    tdxdir = tdx_cfg.get("tdxdir", r"D:\Tools\tdx_64")
    market = tdx_cfg.get("market", "std")

    logger.info("通达信路径: %s, 市场: %s", tdxdir, market)

    # 日期范围
    raw_start = str(cfg.get("start", "20190101"))
    raw_end = str(cfg.get("end", "today"))
    start = dt.date.today().strftime("%Y%m%d") if raw_start.lower() == "today" else raw_start
    end = dt.date.today().strftime("%Y%m%d") if raw_end.lower() == "today" else raw_end

    # 输出目录
    out_dir = _resolve_cfg_path(cfg.get("out", "./data/raw"))
    out_dir.mkdir(parents=True, exist_ok=True)

    # 股票池
    stocklist_path = _resolve_cfg_path(cfg.get("stocklist", "./pipeline/stocklist.csv"))
    exclude_boards = set(cfg.get("exclude_boards") or [])
    codes = load_codes_from_stocklist(stocklist_path, exclude_boards)

    if not codes:
        logger.error("stocklist 为空或被过滤后无代码，请检查。")
        sys.exit(1)

    logger.info(
        "开始读取 %d 只股票 | 数据源:TDX本地(%s) | 日期:%s → %s | 排除:%s",
        len(codes), tdxdir, start, end, ",".join(sorted(exclude_boards)) or "无",
    )

    # 批量读取
    fetcher = TdxKlineFetcher(tdxdir=tdxdir, market=market)
    workers = min(int(cfg.get("workers", 8)), 4)  # 本地文件读取不需要太多线程

    ok_count = 0
    fail_count = 0

    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {
            executor.submit(fetch_one_to_csv, fetcher, code, start, end, out_dir): code
            for code in codes
        }
        for fut in tqdm(as_completed(future_map), total=len(future_map), desc="读取进度"):
            if fut.result():
                ok_count += 1
            else:
                fail_count += 1

    logger.info("完成：成功 %d 只，失败 %d 只，输出目录 %s", ok_count, fail_count, out_dir)


if __name__ == "__main__":
    main()
