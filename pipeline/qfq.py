"""前复权数据调整模块

通过 akshare 获取前复权收盘价，计算复权比例并应用到 mootdx 原始数据上。
支持本地 parquet 缓存 + 内存缓存，避免重复网络请求。
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_QFQ_CACHE_DIR = _PROJECT_ROOT / "cache" / "qfq"

# 内存缓存：code -> pd.Series(qfq_close, index=DatetimeIndex)
_memory_cache: dict[str, pd.Series] = {}

# 指数代码前缀（不需要复权）
_INDEX_PREFIXES = ("399", "899")


def is_index(code: str) -> bool:
    return code == "000001" or code[:3] in _INDEX_PREFIXES


def _cache_path(code: str) -> str:
    return str(_QFQ_CACHE_DIR / f"{code}.parquet")


def _load_disk_cache(code: str) -> pd.Series | None:
    path = _cache_path(code)
    if not os.path.isfile(path):
        return None
    try:
        df = pd.read_parquet(path)
        dates = pd.to_datetime(df["date"])
        return pd.Series(df["qfq_close"].values, index=dates, name=code)
    except Exception:
        return None


def _save_disk_cache(code: str, qfq_close: pd.Series) -> None:
    _QFQ_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame({"date": qfq_close.index, "qfq_close": qfq_close.values})
    df.to_parquet(_cache_path(code), index=False)


def _fetch_qfq_from_akshare(code: str) -> pd.Series | None:
    import akshare as ak

    try:
        qfq_df = ak.stock_zh_a_hist(
            symbol=code, period="daily",
            start_date="19900101", end_date="20991231",
            adjust="qfq",
        )
        if qfq_df is None or qfq_df.empty:
            return None
        dates = pd.to_datetime(qfq_df.iloc[:, 0])
        closes = qfq_df.iloc[:, 3].astype(float)
        return pd.Series(closes.values, index=dates, name=code)
    except Exception as e:
        print(f"  [QFQ] 获取 {code} 失败: {e}")
        return None


def get_qfq_close(code: str) -> pd.Series | None:
    """获取前复权收盘价（带缓存）。"""
    if is_index(code):
        return None

    if code in _memory_cache:
        return _memory_cache[code]

    cached = _load_disk_cache(code)
    if cached is not None:
        _memory_cache[code] = cached
        return cached

    qfq_close = _fetch_qfq_from_akshare(code)
    if qfq_close is not None:
        _save_disk_cache(code, qfq_close)
        _memory_cache[code] = qfq_close
    return qfq_close


def apply_qfq(df: pd.DataFrame, code: str) -> pd.DataFrame:
    """对 DataFrame 应用前复权。ratio = qfq_close / raw_close，乘以 OHLC 列。volume 不调整。"""
    if df is None or df.empty:
        return df

    qfq_close = get_qfq_close(code)
    if qfq_close is None:
        return df

    # 统一日期索引
    if "date" in df.columns:
        df_dates = pd.to_datetime(df["date"])
    elif isinstance(df.index, pd.DatetimeIndex):
        df_dates = df.index
    else:
        df_dates = pd.to_datetime(df.index)

    common = pd.Index(df_dates).intersection(pd.Index(qfq_close.index))
    if len(common) == 0:
        return df

    # 重建 df 的日期索引用于 reindex
    df_indexed = df.set_index(df_dates)

    raw_close_common = df_indexed["close"].reindex(common).astype(float)
    ratio_common = qfq_close.reindex(common) / raw_close_common

    ratio_full = pd.Series(1.0, index=df_dates)
    ratio_full.loc[common] = ratio_common.values
    ratio_arr = ratio_full.values.astype(float)

    if np.allclose(ratio_arr, 1.0):
        return df

    for col in ("open", "high", "low", "close"):
        if col in df.columns:
            df[col] = df[col].astype(float) * ratio_arr

    return df
