"""
Z哥B1战法选股脚本
基于通达信公式实现的独立选股工具

使用方式:
    python zgnb_zk_selector.py --data-dir ./data --date 2026-01-27
    python zgnb_zk_selector.py --data-dir ./data --date 2026-01-27 --tickers "600000,600001"
    python zgnb_zk_selector.py --data-dir ./data --date 2026-01-27 --output results.txt
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# ==================== 日志配置 ====================
# 设置UTF-8编码输出
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("zgnb_zk_selector.log", encoding="utf-8")
    ]
)
logger = logging.getLogger(__name__)

# ==================== 常量定义 ====================
# MA周期参数
M1 = 14
M2 = 28
M3 = 57
M4 = 114

# SHORT/LONG 周期
N1 = 3
N2 = 21

# 振幅计算周期
N = 20
M = 50

# ==================== 技术指标计算函数 ====================

def compute_brick_type(df: pd.DataFrame) -> pd.Series:
    """
    计算砖型图指标
    VAR1A:=(HHV(HIGH,4)-CLOSE)/(HHV(HIGH,4)-LLV(LOW,4))*100-90;
    VAR2A:=SMA(VAR1A,4,1)+100;
    VAR3A:=(CLOSE-LLV(LOW,4))/(HHV(HIGH,4)-LLV(LOW,4))*100;
    VAR4A:=SMA(VAR3A,6,1);
    VAR5A:=SMA(VAR4A,6,1)+100;
    VAR6A:=VAR5A-VAR2A;
    砖型图:=IF(VAR6A>4,VAR6A-4,0),COLORRED;
    """
    high4 = df["high"].rolling(4, min_periods=1).max()
    low4 = df["low"].rolling(4, min_periods=1).min()

    var1a = (high4 - df["close"]) / (high4 - low4 + 1e-9) * 100 - 90

    # SMA(X,N,1) = (X + (N-1)*REF(SMA,1)) / N
    # 处理NaN值：遇到NaN时保持前值
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
    """
    计算RSI指标
    LC:=REF(CLOSE,1);
    TEMP1:=MAX(CLOSE-LC,0);
    TEMP2:=ABS(CLOSE-LC);
    RSI:=SMA(TEMP1,3,1)/SMA(TEMP2,3,1)*100;
    """
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
    """
    计算SHORT和LONG指标
    SHORT :=100*(C-LLV(L,N1))/(HHV(C,N1)-LLV(L,N1))
    LONG :=100*(C-LLV(L,N2))/(HHV(C,N2)-LLV(L,N2))
    """
    low_n1 = df["low"].rolling(N1, min_periods=1).min()
    high_c_n1 = df["close"].rolling(N1, min_periods=1).max()
    short = 100 * (df["close"] - low_n1) / (high_c_n1 - low_n1 + 1e-9)

    low_n2 = df["low"].rolling(N2, min_periods=1).min()
    high_c_n2 = df["close"].rolling(N2, min_periods=1).max()
    long = 100 * (df["close"] - low_n2) / (high_c_n2 - low_n2 + 1e-9)

    return short, long


def compute_trend_white_line(df: pd.DataFrame) -> pd.Series:
    """
    计算趋势白线: EMA(EMA(C,10),10)
    """
    ema1 = df["close"].ewm(span=10, adjust=False).mean()
    ema2 = ema1.ewm(span=10, adjust=False).mean()
    return ema2


def compute_big_brother_yellow_line(df: pd.DataFrame) -> pd.Series:
    """
    计算大哥黄线: (MA14+MA28+MA57+MA114)/4
    """
    ma14 = df["close"].rolling(M1, min_periods=1).mean()
    ma28 = df["close"].rolling(M2, min_periods=1).mean()
    ma57 = df["close"].rolling(M3, min_periods=1).mean()
    ma114 = df["close"].rolling(M4, min_periods=1).mean()
    return (ma14 + ma28 + ma57 + ma114) / 4


def compute_kdj_custom(df: pd.DataFrame, n: int = 9) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """
    计算KDJ指标
    """
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
    """
    计算BBI指标: (MA3+MA6+MA12+MA24)/4
    """
    ma3 = df["close"].rolling(3, min_periods=1).mean()
    ma6 = df["close"].rolling(6, min_periods=1).mean()
    ma12 = df["close"].rolling(12, min_periods=1).mean()
    ma24 = df["close"].rolling(24, min_periods=1).mean()
    return (ma3 + ma6 + ma12 + ma24) / 4


# ==================== 辅助判断函数 ====================

def get_board_type(code: str) -> str:
    """
    根据股票代码判断板块
    """
    if code.startswith("30"):
        return "gem"      # 创业板
    elif code.startswith("68"):
        return "star"     # 科创板
    elif code.startswith("4") or code.startswith("8"):
        return "bj"       # 北交所
    else:
        return "main"     # 主板


def get_amp_range(board_type: str, df: pd.DataFrame, idx: int) -> float:
    """
    获取振幅区间
    创业板/科创板/北交所: 8
    主板: 5
    如果200天内有涨幅>15%: 8
    """
    if board_type in ("gem", "star", "bj"):
        return 8

    # 检查200天内是否有涨幅>15%
    if idx >= 200:
        recent = df.iloc[idx-200:idx]
    else:
        recent = df.iloc[:idx]

    if len(recent) > 0:
        max_gain = ((recent["close"] - recent["close"].shift(1)) / recent["close"].shift(1)).max()
        if pd.notna(max_gain) and max_gain > 0.15:
            return 8

    return 5


def count_condition(series: pd.Series, condition: callable, period: int, idx: int) -> int:
    """
    COUNT函数: 统计满足条件的周期数
    """
    if idx < period:
        end = idx
    else:
        end = period

    count = 0
    for i in range(max(0, idx - period + 1), idx + 1):
        if condition(series.iloc[i]):
            count += 1
    return count


def every_condition(series: pd.Series, condition: callable, period: int, idx: int) -> bool:
    """
    EVERY函数: 判断是否一直满足条件
    """
    if idx < period - 1:
        return False

    for i in range(idx - period + 1, idx + 1):
        if not condition(series.iloc[i]):
            return False
    return True


def exist_condition(series: pd.Series, condition: callable, period: int, idx: int) -> bool:
    """
    EXIST函数: 判断是否存在满足条件
    """
    if idx < period - 1:
        end = idx
    else:
        end = period

    for i in range(max(0, idx - period + 1), idx + 1):
        if condition(series.iloc[i]):
            return True
    return False


def hhv_bars(df: pd.DataFrame, column: str, period: int, idx: int) -> int:
    """
    HHVBARS: 求最高值位置
    """
    if idx < period:
        window = df[column].iloc[:idx+1]
    else:
        window = df[column].iloc[idx-period+1:idx+1]

    max_val = window.max()
    for i in range(len(window)-1, -1, -1):
        if window.iloc[i] == max_val:
            return i
    return 0


# ==================== B1买入条件函数 ====================

def check_chaomai_suoliang_guantou(df: pd.DataFrame, idx: int, code: str) -> bool:
    """
    超卖缩量拐头B:
    做上涨趋势 AND (RSI-15)>=REF(RSI,1) AND (REF(RSI,1)<20 OR REF(J,1)<14)
    AND 当日振幅<(振幅区间+0.5) AND (当日涨跌幅<2.3 OR (上涨十字星 AND 当日涨跌幅<4))
    AND (不是大绿棒 OR 大绿棒离得远) AND (近期异动 OR 远期异动 OR 洗盘异动) AND C>=大哥黄线
    """
    if idx < 10:
        return False

    board_type = get_board_type(code)
    amp_range = get_amp_range(board_type, df, idx)
    relax_coef = 0.9 if board_type in ("gem", "star", "bj") else 1

    # 计算指标
    trend_white = compute_trend_white_line(df)
    yellow_line = compute_big_brother_yellow_line(df)
    rsi = compute_rsi(df)
    _, _, j = compute_kdj_custom(df)
    short, long = compute_short_long(df)

    # 当日数据
    c = df["close"].iloc[idx]
    o = df["open"].iloc[idx]
    h = df["high"].iloc[idx]
    l = df["low"].iloc[idx]
    v = df["volume"].iloc[idx]

    # 做上涨趋势
    uptrend = (trend_white.iloc[idx] >= yellow_line.iloc[idx] * 0.999 and
              (c >= yellow_line.iloc[idx] or (c > yellow_line.iloc[idx] * 0.975 and c > o)))

    # RSI拐头
    rsi_prev = rsi.iloc[idx-1] if idx > 0 else rsi.iloc[idx]
    j_prev = j.iloc[idx-1] if idx > 0 else j.iloc[idx]
    rsi_turn = ((rsi.iloc[idx] - 15) >= rsi_prev) and (rsi_prev < 20 or j_prev < 14)

    # 当日振幅
    day_amp = (h - l) / l * 100
    amp_ok = day_amp < (amp_range + 0.5)

    # 当日涨跌幅
    c_prev = df["close"].iloc[idx-1] if idx > 0 else c
    day_change = abs(c - c_prev) / c_prev * 100 * relax_coef

    # 上涨十字星
    rising_doji = (c > c_prev) and (abs(c - o) / o * 100 * relax_coef) < 1.8

    change_ok = (day_change < 2.3) or (rising_doji and day_change < 4)

    # 大绿棒判断
    vday = hhv_bars(df, "volume", 40, idx)
    vday_close = df["close"].iloc[max(0, idx-vday)]
    vday_close_prev = df["close"].iloc[max(0, idx-vday-1)] if idx-vday-1 >= 0 else vday_close
    vday_open = df["open"].iloc[max(0, idx-vday)]

    not_big_green = (vday_close >= vday_close_prev) or (vday_close >= vday_open)
    big_green_far = (vday >= 15) and (not not_big_green)

    green_ok = not_big_green or big_green_far

    # 异动判断
    low_n = df["low"].rolling(N, min_periods=1).min().iloc[idx]
    high_n = df["high"].rolling(N, min_periods=1).max().iloc[idx]
    recent_amp = (high_n - low_n) / low_n * 100

    low_m = df["low"].rolling(M, min_periods=1).min().iloc[idx]
    high_m = df["high"].rolling(M, min_periods=1).max().iloc[idx]
    far_amp = (high_m - low_m) / low_m * 100

    # 单针下20
    single_needle = (short.iloc[idx] <= 20 and long.iloc[idx] >= 75) or ((long.iloc[idx] - short.iloc[idx]) >= 70)
    single_needle_count = count_condition(short, lambda x: x <= 20, 10, idx) + count_condition(long-short, lambda x: x >= 70, 10, idx)

    wash_move = single_needle_count >= 2

    move_ok = (recent_amp >= 15) or (far_amp >= 30) or wash_move

    # 收盘价>=大哥黄线
    c_above_yellow = c >= yellow_line.iloc[idx]

    return (uptrend and rsi_turn and amp_ok and change_ok and
            green_ok and move_ok and c_above_yellow)


def check_chaomai_suoliang(df: pd.DataFrame, idx: int, code: str) -> bool:
    """
    超卖缩量B:
    做上涨趋势 AND (J<14 OR RSI<23) AND (RSI+J<55 OR J=LLV(J,20))
    AND 当日振幅<振幅区间 AND (当日涨跌幅<2.5 OR 上涨十字星)
    AND (不是大绿棒 OR 大绿棒离得远) AND (缩量 OR (适当缩量 AND 当日涨跌幅<1))
    AND (近期异动 OR 远期异动 OR 洗盘异动)
    """
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

    # 做上涨趋势
    uptrend = (trend_white.iloc[idx] >= yellow_line.iloc[idx] * 0.999 and
              (c >= yellow_line.iloc[idx] or (c > yellow_line.iloc[idx] * 0.975 and c > o)))

    # J或RSI低位
    low_j_rsi = (j.iloc[idx] < 14 or rsi.iloc[idx] < 23)

    # RSI+J条件
    j_low = j.iloc[max(0, idx-20):idx+1].min()
    sum_ok = ((rsi.iloc[idx] + j.iloc[idx]) < 55) or (j.iloc[idx] == j_low)

    # 振幅
    day_amp = (h - l) / l * 100
    amp_ok = day_amp < amp_range

    # 涨跌幅
    day_change = abs(c - c_prev) / c_prev * 100 * relax_coef
    rising_doji = (c > c_prev) and (abs(c - o) / o * 100 * relax_coef) < 1.8
    change_ok = (day_change < 2.5) or rising_doji

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
    vol_shrink = (v < vol_max20 * 0.416) or (v < vol_max50 / 3)

    vol_proper = (v < vol_max20 * 0.618) or (v < vol_max50 / 3)
    vol_ok = vol_shrink or (vol_proper and day_change < 1)

    # 异动
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
    """
    原始B1:
    趋势白线>大哥黄线 AND C>=大哥黄线*0.99 AND 大哥黄线>=REF(大哥黄线,1)
    AND (J<13 OR RSI<21) AND (RSI+J)<LLV(RSI+J,15)*1.5 AND 适当缩量
    AND (不是大绿棒 OR 大绿棒离得远) AND ...
    """
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

    # 基础条件
    base_ok = (trend_white.iloc[idx] > yellow_line.iloc[idx] and
               c >= yellow_line.iloc[idx] * 0.99 and
               yellow_line.iloc[idx] >= yellow_line.iloc[idx-1] * 0.999)

    # J或RSI低位
    low_j_rsi = (j.iloc[idx] < 13 or rsi.iloc[idx] < 21)

    # RSI+J条件
    rsi_j_sum = rsi.iloc[idx] + j.iloc[idx]
    rsi_j_min = (rsi.iloc[max(0, idx-15):idx+1] + j.iloc[max(0, idx-15):idx+1]).min()
    sum_ok = rsi_j_sum < rsi_j_min * 1.5

    # 适当缩量
    vol_max20 = df["volume"].iloc[max(0, idx-20):idx+1].max()
    vol_max50 = df["volume"].iloc[max(0, idx-50):idx+1].max()
    vol_proper = (v < vol_max20 * 0.618) or (v < vol_max50 / 3)

    # 大绿棒
    vday = hhv_bars(df, "volume", 40, idx)
    vday_close = df["close"].iloc[max(0, idx-vday)]
    vday_close_prev = df["close"].iloc[max(0, idx-vday-1)] if idx-vday-1 >= 0 else vday_close
    vday_open = df["open"].iloc[max(0, idx-vday)]
    not_big_green = (vday_close >= vday_close_prev) or (vday_close >= vday_open)
    big_green_far = (vday >= 15) and (not not_big_green)
    green_ok = not_big_green or big_green_far

    # 十字星或超缩量
    body_small = (abs(c - o) * 100 / o) < 1.5
    vol_super_shrink = (v < vol_max20 / 4) or (v < vol_max50 / 6)
    vol_llv = df["volume"].iloc[max(0, idx-20):idx+1].min()
    vol_proper_llv = (vol_proper and v < vol_llv * 1.1 and j.iloc[idx] == j.iloc[max(0, idx-20):idx+1].min())

    # 距离条件
    dist_white = abs(c - trend_white.iloc[idx]) / c * 100
    dist_bbi = abs(c - bbi.iloc[idx]) / c * 100
    dist_yellow = abs(c - yellow_line.iloc[idx]) / yellow_line.iloc[idx] * 100
    dist_ok = (vol_proper and (dist_white < 1.8 or dist_bbi < 1.5 or dist_yellow < 2.8))

    body_ok = body_small or vol_super_shrink or vol_proper_llv or dist_ok

    # 异动
    low_n = df["low"].rolling(N, min_periods=1).min().iloc[idx]
    high_n = df["high"].rolling(N, min_periods=1).max().iloc[idx]
    recent_amp = (high_n - low_n) / low_n * 100

    low_m = df["low"].rolling(M, min_periods=1).min().iloc[idx]
    high_m = df["high"].rolling(M, min_periods=1).max().iloc[idx]
    far_amp = (high_m - low_m) / low_m * 100

    move_ok = (recent_amp >= 15) or (far_amp >= 30)

    return base_ok and low_j_rsi and sum_ok and vol_proper and green_ok and body_ok and move_ok


def check_chaomai_chaosuoliang(df: pd.DataFrame, idx: int, code: str) -> bool:
    """
    超卖超缩量B
    """
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

    # 做上涨趋势
    uptrend = (trend_white.iloc[idx] >= yellow_line.iloc[idx] * 0.999 and
              (c >= yellow_line.iloc[idx] or (c > yellow_line.iloc[idx] * 0.975 and c > o)))

    # J或RSI低位
    low_j_rsi = (j.iloc[idx] < 14 or rsi.iloc[idx] < 23)

    # RSI+J条件
    sum_ok = (rsi.iloc[idx] + j.iloc[idx]) < 60

    # 远期振幅
    low_m = df["low"].rolling(M, min_periods=1).min().iloc[idx]
    high_m = df["high"].rolling(M, min_periods=1).max().iloc[idx]
    far_amp = (high_m - low_m) / low_m * 100
    far_amp_ok = far_amp >= 45

    # 近期振幅
    low_n = df["low"].rolling(N, min_periods=1).min().iloc[idx]
    high_n = df["high"].rolling(N, min_periods=1).max().iloc[idx]
    recent_amp = (high_n - low_n) / low_n * 100

    super_move = recent_amp >= 60

    day_amp = (h - l) / l * 100
    amp_ok = (day_amp < amp_range) or (super_move and day_amp < amp_range + 3.2 and c > o and c >= trend_white.iloc[idx])

    # 成交量和收盘
    v_prev = df["volume"].iloc[idx-1] if idx > 0 else v
    vol_c_ok = ((c < o and v < v_prev and c >= yellow_line.iloc[idx]) or (c >= o))

    # 涨跌幅
    day_change = abs(c - c_prev) / c_prev * 100 * relax_coef
    rising_doji = (c > c_prev) and (abs(c - o) / o * 100 * relax_coef) < 1.8
    change_ok = (day_change < 2) or rising_doji

    # 大绿棒
    vday = hhv_bars(df, "volume", 40, idx)
    vday_close = df["close"].iloc[max(0, idx-vday)]
    vday_close_prev = df["close"].iloc[max(0, idx-vday-1)] if idx-vday-1 >= 0 else vday_close
    vday_open = df["open"].iloc[max(0, idx-vday)]
    not_big_green = (vday_close >= vday_close_prev) or (vday_close >= vday_open)
    big_green_far = (vday >= 15) and (not not_big_green)
    green_ok = not_big_green or big_green_far

    # 超缩量
    vol_max30 = df["volume"].iloc[max(0, idx-30):idx+1].max()
    vol_max50 = df["volume"].iloc[max(0, idx-50):idx+1].max()
    vol_super_shrink = (v < vol_max30 / 4) or (v < vol_max50 / 6)

    # 异动
    move_ok = (recent_amp >= 15) or (far_amp >= 30)

    return (uptrend and low_j_rsi and sum_ok and far_amp_ok and amp_ok and
            vol_c_ok and change_ok and green_ok and vol_super_shrink and move_ok)


def check_huicai_baixian(df: pd.DataFrame, idx: int, code: str) -> bool:
    """
    回踩白线B
    """
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

    # 强趋势股
    yellow_rising = every_condition(yellow_line, lambda x: x >= 0, 13, idx) or True
    yellow_rising = yellow_line.iloc[max(0, idx-13):idx+1].min() >= yellow_line.iloc[max(0, idx-14):idx].min() * 0.999

    white_rising = trend_white.iloc[idx] >= trend_white.iloc[idx-1]
    white_above = every_condition(trend_white, lambda x: x > 0, 20, idx)
    white_above = (trend_white.iloc[max(0, idx-20):idx+1] > yellow_line.iloc[max(0, idx-20):idx+1]).all()

    white_always_rising = every_condition(trend_white, lambda x: x >= 0, 11, idx)
    white_always_rising = trend_white.iloc[max(0, idx-11):idx+1].min() >= trend_white.iloc[max(0, idx-12):idx].min()

    # 红肥绿瘦
    red_fat = count_condition(df["close"], lambda x: x >= 0, 15, idx) > 7
    green_thin = count_condition(df["close"], lambda x: x > 0, 11, idx) > 5

    strong_trend = (yellow_rising and white_rising and white_above and
                    white_always_rising and (red_fat or green_thin))

    # J或RSI或洗盘
    single_needle = (short.iloc[idx] <= 20 and long.iloc[idx] >= 75) or ((long.iloc[idx] - short.iloc[idx]) >= 70)

    low_j_rsi = (j.iloc[idx] < 30 or rsi.iloc[idx] < 40 or single_needle)
    sum_ok = (rsi.iloc[idx] + j.iloc[idx]) < 70

    # 振幅
    day_amp = (h - l) / l * 100
    dist_white = abs(c - trend_white.iloc[idx]) / c * 100
    dist_bbi = abs(c - bbi.iloc[idx]) / c * 100
    amp_ok = (day_amp < amp_range + 0.5) or (dist_white < 1) or (dist_bbi < 1)

    # 回踩白线
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

    # 回踩缩量
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

    # 最低价<=前收盘
    l_ok = l <= c_prev

    return (strong_trend and low_j_rsi and sum_ok and amp_ok and white_ok and
            change_ok and green_ok and vol_shrink and move_ok and l_ok)


def check_huicai_chaoji(df: pd.DataFrame, idx: int, code: str) -> bool:
    """
    回踩超级B
    """
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

    # 超牛股
    bbi_rising = every_condition(bbi, lambda x: x >= 0, 20, idx)
    bbi_rising = bbi.iloc[max(0, idx-20):idx+1].min() >= bbi.iloc[max(0, idx-21):idx].min() * 0.999
    bbi_count = count_condition(bbi, lambda x: x >= 0, 25, idx)
    bbi_ok = bbi_rising or bbi_count >= 23

    low_n = df["low"].rolling(N, min_periods=1).min().iloc[idx]
    high_n = df["high"].rolling(N, min_periods=1).max().iloc[idx]
    recent_amp = (high_n - low_n) / low_n * 100

    low_m = df["low"].rolling(M, min_periods=1).min().iloc[idx]
    high_m = df["high"].rolling(M, min_periods=1).max().iloc[idx]
    far_amp = (high_m - low_m) / low_m * 100

    # 金叉位置
    cross_found = False
    cross_pos = 0
    for i in range(idx, max(0, idx-60), -1):
        if i > 0 and df["close"].iloc[i] >= yellow_line.iloc[i] and df["close"].iloc[i-1] < yellow_line.iloc[i-1]:
            cross_found = True
            cross_pos = i
            break

    super_bull = bbi_ok and ((recent_amp >= 30) or (far_amp > 80)) and (idx - cross_pos > 12)

    # J或RSI或洗盘
    single_needle = (short.iloc[idx] <= 20 and long.iloc[idx] >= 75) or ((long.iloc[idx] - short.iloc[idx]) >= 70)
    low_j_rsi = (j.iloc[idx] < 35 or rsi.iloc[idx] < 45 or single_needle)

    # RSI+J条件
    rsi_j_sum = rsi.iloc[idx] + j.iloc[idx]
    rsi_j_min = (rsi.iloc[max(0, idx-25):idx+1] + j.iloc[max(0, idx-25):idx+1]).min()
    sum_ok = rsi_j_sum == rsi_j_min

    # 振幅
    day_amp = (h - l) / l * 100
    dist_white = abs(c - trend_white.iloc[idx]) / c * 100
    amp_ok = day_amp < amp_range + 1

    # 涨跌幅
    day_change = abs(c - c_prev) / c_prev * 100 * relax_coef
    change_ok = (day_change < 2.5) or (dist_white < 2)

    # 强势回踩不破
    l_dist_white = abs(l - trend_white.iloc[idx]) / trend_white.iloc[idx] * 100
    l_dist_bbi = abs(l - bbi.iloc[idx]) / bbi.iloc[idx] * 100
    strong_touch = ((l_dist_white < 1 or l_dist_bbi < 0.5) and
                     (c > trend_white.iloc[idx]) and (dist_white <= 3.5))

    # 大绿棒
    vday = hhv_bars(df, "volume", 40, idx)
    vday_close = df["close"].iloc[max(0, idx-vday)]
    vday_close_prev = df["close"].iloc[max(0, idx-vday-1)] if idx-vday-1 >= 0 else vday_close
    vday_open = df["open"].iloc[max(0, idx-vday)]
    not_big_green = (vday_close >= vday_close_prev) or (vday_close >= vday_open)
    big_green_far = (vday >= 15) and (not not_big_green)
    green_ok = not_big_green or big_green_far

    # 适当缩量
    vol_max20 = df["volume"].iloc[max(0, idx-20):idx+1].max()
    vol_max50 = df["volume"].iloc[max(0, idx-50):idx+1].max()
    vol_proper = (v < vol_max20 * 0.618) or (v < vol_max50 / 3)

    # 异动
    move_ok = (recent_amp >= 15) or (far_amp >= 30)

    return (super_bull and low_j_rsi and sum_ok and amp_ok and change_ok and
            strong_touch and green_ok and move_ok and vol_proper)


def check_huicai_huangxian(df: pd.DataFrame, idx: int, code: str) -> bool:
    """
    回踩黄线B
    """
    if idx < 120:
        return False

    trend_white = compute_trend_white_line(df)
    yellow_line = compute_big_brother_yellow_line(df)
    rsi = compute_rsi(df)
    _, _, j = compute_kdj_custom(df)

    c = df["close"].iloc[idx]
    o = df["open"].iloc[idx]
    h = df["high"].iloc[idx]
    l = df["low"].iloc[idx]
    v = df["volume"].iloc[idx]
    c_prev = df["close"].iloc[idx-1] if idx > 0 else c

    # 趋势白线>=大哥黄线
    white_above_yellow = trend_white.iloc[idx] >= yellow_line.iloc[idx]

    # C>=大哥黄线*0.975
    c_above_yellow = c >= yellow_line.iloc[idx] * 0.975

    # J<13 OR RSI<18
    low_j_rsi = (j.iloc[idx] < 13 or rsi.iloc[idx] < 18)

    # 回踩黄线
    dist_yellow = abs(c - yellow_line.iloc[idx]) / yellow_line.iloc[idx] * 100
    touch_yellow = ((c >= yellow_line.iloc[idx] and dist_yellow <= 1.5) or
                    (c >= yellow_line.iloc[idx] and dist_yellow <= 2 and
                     abs(c - c_prev) / c_prev * 100 < 1) or
                    (c < yellow_line.iloc[idx] and dist_yellow <= 0.8))

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
    vol_shrink = (v < vol_max20 * 0.416) or (v < vol_max50 / 3)

    vol_proper = (v < vol_max20 * 0.618) or (v < vol_max50 / 3)

    j_low = j.iloc[idx] == j.iloc[max(0, idx-20):idx+1].min()
    rsi_low = rsi.iloc[idx] == rsi.iloc[max(0, idx-14):idx+1].min()

    vol_ok = vol_shrink or (vol_proper and (j_low or rsi_low))

    # 大哥黄线上升
    yellow_rising = yellow_line.iloc[idx] >= yellow_line.iloc[idx-1] * 0.997

    # MA60上升
    ma60 = df["close"].rolling(60, min_periods=1).mean()
    ma60_rising = ma60.iloc[idx] >= ma60.iloc[idx-1]

    # 振幅
    low_n = df["low"].rolling(N, min_periods=1).min().iloc[idx]
    high_n = df["high"].rolling(N, min_periods=1).max().iloc[idx]
    recent_amp = (high_n - low_n) / low_n * 100

    low_m = df["low"].rolling(M, min_periods=1).min().iloc[idx]
    high_m = df["high"].rolling(M, min_periods=1).max().iloc[idx]
    far_amp = (high_m - low_m) / low_m * 100

    amp_ok = recent_amp >= 11.9 and far_amp >= 19.5

    return (white_above_yellow and c_above_yellow and low_j_rsi and
            touch_yellow and green_ok and vol_ok and yellow_rising and
            ma60_rising and amp_ok)


def check_any_b1(df: pd.DataFrame, idx: int, code: str) -> bool:
    """
    检查是否满足任一B1买入条件
    """
    try:
        return (check_chaomai_suoliang_guantou(df, idx, code) or
                check_chaomai_suoliang(df, idx, code) or
                check_yuanshi_b1(df, idx, code) or
                check_chaomai_chaosuoliang(df, idx, code) or
                check_huicai_baixian(df, idx, code) or
                check_huicai_chaoji(df, idx, code) or
                check_huicai_huangxian(df, idx, code))
    except Exception as e:
        logger.debug(f"股票 {code} B1条件检查出错: {e}")
        return False


# ==================== 共振条件函数 ====================

def check_strong_red(df: pd.DataFrame, idx: int) -> bool:
    """
    强红判定
    今红 AND 昨绿 AND 比值>0.666
    """
    if idx < 2:
        return False

    brick = compute_brick_type(df)

    today_red = brick.iloc[idx] > brick.iloc[idx-1]
    yesterday_green = brick.iloc[idx-1] <= brick.iloc[idx-2]

    if not (today_red and yesterday_green):
        return False

    red_length = brick.iloc[idx] - brick.iloc[idx-1]
    green_length = brick.iloc[idx-2] - brick.iloc[idx-1]

    ratio = red_length / green_length if green_length > 0 else 0

    return ratio > 0.666


def check_momentum(df: pd.DataFrame, idx: int) -> Tuple[bool, float, float]:
    """
    动能指标
    返回: (是否满足, 黄柱值, X动能值)
    """
    if idx < 2:
        return False, 0, 0

    rsi = compute_rsi(df)
    _, _, j = compute_kdj_custom(df)

    n1 = j.iloc[idx] - j.iloc[idx-1]
    n2 = rsi.iloc[idx] - rsi.iloc[idx-1]

    c = df["close"].iloc[idx]
    o = df["open"].iloc[idx]
    h = df["high"].iloc[idx]
    l = df["low"].iloc[idx]
    v = df["volume"].iloc[idx]
    c_prev = df["close"].iloc[idx-1]
    v_prev = df["volume"].iloc[idx-1]

    # 成交量系数
    vol_coef = 1
    if v < v_prev * 0.99:
        vol_coef = (1 - 5 * (v_prev - v) / v_prev) * 0.8

    # 倍量系数
    mult_coef = 1
    if v / v_prev >= 4:
        mult_coef = 1.4
    else:
        mult_coef = 0.1 * v / v_prev + 1

    # 倍量系数加成
    mult_add = 1
    if c > o and c > c_prev and v > v_prev * 1.8:
        mult_add = mult_coef

    # 影线系数
    shadow_coef = 1
    if c > c_prev and c > o:
        shadow_coef = (0.75 - (h - c) / (h - min(o, c_prev))) * 1.3

    # 黄柱
    yellow_pillar = (n1 + n2) / 2 * shadow_coef * mult_add

    # X动能
    x_momentum = 0
    if c > o and c > c_prev and (n1 + n2) > ((j.iloc[idx-1] - j.iloc[idx-2]) + (rsi.iloc[idx-1] - rsi.iloc[idx-2])):
        x_momentum = ((n1 + n2) - ((j.iloc[idx-1] - j.iloc[idx-2]) + (rsi.iloc[idx-1] - rsi.iloc[idx-2]))) / 2 * shadow_coef * vol_coef * mult_add

    return (yellow_pillar >= 10 or x_momentum >= 10), yellow_pillar, x_momentum


def check_upper_shadow(df: pd.DataFrame, idx: int) -> bool:
    """
    上影线条件
    (C>=O OR C>REF(C,1)) AND (1-(H-C)/(H-MIN(L,REF(C,1))))>0.618
    """
    if idx < 1:
        return False

    c = df["close"].iloc[idx]
    o = df["open"].iloc[idx]
    h = df["high"].iloc[idx]
    l = df["low"].iloc[idx]
    c_prev = df["close"].iloc[idx-1]

    body_up = (c >= o) or (c > c_prev)

    shadow_ratio = 1 - (h - c) / (h - min(l, c_prev) + 1e-9)

    return body_up and shadow_ratio > 0.618


def check_trend_condition(df: pd.DataFrame, idx: int) -> bool:
    """
    趋势条件
    趋势白线>=大哥黄线*0.995 AND 大哥黄线>=REF(大哥黄线,1)*0.997 AND C>=大哥黄线*0.997
    """
    if idx < 1:
        return False

    trend_white = compute_trend_white_line(df)
    yellow_line = compute_big_brother_yellow_line(df)
    c = df["close"].iloc[idx]

    return (trend_white.iloc[idx] >= yellow_line.iloc[idx] * 0.995 and
            yellow_line.iloc[idx] >= yellow_line.iloc[idx-1] * 0.997 and
            c >= yellow_line.iloc[idx] * 0.997)


def check_turnover_condition(df: pd.DataFrame, idx: int) -> bool:
    """
    换手条件
    通达信公式：换手条件:=DYNAINFO(37)>=0.0099;
    DYNAINFO(37)是换手率，0.0099=0.99%是一个非常低的门槛
    由于缺少流通股本数据，这里简化处理：
    1. 成交量不为0
    2. 或者成交量相对昨日有所放大
    """
    if idx < 1:
        return False

    v = df["volume"].iloc[idx]
    v_prev = df["volume"].iloc[idx-1]

    # 基本条件：有成交
    if v > 0:
        return True

    # 或者相比昨日没有大幅萎缩（避免停牌或异常情况）
    if v_prev > 0 and v >= v_prev * 0.5:
        return True

    return False


def check_resonance_buy(df: pd.DataFrame, idx: int, code: str) -> bool:
    """
    综合共振买入条件
    """
    # MA114需要至少114个数据点
    if idx < 114:
        return False

    # 强红
    if not check_strong_red(df, idx):
        return False

    # 动能
    momentum_ok, yellow_pillar, x_momentum = check_momentum(df, idx)
    if not momentum_ok:
        return False

    # 判断共振条件1或2
    short, long = compute_short_long(df)

    # 检查2日内是否存在B1
    b1_exist = False
    for i in range(max(0, idx-1), idx+1):
        if check_any_b1(df, i, code):
            b1_exist = True
            break

    condition1 = b1_exist or (long.iloc[idx-1] > 85 and short.iloc[idx-1] < 30)

    # 共振条件2
    long_short_diff = long.iloc[idx] - short.iloc[idx]
    condition2_part1 = (long_short_diff > 60 and long.iloc[idx] > 98 and short.iloc[idx] > 98)

    trend_white = compute_trend_white_line(df)
    condition2_part2 = yellow_pillar > 20 and df["close"].iloc[idx] > trend_white.iloc[idx]

    brick = compute_brick_type(df)
    length = brick.iloc[idx] - brick.iloc[idx-1]
    condition2_part3 = yellow_pillar > 30 or (yellow_pillar + length) > 50 or x_momentum > 40

    condition2 = condition2_part1 or condition2_part2 or condition2_part3

    if not (condition1 or condition2):
        return False

    # 上影线条件
    if not check_upper_shadow(df, idx):
        return False

    # 趋势条件
    if not check_trend_condition(df, idx):
        return False

    # 换手条件
    if not check_turnover_condition(df, idx):
        return False

    return True


# ==================== 主选股类 ====================

class ZGNBZKSelector:
    """Z哥B1战法选股器"""

    def __init__(self, data_dir: Path, min_market_cap: float = 50):
        """
        初始化选股器

        Parameters
        ----------
        data_dir : Path
            CSV数据目录
        min_market_cap : float, default 50
            最小市值（亿元），用于过滤
        """
        self.data_dir = Path(data_dir)
        self.min_market_cap = min_market_cap

    def load_data(self, codes: List[str] = None) -> Dict[str, pd.DataFrame]:
        """
        加载CSV数据

        Parameters
        ----------
        codes : List[str], optional
            指定股票代码列表，None表示加载全部

        Returns
        -------
        Dict[str, pd.DataFrame]
            股票代码到K线数据的映射
        """
        data = {}

        if codes is None:
            # 加载所有CSV文件
            csv_files = list(self.data_dir.glob("*.csv"))
            logger.info(f"发现 {len(csv_files)} 个数据文件")

            for csv_file in csv_files:
                code = csv_file.stem
                try:
                    df = pd.read_csv(csv_file)
                    df["date"] = pd.to_datetime(df["date"])
                    df = df.sort_values("date").reset_index(drop=True)

                    if len(df) >= 114:  # 至少需要114天数据（MA114）
                        data[code] = df
                except Exception as e:
                    logger.warning(f"加载 {code} 数据失败: {e}")
        else:
            # 加载指定股票
            for code in codes:
                csv_file = self.data_dir / f"{code}.csv"
                if csv_file.exists():
                    try:
                        df = pd.read_csv(csv_file)
                        df["date"] = pd.to_datetime(df["date"])
                        df = df.sort_values("date").reset_index(drop=True)

                        if len(df) >= 120:
                            data[code] = df
                    except Exception as e:
                        logger.warning(f"加载 {code} 数据失败: {e}")
                else:
                    logger.warning(f"股票 {code} 数据文件不存在")

        logger.info(f"成功加载 {len(data)} 只股票数据")
        return data

    def select_stock(self, code: str, df: pd.DataFrame, trade_date: pd.Timestamp) -> bool:
        """
        判断单只股票是否符合选股条件

        Parameters
        ----------
        code : str
            股票代码
        df : pd.DataFrame
            K线数据
        trade_date : pd.Timestamp
            交易日期

        Returns
        -------
        bool
            是否满足选股条件
        """
        # 过滤日期
        hist = df[df["date"] <= trade_date].copy()

        # MA114需要至少114个数据点
        if len(hist) < 114:
            return False

        idx = len(hist) - 1

        try:
            return check_resonance_buy(hist, idx, code)
        except Exception as e:
            logger.debug(f"股票 {code} 选股检查出错: {e}")
            return False

    def run(self, date: pd.Timestamp, codes: List[str] = None) -> List[str]:
        """
        执行选股

        Parameters
        ----------
        date : pd.Timestamp
            选股日期
        codes : List[str], optional
            指定股票池，None表示全部

        Returns
        -------
        List[str]
            符合条件的股票列表
        """
        logger.info(f"开始选股，日期: {date.strftime('%Y-%m-%d')}")

        data = self.load_data(codes)

        if not data:
            logger.warning("没有可用的股票数据")
            return []

        results = []
        for code, df in data.items():
            if self.select_stock(code, df, date):
                results.append(code)
                logger.info(f"符合条件: {code}")

        logger.info(f"选股完成，检测 {len(data)} 只股票，符合条件 {len(results)} 只")
        return results


# ==================== 命令行入口 ====================

def main():
    parser = argparse.ArgumentParser(description="Z哥B1战法选股")
    parser.add_argument("--data-dir", default="./data", help="CSV数据目录")
    parser.add_argument("--date", help="交易日 YYYY-MM-DD，默认为最后一个交易日")
    parser.add_argument("--tickers", default="all", help="股票代码，逗号分隔，all表示全部")
    parser.add_argument("--output", help="输出文件路径，默认为zgnb_zk_results.log")
    parser.add_argument("--no-log", action="store_true", help="不保存到日志文件")

    args = parser.parse_args()

    # 解析股票代码
    codes = None
    if args.tickers.lower() != "all":
        codes = [c.strip() for c in args.tickers.split(",")]

    # 解析日期
    if args.date:
        trade_date = pd.to_datetime(args.date)
    else:
        trade_date = pd.Timestamp.now()

    # 执行选股
    selector = ZGNBZKSelector(data_dir=Path(args.data_dir))
    results = selector.run(trade_date, codes)

    # 输出结果
    output_lines = [
        "=" * 40,
        "Z哥B1战法选股结果",
        "=" * 40,
        f"交易日: {trade_date.strftime('%Y-%m-%d')}",
        f"数据目录: {args.data_dir}",
        f"检测股票数: {len(selector.load_data(codes))}",
        f"符合条件: {len(results)}",
        "",
        "符合条件的股票:",
        ", ".join(results) if results else "无",
        "=" * 40,
    ]

    output_text = "\n".join(output_lines)
    print(output_text)

    # 确定输出文件路径
    if args.output:
        output_file = args.output
    else:
        output_file = "zgnb_zk_results.log"

    # 写入文件（除非指定--no-log）
    if not args.no_log:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(output_text)
        logger.info(f"结果已保存到: {output_file}")


if __name__ == "__main__":
    main()
