"""
agent/quant_scorer.py
纯代码量价评分器 — 从 OHLCV 数据直接计算评分，替代 Gemini 视觉分析。

评分规则源自 agent/prompt.md，四维加权：
  趋势结构 20% | 价格位置 20% | 量价行为 30% | 前期异动 30%

输出 JSON 格式与 Gemini 完全一致，下游无感知。

用法：
    python -m agent.quant_scorer
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parent.parent

# ── 权重 ────────────────────────────────────────────────────────────────────
WEIGHTS = {
    "trend_structure": 0.20,
    "price_position": 0.20,
    "volume_behavior": 0.30,
    "previous_abnormal_move": 0.30,
}


# =============================================================================
# 工具函数
# =============================================================================

def _sma(series: pd.Series, n: int) -> pd.Series:
    return series.rolling(n, min_periods=1).mean()


def _hhv(series: pd.Series, n: int) -> pd.Series:
    return series.rolling(n, min_periods=1).max()


def _llv(series: pd.Series, n: int) -> pd.Series:
    return series.rolling(n, min_periods=1).min()


def _load_raw(code: str, raw_dir: Path) -> pd.DataFrame:
    csv = raw_dir / f"{code}.csv"
    if not csv.exists():
        return pd.DataFrame()
    df = pd.read_csv(csv)
    df.columns = [c.lower() for c in df.columns]
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date").reset_index(drop=True)


def precompute_score_columns(df: pd.DataFrame) -> pd.DataFrame:
    """预计算所有评分指标列（幂等：已存在则跳过）。"""
    if "ma5" in df.columns:
        return df
    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    df = df.copy()
    df["ma5"] = _sma(close, 5)
    df["ma10"] = _sma(close, 10)
    df["ma20"] = _sma(close, 20)
    df["ma60"] = _sma(close, 60)
    df["hhv60"] = _hhv(high, 60)
    df["hhv120"] = _hhv(high, 120)
    df["llv60"] = _llv(low, 60)
    return df


# =============================================================================
# 维度一：趋势结构
# =============================================================================

def score_trend(df: pd.DataFrame) -> tuple[int, str]:
    """MA 多头排列 + 均线斜率评分。"""
    close = df["close"].astype(float)
    ma5 = df["ma5"]
    ma10 = df["ma10"]
    ma20 = df["ma20"]
    ma60 = df["ma60"]

    # 取最近一个交易日
    c = close.iloc[-1]
    m5, m10, m20, m60 = ma5.iloc[-1], ma10.iloc[-1], ma20.iloc[-1], ma60.iloc[-1]

    # MA5 近5日斜率
    ma5_slope = (ma5.iloc[-1] - ma5.iloc[-6]) / ma5.iloc[-6] if len(df) > 5 else 0

    # close 跌破 MA5 的比例（近10日）
    below_ma5_ratio = (close.iloc[-10:] < ma5.iloc[-10:]).mean() if len(df) >= 10 else 0

    # MA5/MA20 近10日交叉次数
    if len(df) >= 11:
        diff = ma5.iloc[-11:] - ma20.iloc[-11:]
        cross = ((diff.iloc[:-1].values * diff.iloc[1:].values) < 0).sum()
    else:
        cross = 0

    # 多头排列
    full_bull = m5 > m10 > m20 > m60
    partial_bull = m5 > m10 > m20
    bear = m5 < m10 < m20 < m60

    reason_parts = []
    if full_bull:
        reason_parts.append("MA5/MA10/MA20/MA60多头排列")
    elif partial_bull:
        reason_parts.append("MA5/MA10/MA20多头但MA60未跟上")
    elif bear:
        reason_parts.append("空头排列")
    else:
        reason_parts.append("均线纠缠")

    if ma5_slope > 0:
        reason_parts.append("短期均线向上")
    else:
        reason_parts.append("短期均线走平或下行")

    # 评分
    if full_bull and ma5_slope > 0.005:
        score = 4
        if partial_bull and ma5_slope > 0.01:
            score = 5
    elif partial_bull and ma5_slope > 0:
        score = 3
        if below_ma5_ratio > 0.3:
            reason_parts.append("价格频繁跌破短期均线")
    elif cross >= 2:
        score = 2
        reason_parts.append("均线频繁交叉")
    elif bear:
        score = 1
    else:
        score = 2

    return score, "；".join(reason_parts)


# =============================================================================
# 维度二：价格位置
# =============================================================================

def score_position(df: pd.DataFrame) -> tuple[int, str]:
    """价格相对 N 日高点的位置评分。"""
    close = df["close"].astype(float)
    high = df["high"].astype(float)
    c = close.iloc[-1]

    hhv60 = df["hhv60"].iloc[-1]
    hhv120 = df["hhv120"].iloc[-1] if len(df) >= 120 else hhv60
    ma20 = df["ma20"].iloc[-1]

    ratio = c / hhv60 if hhv60 > 0 else 1.0
    dev_ma20 = (c - ma20) / ma20 if ma20 > 0 else 0

    # 前期平台：近20日 high 的中位数
    platform = high.iloc[-30:-5].median() if len(df) >= 30 else hhv60 * 0.8
    breakout = c > platform

    reason_parts = []
    reason_parts.append(f"价格处于60日高点的{ratio:.0%}位置")

    if ratio > 1.0 and dev_ma20 > 0.10:
        score = 1
        reason_parts.append("过热，远离均线")
    elif ratio > 0.95:
        score = 2
        reason_parts.append("接近历史高位，上方空间有限")
    elif ratio > 0.80:
        score = 3
        reason_parts.append("接近前高压力区")
    elif ratio > 0.60:
        score = 4
        reason_parts.append("中位突破区")
        if breakout:
            reason_parts.append("已脱离整理平台")
    else:
        score = 5
        reason_parts.append("中低位，上方空间充足")
        if breakout:
            reason_parts.append("刚突破平台")

    return score, "；".join(reason_parts)


# =============================================================================
# 维度三：量价行为
# =============================================================================

def score_volume(df: pd.DataFrame) -> tuple[int, str]:
    """量价配合评分：上涨放量、回调缩量。"""
    close = df["close"].astype(float)
    open_ = df["open"].astype(float)
    volume = df["volume"].astype(float)

    n = min(len(df), 20)
    recent = df.tail(n)
    is_up = recent["close"].values >= recent["open"].values

    up_vol = volume.iloc[-n:][is_up]
    down_vol = volume.iloc[-n:][~is_up]

    avg_up = up_vol.mean() if len(up_vol) > 0 else 0
    avg_down = down_vol.mean() if len(down_vol) > 0 else 0

    vol_ratio = avg_up / avg_down if avg_down > 0 else 2.0

    # 下跌日最大量 vs 上涨日最大量
    max_up_vol = up_vol.max() if len(up_vol) > 0 else 0
    max_down_vol = down_vol.max() if len(down_vol) > 0 else 0

    # 放量大阴线检测
    avg_vol = volume.iloc[-n:].mean()
    big_down_candles = (
        (close.iloc[-n:].values < open_.iloc[-n:].values)
        & (volume.iloc[-n:].values > avg_vol * 1.5)
    ).sum()

    reason_parts = []

    if vol_ratio > 1.5:
        reason_parts.append("上涨明显放量")
    elif vol_ratio > 1.2:
        reason_parts.append("上涨温和放量")
    elif vol_ratio > 0.8:
        reason_parts.append("量价中性")
    else:
        reason_parts.append("上涨缩量或下跌放量")

    if max_down_vol > max_up_vol:
        reason_parts.append("最大成交量出现在下跌")
    if big_down_candles > 0:
        reason_parts.append(f"存在{big_down_candles}根放量大阴线")

    # 评分
    if vol_ratio < 0.8 and max_down_vol > max_up_vol:
        score = 1
    elif vol_ratio < 0.8:
        score = 2
    elif vol_ratio < 1.2:
        score = 3
    elif vol_ratio < 1.5:
        score = 4
    else:
        score = 5
        if max_down_vol < avg_up and big_down_candles == 0:
            pass  # 保持5分
        elif big_down_candles > 0:
            score = 4

    return score, "；".join(reason_parts)


# =============================================================================
# 维度四：前期异动
# =============================================================================

def score_abnormal(df: pd.DataFrame) -> tuple[int, str]:
    """主力建仓异动评分。"""
    close = df["close"].astype(float)
    open_ = df["open"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    volume = df["volume"].astype(float)

    n = min(len(df), 60)
    recent = df.tail(n)
    avg_vol = volume.iloc[-n:].mean()

    # 找最大量那根K线
    vol_slice = volume.iloc[-n:]
    max_idx = vol_slice.idxmax()
    max_vol = vol_slice[max_idx]
    max_ratio = max_vol / avg_vol if avg_vol > 0 else 1.0

    max_is_up = close.loc[max_idx] >= open_.loc[max_idx]

    # 区间涨幅
    llv60 = df["llv60"].iloc[-1] if len(df) >= n else low.min()
    c = close.iloc[-1]
    gain = (c - llv60) / llv60 if llv60 > 0 else 0

    # 是否突破前高（区间前2/3的高点 vs 当前价）
    if n >= 10:
        prev_high = high.iloc[-n:-n // 3].max()
    else:
        prev_high = df["hhv60"].iloc[-1]
    breakout = c > prev_high

    reason_parts = []

    # 放量大阴线出货
    big_down = (
        (close.iloc[-n:].values < open_.iloc[-n:].values)
        & (volume.iloc[-n:].values > avg_vol * 2)
    ).sum()

    if gain > 1.0:
        reason_parts.append(f"区间涨幅{gain:.0%}，主升浪已完成")
    elif gain > 0.5:
        reason_parts.append(f"区间涨幅{gain:.0%}，涨幅偏大")
    else:
        reason_parts.append(f"区间涨幅{gain:.0%}")

    if max_ratio > 2:
        reason_parts.append(f"最大量是均量的{max_ratio:.1f}倍")
        if max_is_up:
            reason_parts.append("异动为放量阳线")
        else:
            reason_parts.append("异动为放量阴线")

    if big_down > 0:
        reason_parts.append(f"存在{big_down}根放量大阴线")

    # 评分
    if gain > 1.0 or (big_down >= 2 and max_ratio > 2):
        score = 1
    elif gain > 0.5:
        score = 2
    elif max_ratio > 3 and max_is_up and breakout and gain < 0.5:
        score = 5
    elif max_ratio > 2.5 and max_is_up:
        score = 4
    elif max_ratio > 1.5:
        score = 3
    else:
        score = 2

    return score, "；".join(reason_parts)


# =============================================================================
# 汇总评分
# =============================================================================

def score_stock(code: str, df: pd.DataFrame) -> dict:
    """对单只股票计算四维评分，返回与 Gemini 同格式的 JSON dict。"""
    df = precompute_score_columns(df)
    if len(df) < 20:
        return {
            "code": code,
            "trend_reasoning": "数据不足",
            "position_reasoning": "数据不足",
            "volume_reasoning": "数据不足",
            "abnormal_move_reasoning": "数据不足",
            "signal_reasoning": "数据不足",
            "scores": {"trend_structure": 1, "price_position": 1,
                       "volume_behavior": 1, "previous_abnormal_move": 1},
            "total_score": 1.0,
            "signal_type": "distribution_risk",
            "verdict": "FAIL",
            "comment": "数据不足，无法评分",
        }

    t_score, t_reason = score_trend(df)
    p_score, p_reason = score_position(df)
    v_score, v_reason = score_volume(df)
    a_score, a_reason = score_abnormal(df)

    scores = {
        "trend_structure": t_score,
        "price_position": p_score,
        "volume_behavior": v_score,
        "previous_abnormal_move": a_score,
    }

    total = (
        t_score * WEIGHTS["trend_structure"]
        + p_score * WEIGHTS["price_position"]
        + v_score * WEIGHTS["volume_behavior"]
        + a_score * WEIGHTS["previous_abnormal_move"]
    )

    # 信号类型
    if v_score <= 2 or a_score <= 2:
        signal = "distribution_risk"
    elif t_score >= 4 and v_score >= 3:
        signal = "trend_start"
    else:
        signal = "rebound"

    # 判定
    if v_score == 1:
        verdict = "FAIL"
    elif total >= 4.0:
        verdict = "PASS"
    elif total >= 3.2:
        verdict = "WATCH"
    else:
        verdict = "FAIL"

    signal_map = {
        "trend_start": "主升启动",
        "rebound": "跌后反弹",
        "distribution_risk": "出货风险",
    }
    signal_reason = f"信号类型为{signal_map.get(signal, signal)}"

    # comment: 压缩为一句
    parts = []
    if t_score >= 4:
        parts.append("趋势向好")
    elif t_score <= 2:
        parts.append("趋势偏弱")
    if v_score >= 4:
        parts.append("量价配合良好")
    elif v_score <= 2:
        parts.append("量价恶化")
    if a_score >= 4:
        parts.append("有主力建仓痕迹")
    elif a_score <= 2:
        parts.append("无明显异动")
    if p_score >= 4:
        parts.append("位置较低有空间")
    elif p_score <= 2:
        parts.append("位置偏高风险较大")
    comment = "，".join(parts) if parts else "整体中性"

    return {
        "code": code,
        "trend_reasoning": t_reason,
        "position_reasoning": p_reason,
        "volume_reasoning": v_reason,
        "abnormal_move_reasoning": a_reason,
        "signal_reasoning": signal_reason,
        "scores": scores,
        "total_score": round(total, 2),
        "signal_type": signal,
        "verdict": verdict,
        "comment": comment,
    }


# =============================================================================
# 汇总推荐
# =============================================================================

def generate_suggestion(pick_date: str, all_results: list[dict], min_score: float) -> dict:
    passed = [r for r in all_results if r.get("total_score", 0) >= min_score]
    excluded = [r["code"] for r in all_results if r.get("total_score", 0) < min_score]
    passed.sort(key=lambda r: r.get("total_score", 0), reverse=True)

    recommendations = [
        {
            "rank": i + 1,
            "code": r["code"],
            "verdict": r.get("verdict", ""),
            "total_score": r.get("total_score", 0),
            "signal_type": r.get("signal_type", ""),
            "comment": r.get("comment", ""),
        }
        for i, r in enumerate(passed)
    ]

    return {
        "date": pick_date,
        "min_score_threshold": min_score,
        "total_reviewed": len(all_results),
        "recommendations": recommendations,
        "excluded": excluded,
    }


# =============================================================================
# 主入口
# =============================================================================

def main() -> None:
    candidates_file = _ROOT / "data" / "candidates" / "candidates_latest.json"
    raw_dir = _ROOT / "data" / "raw"
    review_dir = _ROOT / "data" / "review"

    if not candidates_file.exists():
        print(f"[ERROR] 找不到 {candidates_file}")
        sys.exit(1)

    with open(candidates_file, encoding="utf-8") as f:
        data = json.load(f)

    pick_date = data.get("pick_date", "")
    candidates = data.get("candidates", [])
    codes = [c["code"] for c in candidates]

    if not codes:
        print("[ERROR] 候选列表为空")
        sys.exit(1)

    print(f"[INFO] 评分方式：纯代码量化  pick_date={pick_date}  候选={len(codes)} 只")

    out_dir = review_dir / pick_date
    out_dir.mkdir(parents=True, exist_ok=True)

    all_results: list[dict] = []

    for i, code in enumerate(codes, 1):
        df = _load_raw(code, raw_dir)
        if df.empty:
            print(f"[{i}/{len(codes)}] {code} — 无数据，跳过")
            continue

        result = score_stock(code, df)

        # 写单股 JSON
        out_file = out_dir / f"{code}.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        all_results.append(result)
        score_str = f"{result['total_score']:.1f}"
        print(f"[{i}/{len(codes)}] {code} — {result['verdict']}  "
              f"score={score_str}  signal={result['signal_type']}")

    # 汇总
    if all_results:
        min_score = 4.0
        suggestion = generate_suggestion(pick_date, all_results, min_score)
        suggestion_file = out_dir / "suggestion.json"
        with open(suggestion_file, "w", encoding="utf-8") as f:
            json.dump(suggestion, f, ensure_ascii=False, indent=2)

        rec_count = len(suggestion["recommendations"])
        print(f"\n[INFO] 评分完成：{len(all_results)} 只  推荐（≥{min_score}）：{rec_count} 只")
        print(f"[INFO] 输出目录：{out_dir}")
    else:
        print("[WARN] 无有效评分结果")


if __name__ == "__main__":
    main()
