"""
Z哥B1战法盈利股票特征分析脚本
分析回测结果中盈利股票的共同特征，包括：
- 板块分布分析
- 技术指标分布对比
- B1条件类型分析
- K线形态分析
- 收益分布分析

使用方式:
    python analyze_backtest_features.py --data-dir ./data --backtest-dir ./backtest_results
    python analyze_backtest_features.py --data-dir ./data --backtest-dir ./backtest_results --workers 10
    python analyze_backtest_features.py --data-dir ./data --backtest-dir ./backtest_results --output report.txt
"""

import argparse
import io
import logging
import re
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# 设置UTF-8编码输出
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("zgnb_analyze_features.log", encoding="utf-8")
    ]
)
logger = logging.getLogger(__name__)

# ==================== 常量定义 ====================
M1 = 14
M2 = 28
M3 = 57
M4 = 114

N1 = 3
N2 = 21

N = 20
M = 50

# ==================== 技术指标计算函数 ====================

def compute_brick_type(df: pd.DataFrame) -> pd.Series:
    """计算砖型图指标"""
    high4 = df["high"].rolling(4, min_periods=1).max()
    low4 = df["low"].rolling(4, min_periods=1).min()

    var1a = (high4 - df["close"]) / (high4 - low4 + 1e-9) * 100 - 90

    var2a = np.zeros(len(var1a))
    for i in range(len(var1a)):
        val = var1a.iloc[i]
        if pd.isna(val):
            var2a[i] = var2a[i-1] if i > 0 else 100
        elif i == 0:
            var2a[i] = val + 100
        else:
            var2a[i] = val * 0.25 + var2a[i-1] * 0.75 + 100

    var3a = (df["close"] - low4) / (high4 - low4 + 1e-9) * 100

    var4a = np.zeros(len(var3a))
    for i in range(len(var3a)):
        val = var3a.iloc[i]
        if pd.isna(val):
            var4a[i] = var4a[i-1] if i > 0 else 0
        elif i == 0:
            var4a[i] = val
        else:
            var4a[i] = val * (1/6) + var4a[i-1] * (5/6)

    var5a = np.zeros(len(var4a))
    for i in range(len(var4a)):
        val = var4a[i]
        if pd.isna(val):
            var5a[i] = var5a[i-1] if i > 0 else 100
        elif i == 0:
            var5a[i] = val + 100
        else:
            var5a[i] = val * (1/6) + var5a[i-1] * (5/6) + 100

    var6a = var5a - var2a
    brick_type = np.maximum(var6a - 4, 0)

    return pd.Series(brick_type, index=df.index)


def compute_rsi(df: pd.DataFrame, period: int = 3) -> pd.Series:
    """计算RSI指标"""
    lc = df["close"].shift(1)
    temp1 = np.maximum(df["close"] - lc, 0)
    temp2 = np.abs(df["close"] - lc)

    sma1 = np.zeros_like(temp1)
    sma2 = np.zeros_like(temp2)

    for i in range(len(temp1)):
        if i == 0:
            sma1[i] = temp1.iloc[i] if pd.notna(temp1.iloc[i]) else 0
            sma2[i] = temp2.iloc[i] if pd.notna(temp2.iloc[i]) else 1
        else:
            sma1[i] = temp1.iloc[i] * (1/period) + sma1[i-1] * ((period-1)/period) if pd.notna(temp1.iloc[i]) else sma1[i-1]
            sma2[i] = temp2.iloc[i] * (1/period) + sma2[i-1] * ((period-1)/period) if pd.notna(temp2.iloc[i]) else sma2[i-1]

    rsi = sma1 / (sma2 + 1e-9) * 100
    return pd.Series(rsi, index=df.index)


def compute_short_long(df: pd.DataFrame) -> Tuple[pd.Series, pd.Series]:
    """计算SHORT和LONG指标"""
    low_n1 = df["low"].rolling(N1, min_periods=1).min()
    high_c_n1 = df["close"].rolling(N1, min_periods=1).max()
    short = 100 * (df["close"] - low_n1) / (high_c_n1 - low_n1 + 1e-9)

    low_n2 = df["low"].rolling(N2, min_periods=1).min()
    high_c_n2 = df["close"].rolling(N2, min_periods=1).max()
    long_val = 100 * (df["close"] - low_n2) / (high_c_n2 - low_n2 + 1e-9)

    return short, long_val


def compute_trend_white_line(df: pd.DataFrame) -> pd.Series:
    """计算趋势白线: EMA(EMA(C,10),10)"""
    ema1 = df["close"].ewm(span=10, adjust=False).mean()
    ema2 = ema1.ewm(span=10, adjust=False).mean()
    return ema2


def compute_big_brother_yellow_line(df: pd.DataFrame) -> pd.Series:
    """计算大哥黄线: (MA14+MA28+MA57+MA114)/4"""
    ma14 = df["close"].rolling(M1, min_periods=1).mean()
    ma28 = df["close"].rolling(M2, min_periods=1).mean()
    ma57 = df["close"].rolling(M3, min_periods=1).mean()
    ma114 = df["close"].rolling(M4, min_periods=1).mean()
    return (ma14 + ma28 + ma57 + ma114) / 4


def compute_kdj_custom(df: pd.DataFrame, n: int = 9) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """计算KDJ指标"""
    low_n = df["low"].rolling(n, min_periods=1).min()
    high_n = df["high"].rolling(n, min_periods=1).max()
    rsv = (df["close"] - low_n) / (high_n - low_n + 1e-9) * 100

    k = np.zeros_like(rsv)
    d = np.zeros_like(rsv)

    for i in range(len(rsv)):
        if i == 0:
            k[i] = 50
            d[i] = 50
        else:
            k[i] = rsv.iloc[i] * (1/3) + k[i-1] * (2/3)
            d[i] = k[i] * (1/3) + d[i-1] * (2/3)

    j = 3 * k - 2 * d

    return pd.Series(k, index=df.index), pd.Series(d, index=df.index), pd.Series(j, index=df.index)


def compute_bbi(df: pd.DataFrame) -> pd.Series:
    """计算BBI指标: (MA3+MA6+MA12+MA24)/4"""
    ma3 = df["close"].rolling(3, min_periods=1).mean()
    ma6 = df["close"].rolling(6, min_periods=1).mean()
    ma12 = df["close"].rolling(12, min_periods=1).mean()
    ma24 = df["close"].rolling(24, min_periods=1).mean()
    return (ma3 + ma6 + ma12 + ma24) / 4


# ==================== 辅助函数 ====================

def get_board_type(code: str) -> str:
    """根据股票代码判断板块"""
    if code.startswith("30"):
        return "gem"      # 创业板
    elif code.startswith("68"):
        return "star"     # 科创板
    elif code.startswith("4") or code.startswith("8"):
        return "bj"       # 北交所
    else:
        return "main"     # 主板


def get_board_name(board_type: str) -> str:
    """获取板块中文名称"""
    names = {
        "main": "主板",
        "gem": "创业板",
        "star": "科创板",
        "bj": "北交所"
    }
    return names.get(board_type, board_type)


