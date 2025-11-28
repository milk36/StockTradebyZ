from __future__ import annotations

import argparse
import datetime as dt
import logging
import random
import sys
import time
import threading
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Optional
import os

import pandas as pd
import tushare as ts
from tqdm import tqdm

warnings.filterwarnings("ignore")

# --------------------------- 全局日志配置 --------------------------- #
LOG_FILE = Path("fetch.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8"),
    ],
)
logger = logging.getLogger("fetch_from_stocklist")

# --------------------------- 限流/封禁处理配置 --------------------------- #
COOLDOWN_SECS = 600
BAN_PATTERNS = (
    "访问频繁", "请稍后", "超过频率", "频繁访问",
    "too many requests", "429",
    "forbidden", "403",
    "max retries exceeded"
)

# Tushare接口限速配置：每分钟最多50次
# 采用更保守的策略，实际限制为每分钟40次，避免边界情况
MAX_REQUESTS_PER_MINUTE = 40
REQUEST_INTERVAL = 60.0 / MAX_REQUESTS_PER_MINUTE  # 1.5秒/次

# 全局限速器
class RateLimiter:
    def __init__(self, interval: float):
        self.interval = interval
        self.last_request_time = 0
        self.lock = threading.Lock()
        self.request_count = 0
        self.window_start = time.time()

    def wait_if_needed(self):
        """等待以确保不超过限速"""
        with self.lock:
            current_time = time.time()

            # 检查是否需要重置时间窗口（每分钟重置）
            if current_time - self.window_start >= 60:
                self.request_count = 0
                self.window_start = current_time
                logger.debug(f"限速器时间窗口重置，请求计数清零")

            # 如果已达到每分钟最大请求数，等待到下一分钟
            if self.request_count >= MAX_REQUESTS_PER_MINUTE:
                wait_time = 60 - (current_time - self.window_start) + 1  # 加1秒安全边际
                logger.warning(f"已达到每分钟最大请求数({MAX_REQUESTS_PER_MINUTE})，等待{wait_time:.0f}秒...")
                time.sleep(wait_time)
                self.request_count = 0
                self.window_start = time.time()
                current_time = self.window_start

            # 基本的间隔控制
            time_since_last = current_time - self.last_request_time
            if time_since_last < self.interval:
                sleep_time = self.interval - time_since_last
                logger.debug(f"限速等待: {sleep_time:.2f}秒")
                time.sleep(sleep_time)

            self.last_request_time = time.time()
            self.request_count += 1
            logger.debug(f"API请求 #{self.request_count} (窗口内)")

# 全局限速器实例（将在main函数中初始化）
rate_limiter = None

def _looks_like_ip_ban(exc: Exception) -> bool:
    msg = (str(exc) or "").lower()
    return any(pat in msg for pat in BAN_PATTERNS)

class RateLimitError(RuntimeError):
    """表示命中限流/封禁，需要长时间冷却后重试。"""
    pass

def _cool_sleep(base_seconds: int) -> None:
    jitter = random.uniform(0.9, 1.2)
    sleep_s = max(1, int(base_seconds * jitter))
    logger.warning("疑似被限流/封禁，进入冷却期 %d 秒...", sleep_s)
    time.sleep(sleep_s)

# --------------------------- 历史K线（Tushare 日线，固定qfq） --------------------------- #
pro: Optional[ts.pro_api] = None  # 模块级会话

def set_api(session) -> None:
    """由外部(比如GUI)注入已创建好的 ts.pro_api() 会话"""
    global pro
    pro = session
    

def _to_ts_code(code: str) -> str:
    """把6位code映射到标准 ts_code 后缀。"""
    code = str(code).zfill(6)
    if code.startswith(("60", "68", "9")):
        return f"{code}.SH"
    elif code.startswith(("4", "8")):
        return f"{code}.BJ"
    else:
        return f"{code}.SZ"

