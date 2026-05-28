"""
dashboard/components/charts.py
K线 / 知行线 / 量能 — matplotlib 图表组件（白底，双周期）

参考 zgnb_Backtrader 项目的 src/charting/kline_chart.py 实现，
使用纯 matplotlib 手绘蜡烛图，不依赖 plotly/kaleido。
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.collections import PatchCollection
import numpy as np
import pandas as pd

plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_ROOT))

# ── 颜色常量 ────────────────────────────────────────────────────────────────
COLOR_YANG = "#dc3545"      # 阳线红
COLOR_YIN = "#28a745"       # 阴线绿
COLOR_ZXDQ = "#e67e22"      # 知行短期线（橙）
COLOR_ZXDKX = "#2980b9"     # 知行多空线（蓝）
GRID_ALPHA = 0.3

# ── 图表尺寸 ────────────────────────────────────────────────────────────────
DPI = 150
FIG_WIDTH = 14
FIG_HEIGHT = 7


# ─────────────────────────────────────────────────────────────────────────────
# 指标计算（保留原函数，供 dashboard app 复用）
# ─────────────────────────────────────────────────────────────────────────────

def _calc_ma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window, min_periods=1).mean()


def _calc_kdj(
    df: pd.DataFrame,
    n: int = 9,
    m1: int = 3,
    m2: int = 3,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)

    llv = low.rolling(n, min_periods=1).min()
    hhv = high.rolling(n, min_periods=1).max()
    denom = hhv - llv
    denom = denom.replace(0, 1e-6)
    rsv = (close - llv) / denom * 100.0

    alpha_k = 1.0 / m1
    alpha_d = 1.0 / m2
    k = rsv.ewm(alpha=alpha_k, adjust=False).mean()
    d = k.ewm(alpha=alpha_d, adjust=False).mean()
    j = 3 * k - 2 * d

    return k, d, j


def _calc_zx_lines(
    df: pd.DataFrame,
    zxdq_span: int = 10,
    m1: int = 14, m2: int = 28, m3: int = 57, m4: int = 114,
) -> tuple[pd.Series, pd.Series]:
    close = df["close"].astype(float)
    zxdq = close.ewm(span=zxdq_span, adjust=False).mean().ewm(span=zxdq_span, adjust=False).mean()
    zxdkx = (
        close.rolling(m1, min_periods=m1).mean()
        + close.rolling(m2, min_periods=m2).mean()
        + close.rolling(m3, min_periods=m3).mean()
        + close.rolling(m4, min_periods=m4).mean()
    ) / 4.0
    return zxdq, zxdkx


def _calc_brick(
    df: pd.DataFrame,
    n: int = 4, m1: int = 4, m2: int = 6, m3: int = 6,
    t: float = 4.0, shift1: float = 90.0, shift2: float = 100.0,
    sma_w1: int = 1, sma_w2: int = 1, sma_w3: int = 1,
) -> pd.Series:
    high = df["high"].values.astype(float)
    low = df["low"].values.astype(float)
    close = df["close"].values.astype(float)
    length = len(close)

    hhv = pd.Series(high).rolling(n, min_periods=1).max().values
    llv = pd.Series(low).rolling(n, min_periods=1).min().values

    a1 = sma_w1 / m1; b1 = 1.0 - a1
    var2a = np.empty(length, dtype=float)
    for i in range(length):
        rng = hhv[i] - llv[i]
        if rng == 0.0: rng = 0.01
        v1 = (hhv[i] - close[i]) / rng * 100.0 - shift1
        var2a[i] = (v1 + shift2) if i == 0 else (a1 * v1 + b1 * (var2a[i - 1] - shift2) + shift2)

    a2 = sma_w2 / m2; b2 = 1.0 - a2
    a3 = sma_w3 / m3; b3 = 1.0 - a3
    var4a = np.empty(length, dtype=float)
    var5a = np.empty(length, dtype=float)
    for i in range(length):
        rng = hhv[i] - llv[i]
        if rng == 0.0: rng = 0.01
        v3 = (close[i] - llv[i]) / rng * 100.0
        if i == 0:
            var4a[i] = v3; var5a[i] = v3 + shift2
        else:
            var4a[i] = a2 * v3 + b2 * var4a[i - 1]
            var5a[i] = a3 * var4a[i] + b3 * (var5a[i - 1] - shift2) + shift2

    raw = np.empty(length, dtype=float)
    for i in range(length):
        diff = var5a[i] - var2a[i]
        raw[i] = diff - t if diff > t else 0.0

    return pd.Series(raw, index=df.index)


def prepare_daily_indicators(
    df: pd.DataFrame,
    zx_params: Optional[dict] = None,
    brick_params: Optional[dict] = None,
) -> pd.DataFrame:
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)

    zxdq, zxdkx = _calc_zx_lines(df, **(zx_params or {}))
    df["_zxdq"] = zxdq.values
    df["_zxdkx"] = zxdkx.values
    df["_brick"] = _calc_brick(df, **(brick_params or {})).values

    k, d, j = _calc_kdj(df)
    df["_kdj_k"] = k.values
    df["_kdj_d"] = d.values
    df["_kdj_j"] = j.values

    return df


def _build_weekly_df(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    d["date"] = pd.to_datetime(d["date"])
    d = d.set_index("date").sort_index()
    weekly = d.resample("W-FRI").agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    ).dropna(subset=["open", "close"])
    weekly = weekly.reset_index()
    return weekly


# ─────────────────────────────────────────────────────────────────────────────
# matplotlib 绘图核心
# ─────────────────────────────────────────────────────────────────────────────

def _draw_candlestick(ax, opens, closes, highs, lows, n):
    """绘制 K 线蜡烛图"""
    x = np.arange(n)

    # 影线
    ax.vlines(x, lows, highs, colors="#888888", linewidths=0.5)

    # 实体
    rects = []
    colors = []
    for i in range(n):
        o, c = float(opens[i]), float(closes[i])
        if np.isnan(o) or np.isnan(c):
            continue
        body_bottom = min(o, c)
        body_height = abs(c - o)
        if body_height < 0.001:
            body_height = c * 0.002
        rect = mpatches.Rectangle((x[i] - 0.35, body_bottom), 0.7, body_height)
        rects.append(rect)
        colors.append(COLOR_YANG if c >= o else COLOR_YIN)

    if rects:
        collection = PatchCollection(rects, facecolors=colors,
                                      edgecolors=colors, linewidths=0.5)
        ax.add_collection(collection)

    ax.set_xlim(-1, n)
    valid_mask = ~np.isnan(highs) & ~np.isnan(lows)
    if valid_mask.any():
        y_min = np.nanmin(lows[valid_mask])
        y_max = np.nanmax(highs[valid_mask])
        margin = (y_max - y_min) * 0.08
        ax.set_ylim(y_min - margin, y_max + margin)


def _draw_volume(ax, x, volumes, opens, closes, n):
    """绘制成交量柱"""
    colors = []
    for i in range(n):
        c, o = float(closes[i]), float(opens[i])
        if np.isnan(c) or np.isnan(o):
            colors.append(COLOR_YIN)
        else:
            colors.append(COLOR_YANG if c >= o else COLOR_YIN)
    ax.bar(x, volumes, width=0.7, color=colors, alpha=0.7)
    ax.set_xlim(-1, n)


# ─────────────────────────────────────────────────────────────────────────────
# 日线图
# ─────────────────────────────────────────────────────────────────────────────

def make_daily_chart(
    df: pd.DataFrame,
    code: str,
    bars: int = 120,
    zx_params: Optional[dict] = None,
    **_kwargs,
) -> plt.Figure:
    """日线图：K线 + 知行短期线 + 知行多空线 + 成交量"""
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)

    # 全量预热知行线
    zxdq, zxdkx = _calc_zx_lines(df, **(zx_params or {}))
    df["_zxdq"] = zxdq.values
    df["_zxdkx"] = zxdkx.values

    if bars > 0:
        df = df.tail(bars).reset_index(drop=True)

    n = len(df)
    x = np.arange(n)
    opens = df["open"].values.astype(float)
    closes = df["close"].values.astype(float)
    highs = df["high"].values.astype(float)
    lows = df["low"].values.astype(float)
    volumes = df["volume"].values.astype(float)
    dates = df["date"].values

    fig, (ax_price, ax_vol) = plt.subplots(
        2, 1, figsize=(FIG_WIDTH, FIG_HEIGHT),
        gridspec_kw={"height_ratios": [3, 1]},
        sharex=True,
    )
    fig.subplots_adjust(hspace=0.05)

    # K 线
    _draw_candlestick(ax_price, opens, closes, highs, lows, n)

    # 知行线
    zxdq_vals = df["_zxdq"].values
    zxdkx_vals = df["_zxdkx"].values
    valid_zxdq = ~np.isnan(zxdq_vals)
    valid_zxdkx = ~np.isnan(zxdkx_vals)
    if valid_zxdq.any():
        ax_price.plot(x[valid_zxdq], zxdq_vals[valid_zxdq],
                      color=COLOR_ZXDQ, linewidth=1.3, alpha=0.9, label="短期均线")
    if valid_zxdkx.any():
        ax_price.plot(x[valid_zxdkx], zxdkx_vals[valid_zxdkx],
                      color=COLOR_ZXDKX, linewidth=1.3, alpha=0.9, linestyle="--", label="长期均线")

    # 成交量
    _draw_volume(ax_vol, x, volumes, opens, closes, n)

    # X 轴日期标签
    step = max(1, n // 12)
    ax_vol.set_xticks(x[::step])
    ax_vol.set_xticklabels(
        [pd.Timestamp(d).strftime("%m-%d") for d in dates[::step]],
        rotation=45, fontsize=8,
    )

    # 标签
    ax_price.set_title(f"{code}  日线", fontsize=13, fontweight="bold")
    ax_price.set_ylabel("价格", fontsize=10)
    ax_vol.set_ylabel("成交量", fontsize=10)
    ax_price.legend(loc="upper left", fontsize=9, framealpha=0.9)
    ax_price.set_facecolor("white")
    ax_vol.set_facecolor("white")
    ax_price.grid(True, alpha=GRID_ALPHA)
    ax_vol.grid(True, alpha=GRID_ALPHA)

    return fig


# ─────────────────────────────────────────────────────────────────────────────
# 周线图
# ─────────────────────────────────────────────────────────────────────────────

def make_weekly_chart(
    df: pd.DataFrame,
    code: str,
    ma_windows: List[int] = None,
    ma_colors: Dict[int, str] = None,
    bars: int = 60,
    **_kwargs,
) -> plt.Figure:
    """周线图：K线 + MA 均线 + 成交量"""
    ma_windows = ma_windows or [5, 10, 20, 60]
    ma_colors = ma_colors or {5: "#e67e22", 10: "#27ae60", 20: "#2980b9", 60: "#8e44ad"}

    wdf = _build_weekly_df(df)
    if bars > 0:
        wdf = wdf.tail(bars).reset_index(drop=True)

    n = len(wdf)
    x = np.arange(n)
    opens = wdf["open"].values.astype(float)
    closes = wdf["close"].values.astype(float)
    highs = wdf["high"].values.astype(float)
    lows = wdf["low"].values.astype(float)
    volumes = wdf["volume"].values.astype(float)
    dates = wdf["date"].values

    fig, (ax_price, ax_vol) = plt.subplots(
        2, 1, figsize=(FIG_WIDTH, FIG_HEIGHT * 0.75),
        gridspec_kw={"height_ratios": [3, 1]},
        sharex=True,
    )
    fig.subplots_adjust(hspace=0.05)

    # K 线
    _draw_candlestick(ax_price, opens, closes, highs, lows, n)

    # MA 均线
    for w in ma_windows:
        if len(wdf) >= w:
            ma = _calc_ma(wdf["close"], w).values
            valid = ~np.isnan(ma)
            if valid.any():
                ax_price.plot(x[valid], ma[valid],
                              color=ma_colors.get(w, "#aaa"), linewidth=1.2,
                              label=f"MA{w}")

    # 成交量
    _draw_volume(ax_vol, x, volumes, opens, closes, n)

    # X 轴
    step = max(1, n // 10)
    ax_vol.set_xticks(x[::step])
    ax_vol.set_xticklabels(
        [pd.Timestamp(d).strftime("%Y-%m-%d") for d in dates[::step]],
        rotation=45, fontsize=8,
    )

    ax_price.set_title(f"{code}  周线", fontsize=13, fontweight="bold")
    ax_price.set_ylabel("价格", fontsize=10)
    ax_vol.set_ylabel("成交量(周)", fontsize=10)
    ax_price.legend(loc="upper left", fontsize=9, framealpha=0.9)
    ax_price.set_facecolor("white")
    ax_vol.set_facecolor("white")
    ax_price.grid(True, alpha=GRID_ALPHA)
    ax_vol.grid(True, alpha=GRID_ALPHA)

    return fig