def hhv_bars(df: pd.DataFrame, column: str, period: int, idx: int) -> int:
    """HHVBARS: 求最高值位置"""
    if idx < period:
        window = df[column].iloc[:idx+1]
    else:
        window = df[column].iloc[idx-period+1:idx+1]

    max_val = window.max()
    for i in range(len(window)-1, -1, -1):
        if window.iloc[i] == max_val:
            return i
    return 0


def count_condition(series: pd.Series, condition, period: int, idx: int) -> int:
    """COUNT函数: 统计满足条件的周期数"""
    end = min(period, idx + 1)

    count = 0
    for i in range(max(0, idx - period + 1), idx + 1):
        try:
            if condition(series.iloc[i]):
                count += 1
        except:
            pass
    return count


def every_condition(series: pd.Series, condition, period: int, idx: int) -> bool:
    """EVERY函数: 判断是否一直满足条件"""
    if idx < period - 1:
        return False

    for i in range(idx - period + 1, idx + 1):
        try:
            if not condition(series.iloc[i]):
                return False
        except:
            return False
    return True


def get_amp_range(board_type: str, df: pd.DataFrame, idx: int) -> float:
    """获取振幅区间"""
    if board_type in ("gem", "star", "bj"):
        return 8

    if idx >= 200:
        recent = df.iloc[idx-200:idx]
    else:
        recent = df.iloc[:idx]

    if len(recent) > 0:
        max_gain = ((recent["close"] - recent["close"].shift(1)) / recent["close"].shift(1)).max()
        if pd.notna(max_gain) and max_gain > 0.15:
            return 8

    return 5


# ==================== B1条件判断函数 ====================

def check_chaomai_suoliang_guantou(df: pd.DataFrame, idx: int, code: str) -> bool:
    """超卖缩量拐头B"""
    if idx < 10:
        return False

    board_type = get_board_type(code)
    amp_range = get_amp_range(board_type, df, idx)
    relax_coef = 0.9 if board_type in ("gem", "star", "bj") else 1

    trend_white = compute_trend_white_line(df)
    yellow_line = compute_big_brother_yellow_line(df)
    rsi = compute_rsi(df)
    _, _, j = compute_kdj_custom(df)
    short, long = compute_short_long(df)

    c = df["close"].iloc[idx]
    o = df["open"].iloc[idx]
    h = df["high"].iloc[idx]
    l = df["low"].iloc[idx]

    uptrend = (trend_white.iloc[idx] >= yellow_line.iloc[idx] * 0.999 and
              (c >= yellow_line.iloc[idx] or (c > yellow_line.iloc[idx] * 0.975 and c > o)))

    rsi_prev = rsi.iloc[idx-1] if idx > 0 else rsi.iloc[idx]
    j_prev = j.iloc[idx-1] if idx > 0 else j.iloc[idx]
    rsi_turn = ((rsi.iloc[idx] - 15) >= rsi_prev) and (rsi_prev < 20 or j_prev < 14)

    day_amp = (h - l) / l * 100
    amp_ok = day_amp < (amp_range + 0.5)

    c_prev = df["close"].iloc[idx-1] if idx > 0 else c
    day_change = abs(c - c_prev) / c_prev * 100 * relax_coef

    rising_doji = (c > c_prev) and (abs(c - o) / o * 100 * relax_coef) < 1.8
    change_ok = (day_change < 2.3) or (rising_doji and day_change < 4)

    vday = hhv_bars(df, "volume", 40, idx)
    vday_close = df["close"].iloc[max(0, idx-vday)]
    vday_close_prev = df["close"].iloc[max(0, idx-vday-1)] if idx-vday-1 >= 0 else vday_close
    vday_open = df["open"].iloc[max(0, idx-vday)]

    not_big_green = (vday_close >= vday_close_prev) or (vday_close >= vday_open)
    big_green_far = (vday >= 15) and (not not_big_green)
    green_ok = not_big_green or big_green_far

    low_n = df["low"].rolling(N, min_periods=1).min().iloc[idx]
    high_n = df["high"].rolling(N, min_periods=1).max().iloc[idx]
    recent_amp = (high_n - low_n) / low_n * 100

    low_m = df["low"].rolling(M, min_periods=1).min().iloc[idx]
    high_m = df["high"].rolling(M, min_periods=1).max().iloc[idx]
    far_amp = (high_m - low_m) / low_m * 100

    single_needle = (short.iloc[idx] <= 20 and long.iloc[idx] >= 75) or ((long.iloc[idx] - short.iloc[idx]) >= 70)
    single_needle_count = count_condition(short, lambda x: x <= 20, 10, idx) + count_condition(long-short, lambda x: x >= 70, 10, idx)

    wash_move = single_needle_count >= 2
    move_ok = (recent_amp >= 15) or (far_amp >= 30) or wash_move

    c_above_yellow = c >= yellow_line.iloc[idx]

    return (uptrend and rsi_turn and amp_ok and change_ok and
            green_ok and move_ok and c_above_yellow)


def check_chaomai_suoliang(df: pd.DataFrame, idx: int, code: str) -> bool:
    """超卖缩量B"""
    if idx < 20:
        return False

    board_type = get_board_type(code)
    amp_range = get_amp_range(board_type, df, idx)
    relax_coef = 0.9 if board_type in ("gem", "star", "bj") else 1

    trend_white = compute_trend_white_line(df)
    yellow_line = compute_big_brother_yellow_line(df)
    rsi = compute_rsi(df)
    _, _, j = compute_kdj_custom(df)
    short, long = compute_short_long(df)

    c = df["close"].iloc[idx]
    o = df["open"].iloc[idx]
    h = df["high"].iloc[idx]
    l = df["low"].iloc[idx]
    v = df["volume"].iloc[idx]
    c_prev = df["close"].iloc[idx-1] if idx > 0 else c

    uptrend = (trend_white.iloc[idx] >= yellow_line.iloc[idx] * 0.999 and
              (c >= yellow_line.iloc[idx] or (c > yellow_line.iloc[idx] * 0.975 and c > o)))

    low_j_rsi = (j.iloc[idx] < 14 or rsi.iloc[idx] < 23)

    j_low = j.iloc[max(0, idx-20):idx+1].min()
    sum_ok = ((rsi.iloc[idx] + j.iloc[idx]) < 55) or (j.iloc[idx] == j_low)

    day_amp = (h - l) / l * 100
    amp_ok = day_amp < amp_range

    day_change = abs(c - c_prev) / c_prev * 100 * relax_coef
    rising_doji = (c > c_prev) and (abs(c - o) / o * 100 * relax_coef) < 1.8
    change_ok = (day_change < 2.5) or rising_doji

    vday = hhv_bars(df, "volume", 40, idx)
    vday_close = df["close"].iloc[max(0, idx-vday)]
    vday_close_prev = df["close"].iloc[max(0, idx-vday-1)] if idx-vday-1 >= 0 else vday_close
    vday_open = df["open"].iloc[max(0, idx-vday)]
    not_big_green = (vday_close >= vday_close_prev) or (vday_close >= vday_open)
    big_green_far = (vday >= 15) and (not not_big_green)
    green_ok = not_big_green or big_green_far

    vol_max20 = df["volume"].iloc[max(0, idx-20):idx+1].max()
    vol_max50 = df["volume"].iloc[max(0, idx-50):idx+1].max()
    vol_shrink = (v < vol_max20 * 0.416) or (v < vol_max50 / 3)

    vol_proper = (v < vol_max20 * 0.618) or (v < vol_max50 / 3)
    vol_ok = vol_shrink or (vol_proper and day_change < 1)

    low_n = df["low"].rolling(N, min_periods=1).min().iloc[idx]
    high_n = df["high"].rolling(N, min_periods=1).max().iloc[idx]
    recent_amp = (high_n - low_n) / low_n * 100

    low_m = df["low"].rolling(M, min_periods=1).min().iloc[idx]
    high_m = df["high"].rolling(M, min_periods=1).max().iloc[idx]
    far_amp = (high_m - low_m) / low_m * 100

    single_needle = (short.iloc[idx] <= 20 and long.iloc[idx] >= 75) or ((long.iloc[idx] - short.iloc[idx]) >= 70)
    single_needle_count = count_condition(short, lambda x: x <= 20, 10, idx) + count_condition(long-short, lambda x: x >= 70, 10, idx)
    wash_move = single_needle_count >= 2

    move_ok = (recent_amp >= 15) or (far_amp >= 30) or wash_move

    return uptrend and low_j_rsi and sum_ok and amp_ok and change_ok and green_ok and vol_ok and move_ok