def _get_kline_tushare(code: str, start: str, end: str) -> pd.DataFrame:
    # 限速等待（如果启用了限速）
    if rate_limiter is not None:
        rate_limiter.wait_if_needed()

    ts_code = _to_ts_code(code)
    try:
        df = ts.pro_bar(
            ts_code=ts_code,
            adj="qfq",
            start_date=start,
            end_date=end,
            freq="D",
            api=pro
        )
    except Exception as e:
        if _looks_like_ip_ban(e):
            raise RateLimitError(str(e)) from e
        raise

    if df is None or df.empty:
        return pd.DataFrame()

    df = df.rename(columns={"trade_date": "date", "vol": "volume"})[
        ["date", "open", "close", "high", "low", "volume"]
    ].copy()
    df["date"] = pd.to_datetime(df["date"])
    for c in ["open", "close", "high", "low", "volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.sort_values("date").reset_index(drop=True)

def validate(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    df = df.drop_duplicates(subset="date").sort_values("date").reset_index(drop=True)
    if df["date"].isna().any():
        raise ValueError("存在缺失日期！")
    if (df["date"] > pd.Timestamp.today()).any():
        raise ValueError("数据包含未来日期，可能抓取错误！")
    return df

# --------------------------- 读取 stocklist.csv & 过滤板块 --------------------------- #

def _filter_by_boards_stocklist(df: pd.DataFrame, exclude_boards: set[str]) -> pd.DataFrame:
    """
    exclude_boards 子集：{'gem','star','bj'}
    - gem  : 创业板 300/301（.SZ）
    - star : 科创板 688（.SH）
    - bj   : 北交所（.BJ 或 4/8 开头）
    """
    code = df["symbol"].astype(str)
    ts_code = df["ts_code"].astype(str).str.upper()
    mask = pd.Series(True, index=df.index)

    if "gem" in exclude_boards:
        mask &= ~code.str.startswith(("300", "301"))
    if "star" in exclude_boards:
        mask &= ~code.str.startswith(("688",))
    if "bj" in exclude_boards:
        mask &= ~(ts_code.str.endswith(".BJ") | code.str.startswith(("4", "8")))

    return df[mask].copy()

def _add_market_cap_info(df: pd.DataFrame) -> pd.DataFrame:
    """
    获取股票市值信息的替代方案
    由于Tushare接口权限限制，这里提供几种备选方案：
    1. 从本地市值数据文件读取
    2. 使用模拟数据进行演示
    3. 跳过市值筛选（不推荐）
    """
    logger.info("正在获取股票市值信息...")

    # 方案1：尝试从本地市值数据文件读取
    market_cap_file = Path("market_cap.csv")
    if market_cap_file.exists():
        try:
            market_df = pd.read_csv(market_cap_file)
            if 'symbol' in market_df.columns and 'market_cap' in market_df.columns:
                result_df = df.merge(market_df[['symbol', 'market_cap']], on='symbol', how='left')
                missing_count = result_df['market_cap'].isna().sum()
                if missing_count > 0:
                    logger.warning(f"有{missing_count}只股票在市值文件中找不到数据")
                    result_df['market_cap'] = result_df['market_cap'].fillna(0)
                logger.info(f"从本地文件成功获取{len(result_df) - missing_count}/{len(df)}只股票的市值信息")
                return result_df
        except Exception as e:
            logger.warning(f"读取本地市值文件失败：{e}")

    # 方案2：使用模拟数据（演示用）
    logger.warning("使用模拟市值数据进行演示，实际使用时请替换为真实数据")

    # 为不同行业的股票分配模拟市值（单位：万元）
    mock_market_caps = {
        '银行': 15000000,  # 1500亿
        '地产': 8000000,   # 800亿
        '保险': 12000000,  # 1200亿
        '科技': 3000000,   # 300亿
        '医药': 4000000,   # 400亿
        '消费': 5000000,   # 500亿
        '制造': 2000000,   # 200亿
    }

    # 为每只股票分配模拟市值
    if 'industry' in df.columns:
        df['market_cap'] = df['industry'].map(mock_market_caps).fillna(2000000)
    else:
        df['market_cap'] = 2000000  # 默认值

    # 添加一些随机变化使数据更真实
    import random
    for i in range(len(df)):
        base_cap = df.iloc[i]['market_cap']
        variation = random.uniform(0.5, 2.0)  # 0.5-2倍的随机变化
        df.iloc[i, df.columns.get_loc('market_cap')] = base_cap * variation

    logger.info(f"使用模拟数据为{len(df)}只股票分配了市值信息")
    return df

def _filter_by_market_cap(df: pd.DataFrame, min_market_cap: float, max_market_cap: float) -> pd.DataFrame:
    """
    根据市值筛选股票
    - min_market_cap: 最小市值（亿元）
    - max_market_cap: 最大市值（亿元）
    """
    if 'market_cap' not in df.columns:
        logger.warning("股票列表中缺少市值信息，跳过市值筛选")
        return df

    # 将市值转换为亿元单位（注意：模拟数据的单位是万元）
    market_cap_yi = df['market_cap'] / 1e4  # 万元转亿元

    mask = (market_cap_yi >= min_market_cap) & (market_cap_yi <= max_market_cap)
    filtered_df = df[mask].copy()

    logger.info(f"市值筛选：{min_market_cap}亿 ≤ 市值 ≤ {max_market_cap}亿，筛选后 {len(filtered_df)}/{len(df)} 只股票")
    return filtered_df

def load_codes_from_stocklist(stocklist_csv: Path, exclude_boards: set[str],
                             min_market_cap: Optional[float] = None,
                             max_market_cap: Optional[float] = None) -> List[str]:
    """
    从股票列表中加载股票代码，支持板块过滤和市值筛选
    """
    df = pd.read_csv(stocklist_csv)
    df = _filter_by_boards_stocklist(df, exclude_boards)

    # 如果需要进行市值筛选，获取市值信息
    if min_market_cap is not None or max_market_cap is not None:
        df = _add_market_cap_info(df)
        if min_market_cap is None:
            min_market_cap = 0
        if max_market_cap is None:
            max_market_cap = float('inf')
        df = _filter_by_market_cap(df, min_market_cap, max_market_cap)

    codes = df["symbol"].astype(str).str.zfill(6).tolist()
    codes = list(dict.fromkeys(codes))  # 去重保持顺序

    filter_info = []
    if exclude_boards:
        filter_info.append(f"排除板块：{','.join(sorted(exclude_boards))}")
    if min_market_cap is not None or max_market_cap is not None:
        filter_info.append(f"市值范围：{min_market_cap or 0}亿-{max_market_cap or '∞'}亿")

    logger.info("从 %s 读取到 %d 只股票（%s）",
                stocklist_csv, len(codes), "；".join(filter_info) or "无过滤")
    return codes

# --------------------------- 单只抓取（全量覆盖保存） --------------------------- #
def fetch_one(
    code: str,
    start: str,
    end: str,
    out_dir: Path,
):
    csv_path = out_dir / f"{code}.csv"

    for attempt in range(1, 4):
        try:
            new_df = _get_kline_tushare(code, start, end)
            if new_df.empty:
                logger.debug("%s 无数据，生成空表。", code)
                new_df = pd.DataFrame(columns=["date", "open", "close", "high", "low", "volume"])
            new_df = validate(new_df)
            new_df.to_csv(csv_path, index=False)  # 直接覆盖保存
            break
        except Exception as e:
            if _looks_like_ip_ban(e):
                logger.error(f"{code} 第 {attempt} 次抓取疑似被封禁，沉睡 {COOLDOWN_SECS} 秒")
                _cool_sleep(COOLDOWN_SECS)
            else:
                silent_seconds = 15 * attempt
                logger.info(f"{code} 第 {attempt} 次抓取失败，{silent_seconds} 秒后重试：{e}")
                time.sleep(silent_seconds)
    else:
        logger.error("%s 三次抓取均失败，已跳过！", code)

# --------------------------- 主入口 --------------------------- #
def main():
    parser = argparse.ArgumentParser(description="从 stocklist.csv 读取股票池并用 Tushare 抓取日线K线（固定qfq，全量覆盖）")
    # 抓取范围
    parser.add_argument("--start", default="20190101", help="起始日期 YYYYMMDD 或 'today'")
    parser.add_argument("--end", default="today", help="结束日期 YYYYMMDD 或 'today'")
    # 股票清单与板块过滤
    parser.add_argument("--stocklist", type=Path, default=Path("./stocklist.csv"), help="股票清单CSV路径（需含 ts_code 或 symbol）")
    parser.add_argument(
        "--exclude-boards",
        nargs="*",
        default=[],
        choices=["gem", "star", "bj"],
        help="排除板块，可多选：gem(创业板300/301) star(科创板688) bj(北交所.BJ/4/8)"
    )
    # 市值筛选（单位：亿元）
    parser.add_argument("--min-market-cap", type=float, default=None, help="最小市值筛选（亿元），如100表示只选市值≥100亿的股票")
    parser.add_argument("--max-market-cap", type=float, default=None, help="最大市值筛选（亿元），如2000表示只选市值≤2000亿的股票")
    # 其它
    parser.add_argument("--out", default="./data", help="输出目录")
    parser.add_argument("--workers", type=int, default=6, help="并发线程数")
    parser.add_argument("--no-rate-limit", action="store_true", help="禁用限速模式（可能触发接口限制）")
    parser.add_argument("--rate-limit-interval", type=float, default=REQUEST_INTERVAL, help=f"限速间隔秒数（默认{REQUEST_INTERVAL:.1f}秒）")
    args = parser.parse_args()

    # ---------- Tushare Token ---------- #
    os.environ["NO_PROXY"] = "api.waditu.com,.waditu.com,waditu.com"
    os.environ["no_proxy"] = os.environ["NO_PROXY"]
    ts_token = os.environ.get("TUSHARE_TOKEN")
    if not ts_token:
        raise ValueError("请先设置环境变量 TUSHARE_TOKEN，例如：export TUSHARE_TOKEN=你的token")
    ts.set_token(ts_token)
    global pro
    pro = ts.pro_api()

    # ---------- 限速器初始化 ---------- #
    global rate_limiter
    if not args.no_rate_limit:
        rate_limit_interval = args.rate_limit_interval
        rate_limiter = RateLimiter(rate_limit_interval)
        logger.info(f"启用限速模式：每{rate_limit_interval:.2f}秒最多1次请求（约{60/rate_limit_interval:.0f}次/分钟）")
    else:
        logger.warning("禁用限速模式，可能触发接口限制！")

    # ---------- 日期解析 ---------- #
    start = dt.date.today().strftime("%Y%m%d") if str(args.start).lower() == "today" else args.start
    end = dt.date.today().strftime("%Y%m%d") if str(args.end).lower() == "today" else args.end

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    # ---------- 从 stocklist.csv 读取股票池 ---------- #
    exclude_boards = set(args.exclude_boards or [])
    codes = load_codes_from_stocklist(
        args.stocklist,
        exclude_boards,
        min_market_cap=args.min_market_cap,
        max_market_cap=args.max_market_cap
    )

    if not codes:
        logger.error("stocklist 为空或被过滤后无代码，请检查。")
        sys.exit(1)

    # 构建筛选信息
    filter_desc = []
    if exclude_boards:
        filter_desc.append(f"排除:{','.join(sorted(exclude_boards))}")
    if args.min_market_cap is not None or args.max_market_cap is not None:
        min_cap = args.min_market_cap or 0
        max_cap = args.max_market_cap or '∞'
        filter_desc.append(f"市值:{min_cap}亿-{max_cap}亿")

    logger.info(
        "开始抓取 %d 支股票 | 数据源:Tushare(日线,qfq) | 日期:%s → %s | %s",
        len(codes), start, end, " | ".join(filter_desc) or "无筛选"
    )

    # ---------- 多线程抓取（全量覆盖） ---------- #
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [
            executor.submit(
                fetch_one,
                code,
                start,
                end,
                out_dir,
            )
            for code in codes
        ]
        for _ in tqdm(as_completed(futures), total=len(futures), desc="下载进度"):
            pass

    logger.info("全部任务完成，数据已保存至 %s", out_dir.resolve())

if __name__ == "__main__":
    main()