def check_yuanshi_b1(df: pd.DataFrame, idx: int, code: str) -> bool:
    """原始B1"""
    if idx < 120:
        return False

    board_type = get_board_type(code)
    relax_coef = 0.9 if board_type in ("gem", "star", "bj") else 1

    trend_white = compute_trend_white_line(df)
    yellow_line = compute_big_brother_yellow_line(df)
    rsi = compute_rsi(df)
    _, _, j = compute_kdj_custom(df)
    bbi = compute_bbi(df)

    c = df["close"].iloc[idx]
    o = df["open"].iloc[idx]
    h = df["high"].iloc[idx]
    l = df["low"].iloc[idx]
    v = df["volume"].iloc[idx]
    c_prev = df["close"].iloc[idx-1] if idx > 0 else c

    base_ok = (trend_white.iloc[idx] > yellow_line.iloc[idx] and
               c >= yellow_line.iloc[idx] * 0.99 and
               yellow_line.iloc[idx] >= yellow_line.iloc[idx-1] * 0.999)

    low_j_rsi = (j.iloc[idx] < 13 or rsi.iloc[idx] < 21)

    rsi_j_sum = rsi.iloc[idx] + j.iloc[idx]
    rsi_j_min = (rsi.iloc[max(0, idx-15):idx+1] + j.iloc[max(0, idx-15):idx+1]).min()
    sum_ok = rsi_j_sum < rsi_j_min * 1.5

    vol_max20 = df["volume"].iloc[max(0, idx-20):idx+1].max()
    vol_max50 = df["volume"].iloc[max(0, idx-50):idx+1].max()
    vol_proper = (v < vol_max20 * 0.618) or (v < vol_max50 / 3)

    vday = hhv_bars(df, "volume", 40, idx)
    vday_close = df["close"].iloc[max(0, idx-vday)]
    vday_close_prev = df["close"].iloc[max(0, idx-vday-1)] if idx-vday-1 >= 0 else vday_close
    vday_open = df["open"].iloc[max(0, idx-vday)]
    not_big_green = (vday_close >= vday_close_prev) or (vday_close >= vday_open)
    big_green_far = (vday >= 15) and (not not_big_green)
    green_ok = not_big_green or big_green_far

    body_small = (abs(c - o) * 100 / o) < 1.5
    vol_super_shrink = (v < vol_max20 / 4) or (v < vol_max50 / 6)
    vol_llv = df["volume"].iloc[max(0, idx-20):idx+1].min()
    vol_proper_llv = (vol_proper and v < vol_llv * 1.1 and j.iloc[idx] == j.iloc[max(0, idx-20):idx+1].min())

    dist_white = abs(c - trend_white.iloc[idx]) / c * 100
    dist_bbi = abs(c - bbi.iloc[idx]) / c * 100
    dist_yellow = abs(c - yellow_line.iloc[idx]) / yellow_line.iloc[idx] * 100
    dist_ok = (vol_proper and (dist_white < 1.8 or dist_bbi < 1.5 or dist_yellow < 2.8))

    body_ok = body_small or vol_super_shrink or vol_proper_llv or dist_ok

    low_n = df["low"].rolling(N, min_periods=1).min().iloc[idx]
    high_n = df["high"].rolling(N, min_periods=1).max().iloc[idx]
    recent_amp = (high_n - low_n) / low_n * 100

    low_m = df["low"].rolling(M, min_periods=1).min().iloc[idx]
    high_m = df["high"].rolling(M, min_periods=1).max().iloc[idx]
    far_amp = (high_m - low_m) / low_m * 100

    move_ok = (recent_amp >= 15) or (far_amp >= 30)

    return base_ok and low_j_rsi and sum_ok and vol_proper and green_ok and body_ok and move_ok


def check_chaomai_chaosuoliang(df: pd.DataFrame, idx: int, code: str) -> bool:
    """超卖超缩量B"""
    if idx < 60:
        return False

    board_type = get_board_type(code)
    amp_range = get_amp_range(board_type, df, idx)
    relax_coef = 0.9 if board_type in ("gem", "star", "bj") else 1

    trend_white = compute_trend_white_line(df)
    yellow_line = compute_big_brother_yellow_line(df)
    rsi = compute_rsi(df)
    _, _, j = compute_kdj_custom(df)
    short, long = compute_short_long(df)

    c = df["close"].iloc[idx]
    o = df["open"].iloc[idx]
    h = df["high"].iloc[idx]
    l = df["low"].iloc[idx]
    v = df["volume"].iloc[idx]
    c_prev = df["close"].iloc[idx-1] if idx > 0 else c

    uptrend = (trend_white.iloc[idx] >= yellow_line.iloc[idx] * 0.999 and
              (c >= yellow_line.iloc[idx] or (c > yellow_line.iloc[idx] * 0.975 and c > o)))

    low_j_rsi = (j.iloc[idx] < 14 or rsi.iloc[idx] < 23)

    sum_ok = (rsi.iloc[idx] + j.iloc[idx]) < 60

    low_m = df["low"].rolling(M, min_periods=1).min().iloc[idx]
    high_m = df["high"].rolling(M, min_periods=1).max().iloc[idx]
    far_amp = (high_m - low_m) / low_m * 100
    far_amp_ok = far_amp >= 45

    low_n = df["low"].rolling(N, min_periods=1).min().iloc[idx]
    high_n = df["high"].rolling(N, min_periods=1).max().iloc[idx]
    recent_amp = (high_n - low_n) / low_n * 100

    super_move = recent_amp >= 60

    day_amp = (h - l) / l * 100
    amp_ok = (day_amp < amp_range) or (super_move and day_amp < amp_range + 3.2 and c > o and c >= trend_white.iloc[idx])

    v_prev = df["volume"].iloc[idx-1] if idx > 0 else v
    vol_c_ok = ((c < o and v < v_prev and c >= yellow_line.iloc[idx]) or (c >= o))

    day_change = abs(c - c_prev) / c_prev * 100 * relax_coef
    rising_doji = (c > c_prev) and (abs(c - o) / o * 100 * relax_coef) < 1.8
    change_ok = (day_change < 2) or rising_doji

    vday = hhv_bars(df, "volume", 40, idx)
    vday_close = df["close"].iloc[max(0, idx-vday)]
    vday_close_prev = df["close"].iloc[max(0, idx-vday-1)] if idx-vday-1 >= 0 else vday_close
    vday_open = df["open"].iloc[max(0, idx-vday)]
    not_big_green = (vday_close >= vday_close_prev) or (vday_close >= vday_open)
    big_green_far = (vday >= 15) and (not not_big_green)
    green_ok = not_big_green or big_green_far

    vol_max30 = df["volume"].iloc[max(0, idx-30):idx+1].max()
    vol_max50 = df["volume"].iloc[max(0, idx-50):idx+1].max()
    vol_super_shrink = (v < vol_max30 / 4) or (v < vol_max50 / 6)

    move_ok = (recent_amp >= 15) or (far_amp >= 30)

    return (uptrend and low_j_rsi and sum_ok and far_amp_ok and amp_ok and
            vol_c_ok and change_ok and green_ok and vol_super_shrink and move_ok)


def check_huicai_baixian(df: pd.DataFrame, idx: int, code: str) -> bool:
    """回踩白线B"""
    if idx < 30:
        return False

    board_type = get_board_type(code)
    amp_range = get_amp_range(board_type, df, idx)
    relax_coef = 0.9 if board_type in ("gem", "star", "bj") else 1

    trend_white = compute_trend_white_line(df)
    yellow_line = compute_big_brother_yellow_line(df)
    rsi = compute_rsi(df)
    _, _, j = compute_kdj_custom(df)
    short, long = compute_short_long(df)
    bbi = compute_bbi(df)

    c = df["close"].iloc[idx]
    o = df["open"].iloc[idx]
    h = df["high"].iloc[idx]
    l = df["low"].iloc[idx]
    v = df["volume"].iloc[idx]
    c_prev = df["close"].iloc[idx-1] if idx > 0 else c

    yellow_rising = yellow_line.iloc[max(0, idx-13):idx+1].min() >= yellow_line.iloc[max(0, idx-14):idx].min() * 0.999

    white_rising = trend_white.iloc[idx] >= trend_white.iloc[idx-1]
    white_above = (trend_white.iloc[max(0, idx-20):idx+1] > yellow_line.iloc[max(0, idx-20):idx+1]).all()

    white_always_rising = trend_white.iloc[max(0, idx-11):idx+1].min() >= trend_white.iloc[max(0, idx-12):idx].min()

    red_fat = count_condition(df["close"], lambda x: x >= 0, 15, idx) > 7
    green_thin = count_condition(df["close"], lambda x: x > 0, 11, idx) > 5

    strong_trend = (yellow_rising and white_rising and white_above and
                    white_always_rising and (red_fat or green_thin))

    single_needle = (short.iloc[idx] <= 20 and long.iloc[idx] >= 75) or ((long.iloc[idx] - short.iloc[idx]) >= 70)

    low_j_rsi = (j.iloc[idx] < 30 or rsi.iloc[idx] < 40 or single_needle)
    sum_ok = (rsi.iloc[idx] + j.iloc[idx]) < 70

    day_amp = (h - l) / l * 100
    dist_white = abs(c - trend_white.iloc[idx]) / c * 100
    dist_bbi = abs(c - bbi.iloc[idx]) / c * 100
    amp_ok = (day_amp < amp_range + 0.5) or (dist_white < 1) or (dist_bbi < 1)

    l_dist_white = abs(l - trend_white.iloc[idx]) / trend_white.iloc[idx] * 100
    l_dist_bbi = abs(l - bbi.iloc[idx]) / bbi.iloc[idx] * 100

    touch_white = ((c >= trend_white.iloc[idx] and dist_white <= 2) or
                   (c < trend_white.iloc[idx] and dist_white < 0.8))
    touch_bbi = (c >= bbi.iloc[idx] and dist_bbi < 2.5 and l_dist_bbi < 1 and
                 dist_white <= 3 and abs(c - c_prev) / c_prev * 100 * relax_coef < 1 and c > c_prev)

    white_ok = touch_white or touch_bbi

    day_change = abs(c - c_prev) / c_prev * 100 * relax_coef
    support = c >= trend_white.iloc[idx] and dist_white < 1.5
    change_ok = (day_change < 2) or (day_change < 5 and support)

    vday = hhv_bars(df, "volume", 40, idx)
    vday_close = df["close"].iloc[max(0, idx-vday)]
    vday_close_prev = df["close"].iloc[max(0, idx-vday-1)] if idx-vday-1 >= 0 else vday_close
    vday_open = df["open"].iloc[max(0, idx-vday)]
    not_big_green = (vday_close >= vday_close_prev) or (vday_close >= vday_open)
    big_green_far = (vday >= 15) and (not not_big_green)
    green_ok = not_big_green or big_green_far

    vol_max20 = df["volume"].iloc[max(0, idx-20):idx+1].max()
    vol_max50 = df["volume"].iloc[max(0, idx-50):idx+1].max()
    vol_shrink = (v < vol_max20 * 0.45) or (v < vol_max50 / 3)

    low_n = df["low"].rolling(N, min_periods=1).min().iloc[idx]
    high_n = df["high"].rolling(N, min_periods=1).max().iloc[idx]
    recent_amp = (high_n - low_n) / low_n * 100

    low_m = df["low"].rolling(M, min_periods=1).min().iloc[idx]
    high_m = df["high"].rolling(M, min_periods=1).max().iloc[idx]
    far_amp = (high_m - low_m) / low_m * 100

    move_ok = (recent_amp >= 15) or (far_amp >= 30)

    l_ok = l <= c_prev

    return (strong_trend and low_j_rsi and sum_ok and amp_ok and white_ok and
            change_ok and green_ok and vol_shrink and move_ok and l_ok)


def check_huicai_chaoji(df: pd.DataFrame, idx: int, code: str) -> bool:
    """回踩超级B"""
    if idx < 30:
        return False

    board_type = get_board_type(code)
    amp_range = get_amp_range(board_type, df, idx)
    relax_coef = 0.9 if board_type in ("gem", "star", "bj") else 1

    trend_white = compute_trend_white_line(df)
    yellow_line = compute_big_brother_yellow_line(df)
    rsi = compute_rsi(df)
    _, _, j = compute_kdj_custom(df)
    bbi = compute_bbi(df)

    c = df["close"].iloc[idx]
    o = df["open"].iloc[idx]
    h = df["high"].iloc[idx]
    l = df["low"].iloc[idx]
    v = df["volume"].iloc[idx]
    c_prev = df["close"].iloc[idx-1] if idx > 0 else c

    # 强趋势
    yellow_rising = yellow_line.iloc[max(0, idx-13):idx+1].min() >= yellow_line.iloc[max(0, idx-14):idx].min() * 0.999

    white_rising = trend_white.iloc[idx] >= trend_white.iloc[idx-1]
    white_above = (trend_white.iloc[max(0, idx-20):idx+1] > yellow_line.iloc[max(0, idx-20):idx+1]).all()

    white_always_rising = trend_white.iloc[max(0, idx-11):idx+1].min() >= trend_white.iloc[max(0, idx-12):idx].min()

    strong_trend = yellow_rising and white_rising and white_above and white_always_rising

    # J或RSI或单针
    low_j_rsi = j.iloc[idx] < 25 or rsi.iloc[idx] < 35

    # 振幅
    day_amp = (h - l) / l * 100
    dist_white = abs(c - trend_white.iloc[idx]) / c * 100
    dist_bbi = abs(c - bbi.iloc[idx]) / c * 100
    amp_ok = (day_amp < amp_range + 0.5) or (dist_white < 1) or (dist_bbi < 1)

    # 回踩白线或BBI
    l_dist_white = abs(l - trend_white.iloc[idx]) / trend_white.iloc[idx] * 100
    l_dist_bbi = abs(l - bbi.iloc[idx]) / bbi.iloc[idx] * 100

    touch_white = ((c >= trend_white.iloc[idx] and dist_white <= 2) or
                   (c < trend_white.iloc[idx] and dist_white < 0.8))
    touch_bbi = (c >= bbi.iloc[idx] and dist_bbi < 2.5 and l_dist_bbi < 1 and
                 dist_white <= 3 and abs(c - c_prev) / c_prev * 100 * relax_coef < 1 and c > c_prev)

    white_ok = touch_white or touch_bbi

    # 涨跌幅
    day_change = abs(c - c_prev) / c_prev * 100 * relax_coef
    support = c >= trend_white.iloc[idx] and dist_white < 1.5
    change_ok = (day_change < 2) or (day_change < 5 and support)

    # 大绿棒
    vday = hhv_bars(df, "volume", 40, idx)
    vday_close = df["close"].iloc[max(0, idx-vday)]
    vday_close_prev = df["close"].iloc[max(0, idx-vday-1)] if idx-vday-1 >= 0 else vday_close
    vday_open = df["open"].iloc[max(0, idx-vday)]
    not_big_green = (vday_close >= vday_close_prev) or (vday_close >= vday_open)
    big_green_far = (vday >= 15) and (not not_big_green)
    green_ok = not_big_green or big_green_far

    # 缩量
    vol_max20 = df["volume"].iloc[max(0, idx-20):idx+1].max()
    vol_max50 = df["volume"].iloc[max(0, idx-50):idx+1].max()
    vol_shrink = (v < vol_max20 * 0.45) or (v < vol_max50 / 3)

    # 异动
    low_n = df["low"].rolling(N, min_periods=1).min().iloc[idx]
    high_n = df["high"].rolling(N, min_periods=1).max().iloc[idx]
    recent_amp = (high_n - low_n) / low_n * 100

    low_m = df["low"].rolling(M, min_periods=1).min().iloc[idx]
    high_m = df["high"].rolling(M, min_periods=1).max().iloc[idx]
    far_amp = (high_m - low_m) / low_m * 100

    move_ok = (recent_amp >= 15) or (far_amp >= 30)

    return (strong_trend and low_j_rsi and amp_ok and white_ok and
            change_ok and green_ok and vol_shrink and move_ok)


def identify_b1_type(df: pd.DataFrame, idx: int, code: str) -> str:
    """判断B1条件类型"""
    # 按优先级顺序检查每个B1条件
    if check_chaomai_suoliang_guantou(df, idx, code):
        return "超卖缩量拐头B"
    if check_chaomai_suoliang(df, idx, code):
        return "超卖缩量B"
    if check_yuanshi_b1(df, idx, code):
        return "原始B1"
    if check_chaomai_chaosuoliang(df, idx, code):
        return "超卖超缩量B"
    if check_huicai_baixian(df, idx, code):
        return "回踩白线B"
    if check_huicai_chaoji(df, idx, code):
        return "回踩超级B"
    return "未知"


# ==================== 特征数据类 ====================

@dataclass
class StockFeatures:
    """股票特征数据"""
    code: str
    select_date: pd.Timestamp
    return_pct: float
    is_profit: bool

    # 板块信息
    board_type: str

    # 技术指标（选股当日T的值）
    j: float = 0
    rsi: float = 0
    short: float = 0
    long: float = 0
    brick_type: float = 0
    trend_white: float = 0
    yellow_line: float = 0
    bbi: float = 0

    # 动能指标
    j_momentum: float = 0
    rsi_momentum: float = 0
    yellow_pillar: float = 0
    x_momentum: float = 0

    # K线形态
    is_red: bool = False
    is_doji: bool = False
    body_pct: float = 0
    upper_shadow_pct: float = 0
    day_amp: float = 0
    day_change: float = 0

    # 成交量特征
    vol_ratio_20: float = 0
    vol_ratio_50: float = 0
    is_shrink: bool = False

    # 振幅特征
    recent_amp: float = 0
    far_amp: float = 0

    # B1条件类型
    b1_type: str = ""


# ==================== 特征提取函数 ====================

def extract_single_stock(task: dict) -> Optional[StockFeatures]:
    """
    单股票特征提取函数（用于多进程）

    参数:
        task: 包含 code, select_date, return_pct, data_dir 的字典

    返回:
        StockFeatures 或 None（数据文件不存在时）
    """
    code = task['code']
    select_date = task['select_date']
    return_pct = task['return_pct']
    data_dir = Path(task['data_dir'])

    # 读取CSV数据
    csv_path = data_dir / f"{code}.csv"
    if not csv_path.exists():
        return None

    try:
        df = pd.read_csv(csv_path)
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date').reset_index(drop=True)

        # 找到选股日期位置
        idx_list = df[df['date'] == select_date].index.tolist()
        if not idx_list:
            return None

        idx = idx_list[0]

        # 计算所有技术指标
        _, _, j = compute_kdj_custom(df)
        rsi = compute_rsi(df)
        short, long = compute_short_long(df)
        brick_type = compute_brick_type(df)
        trend_white = compute_trend_white_line(df)
        yellow_line = compute_big_brother_yellow_line(df)
        bbi = compute_bbi(df)

        # 当日数据
        c = df["close"].iloc[idx]
        o = df["open"].iloc[idx]
        h = df["high"].iloc[idx]
        l = df["low"].iloc[idx]
        v = df["volume"].iloc[idx]
        c_prev = df["close"].iloc[idx-1] if idx > 0 else c

        # 动能指标
        j_prev = j.iloc[idx-1] if idx > 0 else j.iloc[idx]
        rsi_prev = rsi.iloc[idx-1] if idx > 0 else rsi.iloc[idx]
        j_momentum = j.iloc[idx] - j_prev
        rsi_momentum = rsi.iloc[idx] - rsi_prev

        # 黄柱 = SHORT - LONG
        yellow_pillar = short.iloc[idx] - long.iloc[idx]

        # X动能 = 砖型图
        x_momentum = brick_type.iloc[idx]

        # K线形态
        is_red = c >= c_prev
        body_size = abs(c - o)
        body_pct = body_size / o * 100 if o > 0 else 0
        is_doji = body_pct < 1.8

        upper_shadow = h - max(c, o)
        upper_shadow_pct = upper_shadow / max(c, o) * 100 if max(c, o) > 0 else 0

        day_amp = (h - l) / l * 100 if l > 0 else 0
        day_change = (c - c_prev) / c_prev * 100 if c_prev > 0 else 0

        # 成交量特征
        vol_max20 = df["volume"].iloc[max(0, idx-20):idx+1].max()
        vol_max50 = df["volume"].iloc[max(0, idx-50):idx+1].max()
        vol_ratio_20 = v / vol_max20 if vol_max20 > 0 else 0
        vol_ratio_50 = v / vol_max50 if vol_max50 > 0 else 0
        is_shrink = v < vol_max20 * 0.5

        # 振幅特征
        low_n = df["low"].rolling(N, min_periods=1).min().iloc[idx]
        high_n = df["high"].rolling(N, min_periods=1).max().iloc[idx]
        recent_amp = (high_n - low_n) / low_n * 100 if low_n > 0 else 0

        low_m = df["low"].rolling(M, min_periods=1).min().iloc[idx]
        high_m = df["high"].rolling(M, min_periods=1).max().iloc[idx]
        far_amp = (high_m - low_m) / low_m * 100 if low_m > 0 else 0

        # 判断B1类型
        b1_type = identify_b1_type(df, idx, code)

        # 板块类型
        board_type = get_board_type(code)

        return StockFeatures(
            code=code,
            select_date=select_date,
            return_pct=return_pct,
            is_profit=return_pct > 0,
            board_type=board_type,
            j=j.iloc[idx],
            rsi=rsi.iloc[idx],
            short=short.iloc[idx],
            long=long.iloc[idx],
            brick_type=brick_type.iloc[idx],
            trend_white=trend_white.iloc[idx],
            yellow_line=yellow_line.iloc[idx],
            bbi=bbi.iloc[idx],
            j_momentum=j_momentum,
            rsi_momentum=rsi_momentum,
            yellow_pillar=yellow_pillar,
            x_momentum=x_momentum,
            is_red=is_red,
            is_doji=is_doji,
            body_pct=body_pct,
            upper_shadow_pct=upper_shadow_pct,
            day_amp=day_amp,
            day_change=day_change,
            vol_ratio_20=vol_ratio_20,
            vol_ratio_50=vol_ratio_50,
            is_shrink=is_shrink,
            recent_amp=recent_amp,
            far_amp=far_amp,
            b1_type=b1_type
        )
    except Exception as e:
        logger.warning(f"处理 {code} 失败: {e}")
        return None


# ==================== 特征分析器类 ====================

class FeatureAnalyzer:
    """特征分析器"""

    B1_CHECK_FUNCTIONS = [
        check_chaomai_suoliang_guantou,
        check_chaomai_suoliang,
        check_yuanshi_b1,
        check_chaomai_chaosuoliang,
        check_huicai_baixian,
        check_huicai_chaoji,
    ]

    B1_TYPE_NAMES = [
        "超卖缩量拐头B",
        "超卖缩量B",
        "原始B1",
        "超卖超缩量B",
        "回踩白线B",
        "回踩超级B",
    ]

    def __init__(self, data_dir: Path, backtest_dir: Path, workers: int = None):
        self.data_dir = Path(data_dir)
        self.backtest_dir = Path(backtest_dir)
        self.workers = workers or 4
        self.features: List[StockFeatures] = []

    def load_backtest_results(self) -> List[dict]:
        """
        从回测日志中解析所有交易数据

        返回:
            交易列表，每个元素包含 code, select_date, return_pct
        """
        log_file = self.backtest_dir / "backtest_summary_all.log"
        if not log_file.exists():
            raise FileNotFoundError(f"回测日志不存在: {log_file}")

        transactions = []

        with open(log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        # 解析个股明细部分
        for line in lines:
            # 匹配个股明细行格式:  代码         买入日期         卖出日期         买入价      卖出价      收益率
            # 示例:  300346     2026-01-06   2026-01-07   44.64    55.19    +23.63%
            match = re.search(r'(\d{6})\s+(\d{4}-\d{2}-\d{2})\s+(\d{4}-\d{2}-\d{2})\s+([\d.]+)\s+([\d.]+)\s+([+-]?[\d.]+)%', line)
            if match:
                code = match.group(1)
                buy_date = pd.to_datetime(match.group(2))
                return_pct = float(match.group(6))

                transactions.append({
                    'code': code,
                    'select_date': buy_date,
                    'return_pct': return_pct
                })

        logger.info(f"从回测日志中解析到 {len(transactions)} 笔交易")
        return transactions

    def extract_all_features_parallel(self, transactions: List[dict]) -> List[StockFeatures]:
        """
        多进程并行提取所有股票特征

        参数:
            transactions: 交易列表

        返回:
            特征列表
        """
        results = []
        total = len(transactions)

        # 添加 data_dir 到每个任务
        for task in transactions:
            task['data_dir'] = str(self.data_dir)

        with ProcessPoolExecutor(max_workers=self.workers) as executor:
            futures = {executor.submit(extract_single_stock, task): task
                      for task in transactions}

            completed = 0
            for future in as_completed(futures):
                completed += 1
                try:
                    feature = future.result(timeout=30)
                    if feature:
                        results.append(feature)
                    if completed % 100 == 0 or completed == total:
                        logger.info(f"进度: {completed}/{total} ({completed/total*100:.1f}%)")
                except Exception as e:
                    task = futures[future]
                    logger.warning(f"处理 {task['code']} 失败: {e}")

        self.features = results
        logger.info(f"成功提取 {len(results)} 只股票的特征")
        return results

    def analyze_board_distribution(self) -> Dict:
        """板块分布分析"""
        board_stats = {}

        for feature in self.features:
            board = feature.board_type
            if board not in board_stats:
                board_stats[board] = {
                    'total': 0,
                    'profit': 0,
                    'loss': 0,
                    'returns': []
                }

            board_stats[board]['total'] += 1
            board_stats[board]['returns'].append(feature.return_pct)
            if feature.is_profit:
                board_stats[board]['profit'] += 1
            else:
                board_stats[board]['loss'] += 1

        # 计算统计指标
        result = {}
        for board, stats in board_stats.items():
            returns = stats['returns']
            result[board] = {
                'board_name': get_board_name(board),
                'total': stats['total'],
                'profit': stats['profit'],
                'loss': stats['loss'],
                'win_rate': stats['profit'] / stats['total'] * 100 if stats['total'] > 0 else 0,
                'avg_return': np.mean(returns),
                'max_return': np.max(returns),
                'min_return': np.min(returns)
            }

        return result

    def analyze_indicator_distribution(self) -> Dict:
        """技术指标分布对比（盈利组 vs 亏损组）"""
        profit_features = [f for f in self.features if f.is_profit]
        loss_features = [f for f in self.features if not f.is_profit]

        indicators = ['j', 'rsi', 'short', 'long', 'brick_type', 'yellow_pillar']
        result = {}

        for ind in indicators:
            profit_values = [getattr(f, ind) for f in profit_features]
            loss_values = [getattr(f, ind) for f in loss_features]

            # 计算相关性
            all_values = [getattr(f, ind) for f in self.features]
            all_returns = [f.return_pct for f in self.features]

            try:
                corr = np.corrcoef(all_values, all_returns)[0, 1]
            except:
                corr = 0

            result[ind] = {
                'profit_mean': np.mean(profit_values),
                'profit_median': np.median(profit_values),
                'loss_mean': np.mean(loss_values),
                'loss_median': np.median(loss_values),
                'diff': np.mean(profit_values) - np.mean(loss_values),
                'correlation': corr if not np.isnan(corr) else 0
            }

        return result

    def analyze_b1_type_distribution(self) -> Dict:
        """B1条件类型分析"""
        b1_stats = {}

        for feature in self.features:
            b1_type = feature.b1_type if feature.b1_type else "未知"
            if b1_type not in b1_stats:
                b1_stats[b1_type] = {
                    'total': 0,
                    'profit': 0,
                    'returns': []
                }

            b1_stats[b1_type]['total'] += 1
            b1_stats[b1_type]['returns'].append(feature.return_pct)
            if feature.is_profit:
                b1_stats[b1_type]['profit'] += 1

        result = {}
        for b1_type, stats in b1_stats.items():
            returns = stats['returns']
            result[b1_type] = {
                'total': stats['total'],
                'profit': stats['profit'],
                'win_rate': stats['profit'] / stats['total'] * 100 if stats['total'] > 0 else 0,
                'avg_return': np.mean(returns),
                'max_return': np.max(returns),
                'min_return': np.min(returns)
            }

        return result

    def analyze_pattern_distribution(self) -> Dict:
        """K线形态分析"""
        result = {
            'red_candle': {'profit': 0, 'total': 0},
            'green_candle': {'profit': 0, 'total': 0},
            'doji': {'profit': 0, 'total': 0},
            'shrink': {'profit': 0, 'total': 0},
        }

        for feature in self.features:
            # 阳线/阴线
            if feature.is_red:
                result['red_candle']['total'] += 1
                if feature.is_profit:
                    result['red_candle']['profit'] += 1
            else:
                result['green_candle']['total'] += 1
                if feature.is_profit:
                    result['green_candle']['profit'] += 1

            # 十字星
            if feature.is_doji:
                result['doji']['total'] += 1
                if feature.is_profit:
                    result['doji']['profit'] += 1

            # 缩量
            if feature.is_shrink:
                result['shrink']['total'] += 1
                if feature.is_profit:
                    result['shrink']['profit'] += 1

        # 计算胜率
        for key, stats in result.items():
            stats['win_rate'] = stats['profit'] / stats['total'] * 100 if stats['total'] > 0 else 0

        return result

    def analyze_high_profit_stocks(self, threshold: float = 10) -> Dict:
        """
        高收益股票特征分析

        参数:
            threshold: 收益率阈值（百分比）

        返回:
            高收益股票的统计特征
        """
        high_profit = [f for f in self.features if f.return_pct >= threshold]

        if not high_profit:
            return {}

        # 板块分布
        board_dist = {}
        for f in high_profit:
            board = f.board_type
            board_dist[board] = board_dist.get(board, 0) + 1

        # B1类型分布
        b1_dist = {}
        for f in high_profit:
            b1_type = f.b1_type if f.b1_type else "未知"
            b1_dist[b1_type] = b1_dist.get(b1_type, 0) + 1

        # 技术指标区间
        j_values = [f.j for f in high_profit]
        rsi_values = [f.rsi for f in high_profit]

        return {
            'count': len(high_profit),
            'avg_return': np.mean([f.return_pct for f in high_profit]),
            'max_return': np.max([f.return_pct for f in high_profit]),
            'board_distribution': {k: v/len(high_profit)*100 for k, v in board_dist.items()},
            'b1_distribution': {k: v/len(high_profit)*100 for k, v in b1_dist.items()},
            'j_range': (np.min(j_values), np.max(j_values)),
            'rsi_range': (np.min(rsi_values), np.max(rsi_values)),
        }

    def generate_report(self) -> str:
        """生成分析报告"""
        lines = []
        lines.append("=" * 60)
        lines.append("Z哥B1战法盈利股票特征分析报告")
        lines.append("=" * 60)
        lines.append("")

        # 整体统计
        total = len(self.features)
        profit_count = sum(1 for f in self.features if f.is_profit)
        loss_count = total - profit_count
        overall_win_rate = profit_count / total * 100 if total > 0 else 0
        avg_return = np.mean([f.return_pct for f in self.features])

        lines.append("一、整体统计")
        lines.append("-" * 60)
        lines.append(f"总交易次数: {total}")
        lines.append(f"盈利次数: {profit_count}")
        lines.append(f"亏损次数: {loss_count}")
        lines.append(f"整体胜率: {overall_win_rate:.1f}%")
        lines.append(f"平均收益: {avg_return:.2f}%")
        lines.append("")

        # 板块分布分析
        board_stats = self.analyze_board_distribution()
        lines.append("二、板块分布分析")
        lines.append("-" * 60)
        lines.append(f"{'板块':<8} {'交易次数':<8} {'盈利次数':<8} {'亏损次数':<8} {'胜率':<8} {'平均收益'}")
        lines.append("-" * 60)

        for board in ['main', 'gem', 'star', 'bj']:
            if board in board_stats:
                s = board_stats[board]
                lines.append(f"{s['board_name']:<8} {s['total']:<8} {s['profit']:<8} {s['loss']:<8} {s['win_rate']:<8.1f}% {s['avg_return']:+.2f}%")
        lines.append("")

        # 技术指标分布对比
        indicator_stats = self.analyze_indicator_distribution()
        lines.append("三、技术指标分布对比")
        lines.append("-" * 60)
        lines.append(f"{'指标':<12} {'盈利组均值':<12} {'亏损组均值':<12} {'差异':<10} {'相关性'}")
        lines.append("-" * 60)

        indicator_names = {
            'j': 'J值',
            'rsi': 'RSI',
            'short': 'SHORT',
            'long': 'LONG',
            'brick_type': '砖型图',
            'yellow_pillar': '黄柱'
        }

        for ind, name in indicator_names.items():
            if ind in indicator_stats:
                s = indicator_stats[ind]
                lines.append(f"{name:<12} {s['profit_mean']:<12.2f} {s['loss_mean']:<12.2f} {s['diff']:<10.2f} {s['correlation']:+.3f}")
        lines.append("")

        # B1条件类型分析
        b1_stats = self.analyze_b1_type_distribution()
        lines.append("四、B1条件类型分析")
        lines.append("-" * 60)
        lines.append(f"{'条件类型':<16} {'触发次数':<10} {'胜率':<10} {'平均收益'}")
        lines.append("-" * 60)

        for b1_type in ['超卖缩量拐头B', '超卖缩量B', '原始B1', '超卖超缩量B', '回踩白线B', '回踩超级B', '未知']:
            if b1_type in b1_stats:
                s = b1_stats[b1_type]
                lines.append(f"{b1_type:<16} {s['total']:<10} {s['win_rate']:<10.1f}% {s['avg_return']:+.2f}%")
        lines.append("")

        # K线形态分析
        pattern_stats = self.analyze_pattern_distribution()
        lines.append("五、K线形态分析")
        lines.append("-" * 60)
        lines.append(f"{'形态':<12} {'盈利次数':<10} {'总次数':<10} {'胜率'}")
        lines.append("-" * 60)

        pattern_names = {
            'red_candle': ('阳线', pattern_stats['red_candle']),
            'green_candle': ('阴线', pattern_stats['green_candle']),
            'doji': ('十字星', pattern_stats['doji']),
            'shrink': ('缩量', pattern_stats['shrink']),
        }

        for name, (cn_name, stats) in pattern_names.items():
            lines.append(f"{cn_name:<12} {stats['profit']:<10} {stats['total']:<10} {stats['win_rate']:.1f}%")
        lines.append("")

        # 高收益股票特征
        high_profit_stats = self.analyze_high_profit_stocks(threshold=10)
        if high_profit_stats:
            lines.append("六、高收益股票特征（收益≥10%）")
            lines.append("-" * 60)
            lines.append(f"数量: {high_profit_stats['count']} 只")
            lines.append(f"平均收益: {high_profit_stats['avg_return']:.2f}%")
            lines.append(f"最大收益: {high_profit_stats['max_return']:.2f}%")
            lines.append("")
            lines.append("特征分布:")

            lines.append(f"- J值区间: {high_profit_stats['j_range'][0]:.2f} - {high_profit_stats['j_range'][1]:.2f}")
            lines.append(f"- RSI区间: {high_profit_stats['rsi_range'][0]:.2f} - {high_profit_stats['rsi_range'][1]:.2f}")

            lines.append("- 板块分布:")
            for board, pct in high_profit_stats['board_distribution'].items():
                lines.append(f"  · {get_board_name(board)}: {pct:.1f}%")

            lines.append("- B1类型分布:")
            for b1_type, pct in high_profit_stats['b1_distribution'].items():
                lines.append(f"  · {b1_type}: {pct:.1f}%")
            lines.append("")

        # 关键发现
        lines.append("七、关键发现")
        lines.append("-" * 60)

        findings = []

        # 1. 最佳板块
        best_board = max(board_stats.items(), key=lambda x: x[1]['win_rate'])
        findings.append(f"1. 最佳板块为{best_board[1]['board_name']}，胜率{best_board[1]['win_rate']:.1f}%，平均收益{best_board[1]['avg_return']:+.2f}%")

        # 2. 最佳B1条件
        if b1_stats:
            valid_b1 = {k: v for k, v in b1_stats.items() if v['total'] >= 10}
            if valid_b1:
                best_b1 = max(valid_b1.items(), key=lambda x: x[1]['win_rate'])
                findings.append(f"2. 最佳B1条件为【{best_b1[0]}】，触发{best_b1[1]['total']}次，胜率{best_b1[1]['win_rate']:.1f}%")

        # 3. 阳线vs阴线
        red_stats = pattern_stats['red_candle']
        green_stats = pattern_stats['green_candle']
        if red_stats['total'] > 0 and green_stats['total'] > 0:
            findings.append(f"3. 阳线胜率({red_stats['win_rate']:.1f}%) {'高于' if red_stats['win_rate'] > green_stats['win_rate'] else '低于'}阴线胜率({green_stats['win_rate']:.1f}%)")

        # 4. 缩量影响
        shrink_stats = pattern_stats['shrink']
        if shrink_stats['total'] > 0:
            findings.append(f"4. 缩量股票胜率为{shrink_stats['win_rate']:.1f}%（共{shrink_stats['total']}只）")

        # 5. 技术指标相关性
        corr_indicators = [(k, v['correlation']) for k, v in indicator_stats.items() if abs(v['correlation']) > 0.05]
        if corr_indicators:
            best_corr = max(corr_indicators, key=lambda x: abs(x[1]))
            corr_name = indicator_names.get(best_corr[0], best_corr[0])
            findings.append(f"5. {corr_name}与收益率相关性最强({best_corr[1]:+.3f})")

        lines.extend(findings)
        lines.append("")
        lines.append("=" * 60)

        return "\n".join(lines)


# ==================== 主函数 ====================

def main():
    parser = argparse.ArgumentParser(description="Z哥B1战法盈利股票特征分析")
    parser.add_argument('--data-dir', default='./data', help='K线数据目录')
    parser.add_argument('--backtest-dir', default='./backtest_results', help='回测结果目录')
    parser.add_argument('--output', default='feature_analysis_report.txt', help='输出报告文件')
    parser.add_argument('--workers', type=int, default=4, help='并行进程数')

    args = parser.parse_args()

    logger.info("开始分析...")
    logger.info(f"数据目录: {args.data_dir}")
    logger.info(f"回测目录: {args.backtest_dir}")
    logger.info(f"并行进程数: {args.workers}")

    analyzer = FeatureAnalyzer(
        data_dir=Path(args.data_dir),
        backtest_dir=Path(args.backtest_dir),
        workers=args.workers
    )

    # 加载回测结果
    logger.info("加载回测结果...")
    transactions = analyzer.load_backtest_results()

    # 提取特征
    logger.info("提取股票特征...")
    analyzer.extract_all_features_parallel(transactions)

    # 生成报告
    logger.info("生成分析报告...")
    report = analyzer.generate_report()

    # 保存报告
    with open(args.output, 'w', encoding='utf-8') as f:
        f.write(report)

    print(report)
    logger.info(f"报告已保存到: {args.output}")


if __name__ == "__main__":
    main()
